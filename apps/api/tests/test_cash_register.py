"""Caisse scolaire, lot 3 — sessions de caisse (ouverture, encaissements, mouvements, comptage,
écart, clôture), RBAC `cash.register.*`, isolation, RLS, fuseau horaire, rapports."""

import asyncio
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update

from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.cash.service import day_bounds_utc, school_today
from app.modules.fees.models import Payment
from app.modules.schools.models import School
from tests.conftest import add_school_to_organization
from tests.test_fees import _create_user_with_role, _full_fee_setup, _payment_payload


# --- Helpers (aussi utilisés par test_school_cashier.py / test_cashier_workstation.py) -----------------
async def open_cash_session(client: AsyncClient, headers: dict, school_id: str, opening_amount: str = "0") -> dict:
    response = await client.post(
        "/api/v1/cash/sessions/open", json={"school_id": school_id, "opening_amount": opening_amount}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


def _key() -> str:
    return f"mv-{uuid.uuid4().hex}"


async def _cashier_ctx(client: AsyncClient, prefix: str, opening: str | None = "10000") -> dict:
    ctx = await _full_fee_setup(client, prefix)
    ctx["cashier"] = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "CAISSIER", f"{prefix}.cash")
    ctx["headers"] = ctx["cashier"]["headers"]
    if opening is not None:
        ctx["session"] = (await open_cash_session(client, ctx["headers"], ctx["school"]["id"], opening))["session"]
    return ctx


async def _pay(client: AsyncClient, ctx: dict, headers: dict, amount: float, method: str = "CASH", key: str | None = None):
    payload = _payment_payload(ctx, amount, key)
    payload["method"] = method
    return await client.post("/api/v1/payments", json=payload, headers=headers)


async def _movement(client: AsyncClient, session_id: str, headers: dict, **data):
    body = {"reason": "Motif", "idempotency_key": _key(), **data}
    return await client.post(f"/api/v1/cash/sessions/{session_id}/movements", json=body, headers=headers)


async def _count(client: AsyncClient, session_id: str, headers: dict, lines: list[tuple[str, int]]):
    body = {"lines": [{"denomination": d, "quantity": q} for d, q in lines]}
    return await client.post(f"/api/v1/cash/sessions/{session_id}/count", json=body, headers=headers)


async def _detail(client: AsyncClient, session_id: str, headers: dict) -> dict:
    response = await client.get(f"/api/v1/cash/sessions/{session_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _close(client: AsyncClient, session_id: str, headers: dict, count_id: str, expected: str, **extra):
    body = {"count_id": count_id, "expected_amount": expected, **extra}
    return await client.post(f"/api/v1/cash/sessions/{session_id}/close", json=body, headers=headers)


async def _audit_actions(school_id: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = await db.execute(
            text("SELECT action FROM audit_logs WHERE school_id = :s ORDER BY created_at"), {"s": uuid.UUID(school_id)}
        )
        return [row[0] for row in rows.all()]


async def _payment_session_id(payment_id: str) -> uuid.UUID | None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return await db.scalar(select(Payment.cash_session_id).where(Payment.id == uuid.UUID(payment_id)))


def D(value: str | int) -> Decimal:
    return Decimal(str(value))


# === Cycle de vie complet =================================================================================
async def test_full_lifecycle_open_pay_move_count_close(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashlife")
    headers, session_id = ctx["headers"], ctx["session"]["id"]
    assert ctx["session"]["status"] == "OPEN" and D(ctx["session"]["opening_amount"]) == 10000

    current = (await client.get(f"/api/v1/cash/sessions/current?school_id={ctx['school']['id']}", headers=headers)).json()
    assert current["current"]["session"]["id"] == session_id
    assert current["currency"] == "XOF" and D(current["denominations"][0]) == 10000

    paid = await _pay(client, ctx, headers, 15000)
    assert paid.status_code == 201, paid.text
    assert str(await _payment_session_id(paid.json()["id"])) == session_id  # rattaché à la session

    for data in (
        {"type": "CASH_IN", "amount": "5000"},
        {"type": "CASH_OUT", "amount": "2000"},
        {"type": "BANK_DEPOSIT", "amount": "10000", "reference": "BORD-1"},
        {"type": "OTHER", "direction": "OUT", "amount": "1000"},
        {"type": "OTHER", "direction": "IN", "amount": "500"},
    ):
        assert (await _movement(client, session_id, headers, **data)).status_code == 201

    detail = await _detail(client, session_id, headers)
    totals = detail["totals"]
    assert D(totals["cash_payments_total"]) == 15000 and totals["cash_payments_count"] == 1
    assert D(totals["movements_in_total"]) == 5500 and D(totals["movements_out_total"]) == 13000
    assert D(totals["expected_amount"]) == 17500  # 10000 + 15000 + 5500 - 13000
    assert [p["receipt_number"] for p in detail["payments"]] == [paid.json()["receipt_number"]]
    assert len(detail["movements"]) == 5

    count = await _count(client, session_id, headers, [("10000", 1), ("5000", 1), ("2000", 1), ("500", 1)])
    assert count.status_code == 201, count.text
    assert D(count.json()["total_amount"]) == 17500

    closed = await _close(client, session_id, headers, count.json()["id"], totals["expected_amount"])
    assert closed.status_code == 200, closed.text
    session = closed.json()["session"]
    assert session["status"] == "CLOSED" and session["closed_at"]
    assert D(session["expected_amount"]) == 17500 and D(session["counted_amount"]) == 17500
    assert D(session["variance_amount"]) == 0 and session["variance_reason"] is None

    actions = await _audit_actions(ctx["school"]["id"])
    for action in ("cash.session.opened", "payment.recorded", "cash.movement.created", "cash.count.created", "cash.session.closed"):
        assert action in actions
    assert "cash.variance.justified" not in actions
    assert actions.count("cash.movement.created") == 5


# === Règle CASH + session ======================================================================================
async def test_cashier_cash_requires_open_session_and_stays_cash_only(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashreq", opening=None)
    no_session = await _pay(client, ctx, ctx["headers"], 1000)
    assert no_session.status_code == 409
    assert no_session.json()["detail"] == "An open cash session is required to record cash payments"
    transfer = await _pay(client, ctx, ctx["headers"], 1000, "BANK_TRANSFER")
    assert transfer.status_code == 403  # lot 1 inchangé
    await open_cash_session(client, ctx["headers"], ctx["school"]["id"])
    assert (await _pay(client, ctx, ctx["headers"], 1000)).status_code == 201
    assert (await _pay(client, ctx, ctx["headers"], 1000, "CHEQUE")).status_code == 403


async def test_other_roles_keep_existing_flow_and_attach_only_with_their_own_session(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "cashroles")
    accountant = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "ACCOUNTANT", "cashroles.acc")
    without = await _pay(client, ctx, accountant["headers"], 1000)
    assert without.status_code == 201 and await _payment_session_id(without.json()["id"]) is None
    transfer = await _pay(client, ctx, ctx["admin_headers"], 1000, "BANK_TRANSFER")
    assert transfer.status_code == 201 and await _payment_session_id(transfer.json()["id"]) is None

    session = (await open_cash_session(client, accountant["headers"], ctx["school"]["id"]))["session"]
    cash = await _pay(client, ctx, accountant["headers"], 1000)
    assert str(await _payment_session_id(cash.json()["id"])) == session["id"]
    non_cash = await _pay(client, ctx, accountant["headers"], 1000, "CHEQUE")
    assert await _payment_session_id(non_cash.json()["id"]) is None  # seul le CASH est rattaché
    admin_cash = await _pay(client, ctx, ctx["admin_headers"], 1000)
    assert await _payment_session_id(admin_cash.json()["id"]) is None  # jamais la session d'un autre


async def test_payment_idempotent_replay_returns_same_payment_even_after_close(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashidem", opening="0")
    key = uuid.uuid4().hex
    first = await _pay(client, ctx, ctx["headers"], 3000, key=key)
    again = await _pay(client, ctx, ctx["headers"], 3000, key=key)
    assert first.status_code == again.status_code == 201 and first.json()["id"] == again.json()["id"]
    sid = ctx["session"]["id"]
    detail = await _detail(client, sid, ctx["headers"])
    assert detail["totals"]["cash_payments_count"] == 1
    count = (await _count(client, sid, ctx["headers"], [("1000", 3)])).json()
    assert (await _close(client, sid, ctx["headers"], count["id"], detail["totals"]["expected_amount"])).status_code == 200
    replay = await _pay(client, ctx, ctx["headers"], 3000, key=key)
    assert replay.status_code == 201 and replay.json()["id"] == first.json()["id"]
    assert (await _audit_actions(ctx["school"]["id"])).count("payment.recorded") == 1


# === Annulation ===============================================================================================
async def test_cancelled_payment_in_open_session_leaves_expected(client: AsyncClient) -> None:
    """Session OPEN : annulation inchangée (superviseur), le paiement annulé sort du théorique."""
    ctx = await _cashier_ctx(client, "cashcancel", opening="1000")
    sid = ctx["session"]["id"]
    await _pay(client, ctx, ctx["headers"], 4000)
    cancelled = (await _pay(client, ctx, ctx["headers"], 6000)).json()
    assert D((await _detail(client, sid, ctx["headers"]))["totals"]["expected_amount"]) == 11000
    # RBAC inchangé : le caissier n'annule jamais (payments.cancel), même dans sa session ouverte.
    denied = await client.post(f"/api/v1/payments/{cancelled['id']}/cancel", json={"reason": "x"}, headers=ctx["headers"])
    assert denied.status_code == 403
    response = await client.post(
        f"/api/v1/payments/{cancelled['id']}/cancel", json={"reason": "Erreur"}, headers=ctx["admin_headers"]
    )
    assert response.status_code == 200 and response.json()["status"] == "CANCELLED"
    totals = (await _detail(client, sid, ctx["headers"]))["totals"]
    assert D(totals["expected_amount"]) == 5000 and totals["cash_payments_count"] == 1


async def test_payment_without_session_cancellation_unchanged(client: AsyncClient) -> None:
    """Paiement sans session (historique, autre rôle, non CASH) : comportement actuel conservé."""
    ctx = await _full_fee_setup(client, "cashcancelnone")
    cash = (await _pay(client, ctx, ctx["admin_headers"], 2000)).json()
    transfer = (await _pay(client, ctx, ctx["admin_headers"], 3000, "BANK_TRANSFER")).json()
    for payment in (cash, transfer):
        assert await _payment_session_id(payment["id"]) is None
        response = await client.post(
            f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "r"}, headers=ctx["admin_headers"]
        )
        assert response.status_code == 200, response.text
    assert (await _audit_actions(ctx["school"]["id"])).count("payment.cancelled") == 2


async def _db_snapshot(payment_id: str, session_id: str) -> dict:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        pid, sid = uuid.UUID(payment_id), uuid.UUID(session_id)
        payment = (
            await db.execute(
                text("SELECT status, cancelled_at, cancelled_by, cancellation_reason, updated_at FROM payments WHERE id = :p"),
                {"p": pid},
            )
        ).one()
        fees = (
            await db.execute(
                text(
                    "SELECT sf.id, sf.status, sf.updated_at FROM student_fees sf JOIN payment_allocations pa "
                    "ON pa.student_fee_id = sf.id WHERE pa.payment_id = :p ORDER BY sf.id"
                ),
                {"p": pid},
            )
        ).all()
        session = (
            await db.execute(
                text("SELECT status, expected_amount, counted_amount, variance_amount, updated_at FROM cash_sessions WHERE id = :s"),
                {"s": sid},
            )
        ).one()
        movements = await db.scalar(text("SELECT count(*) FROM cash_movements WHERE cash_session_id = :s"), {"s": sid})
        audits = (
            await db.execute(text("SELECT action FROM audit_logs WHERE entity_id = :p ORDER BY created_at"), {"p": pid})
        ).all()
    return {
        "payment": tuple(payment),
        "fees": [tuple(f) for f in fees],
        "session": tuple(session),
        "movements": movements,
        "audits": [a[0] for a in audits],
    }


async def test_payment_of_closed_session_cannot_be_cancelled_and_nothing_changes(client: AsyncClient) -> None:
    """Session CLOSED : refus 409 explicite ; aucune donnée modifiée, aucun audit payment.cancelled."""
    ctx = await _cashier_ctx(client, "cashcancelclosed", opening="1000")
    sid = ctx["session"]["id"]
    paid = (await _pay(client, ctx, ctx["headers"], 4000)).json()
    await _movement(client, sid, ctx["headers"], type="BANK_DEPOSIT", amount="500")
    detail = await _detail(client, sid, ctx["headers"])
    count = (await _count(client, sid, ctx["headers"], [("2000", 2), ("500", 1)])).json()
    assert (await _close(client, sid, ctx["headers"], count["id"], detail["totals"]["expected_amount"])).status_code == 200
    summary_url = f"/api/v1/students/{ctx['student']['id']}/financial-summary"
    summary_before = (await client.get(summary_url, headers=ctx["admin_headers"])).json()
    before = await _db_snapshot(paid["id"], sid)
    cancel_url = f"/api/v1/payments/{paid['id']}/cancel"

    # Isolation conservée : une autre organisation ne voit même pas le paiement (404, avant la règle).
    other = await _full_fee_setup(client, "cashcancelclosedb")
    assert (await client.post(cancel_url, json={"reason": "x"}, headers=other["admin_headers"])).status_code == 404
    # RBAC conservé : le caissier reste refusé (403) avant toute règle de session.
    assert (await client.post(cancel_url, json={"reason": "x"}, headers=ctx["headers"])).status_code == 403

    for _ in range(2):  # second essai compris : refus stable, jamais d'effet de bord
        refused = await client.post(cancel_url, json={"reason": "Tard"}, headers=ctx["admin_headers"])
        assert refused.status_code == 409
        assert refused.json()["detail"] == "A payment belonging to a closed cash session cannot be cancelled"

    after = await _db_snapshot(paid["id"], sid)
    assert after == before  # paiement, frais élève, session, mouvements, audits : identiques
    assert after["payment"][0] == "COMPLETED" and after["payment"][1] is None
    assert "payment.cancelled" not in after["audits"]
    assert (await _audit_actions(ctx["school"]["id"])).count("payment.cancelled") == 0
    assert (await client.get(summary_url, headers=ctx["admin_headers"])).json() == summary_before
    session = (await _detail(client, sid, ctx["headers"]))["session"]
    assert D(session["expected_amount"]) == 4500 and D(session["variance_amount"]) == 0


async def test_unit_cancellation_lock_refuses_unknown_session() -> None:
    """Unitaire : le verrou de session échoue fermé (409) si la session est introuvable."""
    from fastapi import HTTPException

    from app.modules.cash.service import lock_session_for_payment_cancellation

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        with pytest.raises(HTTPException) as exc:
            await lock_session_for_payment_cancellation(db, uuid.uuid4())
        await db.rollback()
    assert exc.value.status_code == 409


async def test_concurrent_close_and_cancel_never_both_succeed(client: AsyncClient) -> None:
    """Clôture et annulation simultanées : exactement une réussit (verrous FOR UPDATE / FOR SHARE
    sur la session) ; une session close garde un théorique figé égal au théorique réel."""
    for attempt in range(4):
        ctx = await _cashier_ctx(client, f"cashrace{attempt}", opening="0")
        sid = ctx["session"]["id"]
        paid = (await _pay(client, ctx, ctx["headers"], 3000)).json()
        detail = await _detail(client, sid, ctx["headers"])
        count = (await _count(client, sid, ctx["headers"], [("1000", 3)])).json()
        close, cancel = await asyncio.gather(
            _close(client, sid, ctx["headers"], count["id"], detail["totals"]["expected_amount"]),
            client.post(f"/api/v1/payments/{paid['id']}/cancel", json={"reason": "course"}, headers=ctx["admin_headers"]),
        )
        assert sorted([close.status_code, cancel.status_code]) == [200, 409], (attempt, close.text, cancel.text)
        final = await _detail(client, sid, ctx["admin_headers"])
        if close.status_code == 200:
            assert final["session"]["status"] == "CLOSED"
            assert D(final["session"]["expected_amount"]) == D(final["totals"]["expected_amount"]) == 3000
            assert (await _db_snapshot(paid["id"], sid))["payment"][0] == "COMPLETED"
        else:
            assert final["session"]["status"] == "OPEN"
            assert D(final["totals"]["expected_amount"]) == 0


# === Mouvements ===============================================================================================
async def test_movement_validation_and_idempotency(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashmove", opening="5000")
    sid, headers = ctx["session"]["id"], ctx["headers"]
    assert (await _movement(client, sid, headers, type="CASH_IN", amount="0")).status_code == 422
    assert (await _movement(client, sid, headers, type="CASH_IN", amount="-5")).status_code == 422
    assert (await _movement(client, sid, headers, type="CASH_IN", amount="100", reason="   ")).status_code == 422
    assert (await _movement(client, sid, headers, type="OTHER", amount="100")).status_code == 422  # direction requise
    assert (await _movement(client, sid, headers, type="UNKNOWN", amount="100")).status_code == 422
    too_much = await _movement(client, sid, headers, type="CASH_OUT", amount="5000.01")
    assert too_much.status_code == 422  # jamais plus que les espèces disponibles

    key = _key()
    first = await _movement(client, sid, headers, type="CASH_IN", amount="700", idempotency_key=key)
    second = await _movement(client, sid, headers, type="CASH_IN", amount="700", idempotency_key=key)
    assert first.status_code == second.status_code == 201 and first.json()["id"] == second.json()["id"]
    detail = await _detail(client, sid, headers)
    assert len(detail["movements"]) == 1 and D(detail["totals"]["expected_amount"]) == 5700
    # La direction d'un type fixe ne peut pas être inversée par le client.
    forced = await _movement(client, sid, headers, type="CASH_OUT", direction="IN", amount="100")
    assert forced.status_code == 201 and forced.json()["direction"] == "OUT"


# === Comptage ===================================================================================================
async def test_count_is_computed_server_side_and_validated(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashcount", opening="0")
    sid, headers = ctx["session"]["id"], ctx["headers"]
    assert (await _count(client, sid, headers, [("3000", 1)])).status_code == 422  # coupure inconnue
    assert (await _count(client, sid, headers, [("1000", 1), ("1000", 2)])).status_code == 422  # doublon
    assert (await _count(client, sid, headers, [("1000", -1)])).status_code == 422
    assert (await client.post(f"/api/v1/cash/sessions/{sid}/count", json={"lines": []}, headers=headers)).status_code == 422

    body = {"lines": [{"denomination": "10000", "quantity": 2}, {"denomination": "25", "quantity": 3}], "total_amount": "1"}
    count = await client.post(f"/api/v1/cash/sessions/{sid}/count", json=body, headers=headers)
    assert count.status_code == 201
    data = count.json()
    assert D(data["total_amount"]) == D("20075")  # total client ignoré, recalculé
    assert {(D(line["denomination"]), line["quantity"], D(line["line_total"])) for line in data["lines"]} == {
        (D(10000), 2, D(20000)),
        (D(25), 3, D(75)),
    }
    recount = (await _count(client, sid, headers, [("500", 1)])).json()
    assert (await _detail(client, sid, headers))["latest_count"]["id"] == recount["id"]


# === Écart, justification, clôture ===============================================================================
async def test_variance_requires_reason_and_note_and_is_audited(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashvar", opening="10000")
    sid, headers = ctx["session"]["id"], ctx["headers"]
    await _pay(client, ctx, headers, 5000)
    expected = (await _detail(client, sid, headers))["totals"]["expected_amount"]
    count = (await _count(client, sid, headers, [("10000", 1), ("2000", 2)])).json()  # 14000 au lieu de 15000

    missing = await _close(client, sid, headers, count["id"], expected)
    assert missing.status_code == 422
    only_reason = await _close(client, sid, headers, count["id"], expected, variance_reason="COUNTING_ERROR")
    assert only_reason.status_code == 422
    blank_note = await _close(client, sid, headers, count["id"], expected, variance_reason="COUNTING_ERROR", variance_note="  ")
    assert blank_note.status_code == 422
    bad_reason = await _close(client, sid, headers, count["id"], expected, variance_reason="WHATEVER", variance_note="x")
    assert bad_reason.status_code == 422

    closed = await _close(
        client, sid, headers, count["id"], expected, variance_reason="CHANGE_ERROR", variance_note="Monnaie rendue en trop"
    )
    assert closed.status_code == 200, closed.text
    session = closed.json()["session"]
    assert D(session["variance_amount"]) == -1000
    assert session["variance_reason"] == "CHANGE_ERROR" and session["variance_note"] == "Monnaie rendue en trop"
    actions = await _audit_actions(ctx["school"]["id"])
    assert "cash.session.closed" in actions and "cash.variance.justified" in actions


async def test_close_guards_count_presence_and_coherent_totals(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashguard", opening="0")
    sid, headers = ctx["session"]["id"], ctx["headers"]
    no_count = await _close(client, sid, headers, str(uuid.uuid4()), "0")
    assert no_count.status_code == 409
    first = (await _count(client, sid, headers, [("1000", 1)])).json()
    newer = (await _count(client, sid, headers, [("1000", 2)])).json()
    stale_count = await _close(client, sid, headers, first["id"], "0", variance_reason="OTHER", variance_note="x")
    assert stale_count.status_code == 409
    await _pay(client, ctx, headers, 2000)  # le théorique change après l'affichage
    stale_expected = await _close(client, sid, headers, newer["id"], "0", variance_reason="OTHER", variance_note="x")
    assert stale_expected.status_code == 409
    ok = await _close(client, sid, headers, newer["id"], "2000.00")
    assert ok.status_code == 200
    assert (await _close(client, sid, headers, newer["id"], "2000.00")).status_code == 409  # pas de double clôture


async def test_closed_session_is_immutable_and_no_retroactive_attachment(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashimmut", opening="0")
    sid, headers = ctx["session"]["id"], ctx["headers"]
    count = (await _count(client, sid, headers, [("1", 0)])).json()
    assert (await _close(client, sid, headers, count["id"], "0.00")).status_code == 200

    assert (await _pay(client, ctx, headers, 1000)).status_code == 409  # plus de session OPEN
    assert (await _movement(client, sid, headers, type="CASH_IN", amount="10")).status_code == 409
    assert (await _count(client, sid, headers, [("1000", 1)])).status_code == 409
    for method in ("PATCH", "PUT", "DELETE"):
        response = await client.request(method, f"/api/v1/cash/sessions/{sid}", json={}, headers=headers)
        assert response.status_code == 405, method  # aucune route de réécriture

    new_session = (await open_cash_session(client, headers, ctx["school"]["id"]))["session"]
    assert new_session["id"] != sid  # pas de réouverture : une NOUVELLE session
    paid = (await _pay(client, ctx, headers, 1000)).json()
    assert str(await _payment_session_id(paid["id"])) == new_session["id"]
    assert (await _detail(client, sid, ctx["admin_headers"]))["totals"]["cash_payments_count"] == 0


# === Une seule session OPEN, y compris en concurrence ===============================================================
async def test_single_open_session_per_cashier_even_concurrently(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashconc", opening=None)
    body = {"school_id": ctx["school"]["id"], "opening_amount": "0"}
    responses = await asyncio.gather(
        *(client.post("/api/v1/cash/sessions/open", json=body, headers=ctx["headers"]) for _ in range(3))
    )
    assert sorted(r.status_code for r in responses) == [201, 409, 409]
    assert (await client.post("/api/v1/cash/sessions/open", json=body, headers=ctx["headers"])).status_code == 409
    bad = await client.post(
        "/api/v1/cash/sessions/open", json={**body, "opening_amount": "-1"}, headers=ctx["headers"]
    )
    assert bad.status_code == 422


# === RBAC ==========================================================================================================
@pytest.mark.parametrize("role_code", ["TEACHER", "STAFF", "PARENT"])
async def test_roles_without_cash_permissions_are_refused(client: AsyncClient, role_code: str) -> None:
    ctx = await _cashier_ctx(client, f"cashdeny{role_code[:4].lower()}")
    other = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], role_code, "cashdeny.u")
    school_id, sid = ctx["school"]["id"], ctx["session"]["id"]
    h = other["headers"]
    assert (await client.get(f"/api/v1/cash/sessions/current?school_id={school_id}", headers=h)).status_code == 403
    assert (await client.post("/api/v1/cash/sessions/open", json={"school_id": school_id, "opening_amount": "0"}, headers=h)).status_code == 403
    assert (await client.get(f"/api/v1/cash/sessions/{sid}", headers=h)).status_code == 403
    assert (await _movement(client, sid, h, type="CASH_IN", amount="1")).status_code == 403
    assert (await client.get(f"/api/v1/cash/sessions?school_id={school_id}", headers=h)).status_code == 403
    assert (await client.get(f"/api/v1/cash/reports/daily?school_id={school_id}", headers=h)).status_code == 403


async def test_cashier_sees_only_own_sessions_and_no_reports(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashown")
    other = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "CAISSIER", "cashown.b")
    other_session = (await open_cash_session(client, other["headers"], ctx["school"]["id"]))["session"]
    school_id = ctx["school"]["id"]

    assert (await client.get(f"/api/v1/cash/sessions/{other_session['id']}", headers=ctx["headers"])).status_code == 403
    assert (await _movement(client, other_session["id"], ctx["headers"], type="CASH_IN", amount="1")).status_code == 403
    listed = (await client.get(
        f"/api/v1/cash/sessions?school_id={school_id}&cashier_user_id={other['user']['id']}", headers=ctx["headers"]
    )).json()
    assert [s["id"] for s in listed] == [ctx["session"]["id"]]  # filtre forcé sur soi
    for path in ("daily", "cashiers", "methods", "export.csv"):
        assert (await client.get(f"/api/v1/cash/reports/{path}?school_id={school_id}", headers=ctx["headers"])).status_code == 403


@pytest.mark.parametrize("role_code", ["DIRECTOR", "ACCOUNTANT"])
async def test_supervisors_review_all_sessions_and_can_close_for_cashier(client: AsyncClient, role_code: str) -> None:
    ctx = await _cashier_ctx(client, f"cashsup{role_code[:4].lower()}", opening="2000")
    supervisor = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], role_code, "cashsup.s")
    h, sid = supervisor["headers"], ctx["session"]["id"]
    listed = (await client.get(f"/api/v1/cash/sessions?school_id={ctx['school']['id']}", headers=h)).json()
    assert [s["id"] for s in listed] == [sid] and listed[0]["cashier_name"]
    detail = await _detail(client, sid, h)
    count = (await _count(client, sid, h, [("2000", 1)])).json()
    closed = await _close(client, sid, h, count["id"], detail["totals"]["expected_amount"])
    assert closed.status_code == 200 and closed.json()["session"]["closed_by"] == supervisor["user"]["id"]


# === Isolation école / organisation et RLS ============================================================================
async def test_school_and_organization_isolation(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashisoa")
    sibling = await add_school_to_organization(client, ctx["org"]["id"], "Ecole soeur", "ecole-soeur", ctx["admin_headers"])
    other_org = await _full_fee_setup(client, "cashisob")
    sid = ctx["session"]["id"]

    # Caissier de l'école A : rien dans l'école soeur (même organisation).
    sibling_open = await client.post(
        "/api/v1/cash/sessions/open", json={"school_id": sibling["id"], "opening_amount": "0"}, headers=ctx["headers"]
    )
    assert sibling_open.status_code == 403
    assert (await client.get(f"/api/v1/cash/sessions/current?school_id={sibling['id']}", headers=ctx["headers"])).status_code == 403
    # Administrateur d'une AUTRE organisation : la session est invisible (RLS -> 404).
    oh = other_org["admin_headers"]
    assert (await client.get(f"/api/v1/cash/sessions/{sid}", headers=oh)).status_code == 404
    assert (await _movement(client, sid, oh, type="CASH_IN", amount="1")).status_code == 404
    assert (await client.get(f"/api/v1/cash/sessions?school_id={ctx['school']['id']}", headers=oh)).status_code == 404
    assert (await client.get(f"/api/v1/cash/reports/daily?school_id={ctx['school']['id']}", headers=oh)).status_code == 404
    # Superviseur de l'école soeur (rôle scopé à cette école) : aucun accès à l'école A.
    sib_director = await _create_user_with_role(client, ctx["admin_headers"], sibling["id"], "DIRECTOR", "cashisoa.dir")
    assert (await client.get(f"/api/v1/cash/sessions/{sid}", headers=sib_director["headers"])).status_code == 403
    assert (await client.get(f"/api/v1/cash/reports/daily?school_id={ctx['school']['id']}", headers=sib_director["headers"])).status_code == 403


async def test_rls_hides_cash_rows_from_other_organization(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashrlsa", opening="1000")
    sid = ctx["session"]["id"]
    await _movement(client, sid, ctx["headers"], type="CASH_IN", amount="10")
    await _count(client, sid, ctx["headers"], [("1000", 1)])
    other = await _full_fee_setup(client, "cashrlsb")
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(other["admin_user_id"]))
        for table in ("cash_sessions", "cash_movements", "cash_counts", "cash_count_lines"):
            visible = await db.scalar(text(f"SELECT count(*) FROM {table} WHERE school_id = :s"), {"s": uuid.UUID(ctx["school"]["id"])})
            assert visible == 0, table
        await db.rollback()
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(ctx["admin_user_id"]))
        for table in ("cash_sessions", "cash_movements", "cash_counts", "cash_count_lines"):
            visible = await db.scalar(text(f"SELECT count(*) FROM {table} WHERE school_id = :s"), {"s": uuid.UUID(ctx["school"]["id"])})
            assert visible >= 1, table
        await db.rollback()


# === Fuseau horaire de l'école ==========================================================================================
def test_day_bounds_follow_school_timezone() -> None:
    lome = School(timezone="Africa/Lome")
    kiritimati = School(timezone="Pacific/Kiritimati")  # UTC+14
    assert day_bounds_utc(lome, date(2026, 10, 14), date(2026, 10, 14)) == (
        datetime(2026, 10, 14, 0, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 15, 0, 0, tzinfo=timezone.utc),
    )
    assert day_bounds_utc(kiritimati, date(2026, 10, 14), date(2026, 10, 14)) == (
        datetime(2026, 10, 13, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 10, 14, 10, 0, tzinfo=timezone.utc),
    )
    late_utc = datetime(2026, 10, 14, 20, 0, tzinfo=timezone.utc)
    assert school_today(lome, late_utc) == date(2026, 10, 14)
    assert school_today(kiritimati, late_utc) == date(2026, 10, 15)
    assert school_today(School(timezone="Not/AZone"), late_utc) == date(2026, 10, 14)  # repli UTC


async def test_business_date_uses_school_timezone(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashtz", opening=None)
    tz = "Pacific/Kiritimati"
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(update(School).where(School.id == uuid.UUID(ctx["school"]["id"])).values(timezone=tz))
        await db.commit()
    expected_day = datetime.now(ZoneInfo(tz)).date().isoformat()
    current = (await client.get(f"/api/v1/cash/sessions/current?school_id={ctx['school']['id']}", headers=ctx["headers"])).json()
    assert current["timezone"] == tz and current["business_date"] == expected_day
    session = (await open_cash_session(client, ctx["headers"], ctx["school"]["id"]))["session"]
    assert session["business_date"] == expected_day
    report = (await client.get(f"/api/v1/cash/reports/daily?school_id={ctx['school']['id']}", headers=ctx["admin_headers"])).json()
    assert report["day"] == expected_day and report["sessions"]["sessions_count"] == 1
    day = (await client.get(f"/api/v1/cashier/payments?school_id={ctx['school']['id']}", headers=ctx["headers"])).json()
    assert day["day"] == expected_day  # journal du jour (lot 2) aligné sur le fuseau de l'école


# === Rapports (agrégations SQL) et CSV ====================================================================================
async def test_reports_aggregate_sessions_methods_and_cashiers(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashrep", opening="1000")
    second = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "CAISSIER", "cashrep.b")
    second_session = (await open_cash_session(client, second["headers"], ctx["school"]["id"], "500"))["session"]
    school_id = ctx["school"]["id"]
    today = (await client.get(f"/api/v1/cash/sessions/current?school_id={school_id}", headers=ctx["headers"])).json()["business_date"]

    def pay_today(headers: dict, amount: float, method: str = "CASH"):
        payload = _payment_payload(ctx, amount)
        payload.update(method=method, paid_at=today)
        return client.post("/api/v1/payments", json=payload, headers=headers)

    await pay_today(ctx["headers"], 3000)
    await pay_today(second["headers"], 2000)
    cancelled = (await pay_today(second["headers"], 700)).json()
    await client.post(f"/api/v1/payments/{cancelled['id']}/cancel", json={"reason": "x"}, headers=ctx["admin_headers"])
    await pay_today(ctx["admin_headers"], 4000, "BANK_TRANSFER")
    await _movement(client, ctx["session"]["id"], ctx["headers"], type="BANK_DEPOSIT", amount="1500")
    # Clôture de la session 2 avec un écart (+100).
    s2 = await _detail(client, second_session["id"], second["headers"])
    count = (await _count(client, second_session["id"], second["headers"], [("2000", 1), ("500", 1), ("100", 1)])).json()
    assert (await _close(
        client, second_session["id"], second["headers"], count["id"], s2["totals"]["expected_amount"],
        variance_reason="COUNTING_ERROR", variance_note="=HYPERLINK(\"x\")",
    )).status_code == 200

    h = ctx["admin_headers"]
    daily = (await client.get(f"/api/v1/cash/reports/daily?school_id={school_id}", headers=h)).json()
    sessions = daily["sessions"]
    assert (sessions["sessions_count"], sessions["open_count"], sessions["closed_count"]) == (2, 1, 1)
    assert D(sessions["opening_total"]) == 1500 and D(sessions["cash_payments_total"]) == 5000
    assert D(sessions["movements_out_total"]) == 1500
    assert D(sessions["expected_total"]) == D(2500) + D(2500)  # 1000+3000-1500 ; 500+2000 (figé)
    assert D(sessions["counted_total"]) == 2600 and D(sessions["variance_total"]) == 100
    methods = {row["method"]: row for row in daily["payments_by_method"]}
    assert D(methods["CASH"]["completed_total"]) == 5000 and methods["CASH"]["cancelled_count"] == 1
    assert D(methods["CASH"]["cancelled_total"]) == 700 and D(methods["BANK_TRANSFER"]["completed_total"]) == 4000

    cashiers = (await client.get(f"/api/v1/cash/reports/cashiers?school_id={school_id}", headers=h)).json()["rows"]
    by_cashier = {row["cashier_user_id"]: row for row in cashiers}
    assert D(by_cashier[ctx["cashier"]["user"]["id"]]["cash_payments_total"]) == 3000
    assert D(by_cashier[second["user"]["id"]]["variance_total"]) == 100

    by_method = (await client.get(f"/api/v1/cash/reports/methods?school_id={school_id}&date_from={today}&date_to={today}", headers=h)).json()
    assert {row["method"] for row in by_method["rows"]} == {"CASH", "BANK_TRANSFER"}
    assert (await client.get(f"/api/v1/cash/reports/methods?school_id={school_id}&date_from=2026-10-10&date_to=2026-10-01", headers=h)).status_code == 422

    csv_response = await client.get(f"/api/v1/cash/reports/export.csv?school_id={school_id}", headers=h)
    assert csv_response.status_code == 200 and csv_response.headers["content-type"].startswith("text/csv")
    lines = csv_response.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("session_id;date_metier;caissier") and len(lines) == 3
    assert "'=HYPERLINK" in csv_response.text  # injection de formule neutralisée


async def test_session_list_filters(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "cashlist", opening="0")
    h, school_id = ctx["admin_headers"], ctx["school"]["id"]
    assert len((await client.get(f"/api/v1/cash/sessions?school_id={school_id}&status=OPEN", headers=h)).json()) == 1
    assert (await client.get(f"/api/v1/cash/sessions?school_id={school_id}&status=CLOSED", headers=h)).json() == []
    assert (await client.get(f"/api/v1/cash/sessions?school_id={school_id}&date_to=2020-01-01", headers=h)).json() == []
    assert (await client.get(f"/api/v1/cash/sessions?school_id={school_id}&status=WRONG", headers=h)).status_code == 422
