"""Phase 32, lot 3 — encaissement en espèces fait SANS INTERNET, envoyé au retour du réseau.

- `POST /payments` accepte la mention « hors connexion » (heure réelle, reçu provisoire) et la caisse
  ouverte au moment de l'encaissement : refus 409 si cette caisse n'est plus ouverte (jamais rattaché
  en silence à une autre session) ; renvoi idempotent même après la clôture.
- `GET /cashier/offline-roster` : liste gardée sur l'appareil, seulement avec une caisse ouverte.
"""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.fees.models import Payment
from app.modules.fees.service import _render_receipt_html
from app.modules.schools.models import School
from app.modules.students.models import Student
from tests.conftest import add_school_to_organization
from tests.test_cash_register import (
    _audit_actions,
    _cashier_ctx,
    _close,
    _count,
    _detail,
    _payment_session_id,
    open_cash_session,
)
from tests.test_cashier_workstation import _add_student
from tests.test_fees import _create_user_with_role, _full_fee_setup, _payment_payload

ROSTER_KEYS = {"school_id", "currency", "generated_at", "cash_session_id", "truncated", "students"}
ROSTER_STUDENT_KEYS = {"id", "matricule", "first_name", "last_name", "current_class_name", "fees"}


def _provisional() -> str:
    return f"PROV-{uuid.uuid4().hex[:10].upper()}"


def _collected_at() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=30)


def _offline_payload(ctx: dict, amount: float, *, session_id: str | None = None, key: str | None = None, **overrides) -> dict:
    payload = _payment_payload(ctx, amount, key)
    payload.update(
        {
            "offline_collected_at": _collected_at().isoformat(),
            "provisional_receipt_number": _provisional(),
            "cash_session_id": session_id or ctx["session"]["id"],
        }
    )
    payload.update(overrides)
    return payload


async def _post(client: AsyncClient, payload: dict, headers: dict):
    return await client.post("/api/v1/payments", json=payload, headers=headers)


async def _audit_summaries(school_id: str, action: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = await db.execute(
            text("SELECT summary FROM audit_logs WHERE school_id = :s AND action = :a ORDER BY created_at"),
            {"s": uuid.UUID(school_id), "a": action},
        )
        return [row[0] for row in rows.all()]


async def _close_session(client: AsyncClient, session_id: str, headers: dict) -> None:
    detail = await _detail(client, session_id, headers)
    expected = detail["totals"]["expected_amount"]
    count = await _count(client, session_id, headers, [("500", int(Decimal(expected) / 500))])
    assert count.status_code == 201, count.text
    closed = await _close(client, session_id, headers, count.json()["id"], expected)
    assert closed.status_code == 200, closed.text


# === Encaissement hors connexion =====================================================================================
async def test_offline_payment_is_recorded_in_its_session_and_marked(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "offpay", opening="0")
    payload = _offline_payload(ctx, 15000)
    response = await _post(client, payload, ctx["headers"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["receipt_number"].startswith("RCPT-")  # numéro officiel attribué par le serveur
    assert body["provisional_receipt_number"] == payload["provisional_receipt_number"]
    assert datetime.fromisoformat(body["offline_collected_at"]) == datetime.fromisoformat(payload["offline_collected_at"])
    assert str(await _payment_session_id(body["id"])) == ctx["session"]["id"]

    day = (
        await client.get(f"/api/v1/cashier/payments?school_id={ctx['school']['id']}&day=2026-10-01", headers=ctx["headers"])
    ).json()
    assert [p["provisional_receipt_number"] for p in day["payments"]] == [payload["provisional_receipt_number"]]
    assert day["payments"][0]["offline_collected_at"] is not None

    detail = await _detail(client, ctx["session"]["id"], ctx["headers"])
    assert detail["payments"][0]["provisional_receipt_number"] == payload["provisional_receipt_number"]
    assert Decimal(detail["totals"]["cash_payments_total"]) == 15000  # compté dans la caisse comme un autre

    summaries = await _audit_summaries(ctx["school"]["id"], "payment.recorded")
    assert len(summaries) == 1 and payload["provisional_receipt_number"] in summaries[0]


async def test_online_payment_has_no_offline_mention(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "offonline", opening="0")
    response = await _post(client, _payment_payload(ctx, 1000), ctx["headers"])
    assert response.status_code == 201, response.text
    assert response.json()["offline_collected_at"] is None
    assert response.json()["provisional_receipt_number"] is None


async def test_offline_replay_returns_same_payment_even_after_close(client: AsyncClient) -> None:
    """Coupure pendant l'envoi : le serveur a enregistré le paiement mais l'appareil ne le sait pas.
    Le renvoi (même clé) rend le même paiement, même si la caisse a été clôturée entre-temps."""
    ctx = await _cashier_ctx(client, "offreplay", opening="0")
    payload = _offline_payload(ctx, 3000)
    first = await _post(client, payload, ctx["headers"])
    assert first.status_code == 201, first.text
    await _close_session(client, ctx["session"]["id"], ctx["headers"])
    replay = await _post(client, payload, ctx["headers"])
    assert replay.status_code == 201 and replay.json()["id"] == first.json()["id"]
    assert (await _audit_actions(ctx["school"]["id"])).count("payment.recorded") == 1


async def test_offline_payment_refused_when_its_session_is_no_longer_open(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "offclosed", opening="0")
    director = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "DIRECTOR", "offclosed.dir")
    old_session = ctx["session"]["id"]
    payload = _offline_payload(ctx, 2000)
    # La supervision clôture la caisse pendant la coupure, puis le caissier en rouvre une autre.
    await _close_session(client, old_session, director["headers"])
    new_session = (await open_cash_session(client, ctx["headers"], ctx["school"]["id"]))["session"]["id"]

    refused = await _post(client, payload, ctx["headers"])
    assert refused.status_code == 409
    assert refused.json()["detail"] == "The cash session open when this payment was collected is no longer open"
    unknown = await _post(client, _offline_payload(ctx, 2000, session_id=str(uuid.uuid4())), ctx["headers"])
    assert unknown.status_code == 409
    assert (await _detail(client, new_session, ctx["headers"]))["totals"]["cash_payments_count"] == 0  # jamais rattaché ailleurs

    accepted = await _post(client, _offline_payload(ctx, 2000, session_id=new_session), ctx["headers"])
    assert accepted.status_code == 201, accepted.text
    assert str(await _payment_session_id(accepted.json()["id"])) == new_session


@pytest.mark.parametrize(
    "overrides",
    [
        {"offline_collected_at": None},  # reçu provisoire sans heure d'encaissement
        {"provisional_receipt_number": None},  # heure sans reçu provisoire
        {"provisional_receipt_number": "PROV-123"},
        {"provisional_receipt_number": "PROV-abcdef0123"},
        {"provisional_receipt_number": "RCPT-ABCDEF0123"},
        {"cash_session_id": None},
        {"offline_collected_at": "2026-11-17T09:00:00"},  # sans fuseau
        {"offline_collected_at": "FUTURE"},
        {"method": "BANK_TRANSFER"},
    ],
)
async def test_offline_fields_are_validated(client: AsyncClient, overrides: dict) -> None:
    ctx = await _cashier_ctx(client, "offvalid", opening="0")
    if overrides.get("offline_collected_at") == "FUTURE":
        overrides = {"offline_collected_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    payload = _offline_payload(ctx, 1000, **overrides)
    # L'administrateur peut enregistrer d'autres modes que les espèces : le refus vient bien de la règle
    # « hors connexion = espèces », pas de la règle du caissier.
    headers = ctx["admin_headers"] if overrides.get("method") else ctx["headers"]
    response = await _post(client, payload, headers)
    assert response.status_code == 422, response.text
    assert (await _detail(client, ctx["session"]["id"], ctx["headers"]))["totals"]["cash_payments_count"] == 0


async def test_provisional_receipt_number_is_unique_per_school(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "offunique", opening="0")
    provisional = _provisional()
    first = await _post(client, _offline_payload(ctx, 1000, provisional_receipt_number=provisional), ctx["headers"])
    assert first.status_code == 201, first.text
    second = await _post(client, _offline_payload(ctx, 1000, provisional_receipt_number=provisional), ctx["headers"])
    assert second.status_code == 409
    assert (await _detail(client, ctx["session"]["id"], ctx["headers"]))["totals"]["cash_payments_count"] == 1


def test_official_receipt_names_the_provisional_receipt() -> None:
    school = School(name="École Test", currency="XOF", timezone="Africa/Lome")
    student = Student(first_name="Ama", last_name="Elève", matricule="F1")
    common = {
        "receipt_number": "RCPT-ABCDEF1234",
        "paid_at": date(2026, 11, 17),
        "method": "CASH",
        "reference": None,
        "payer_name": None,
        "amount": Decimal("1000.00"),
    }
    offline = Payment(
        **common,
        offline_collected_at=datetime(2026, 11, 17, 9, 5, tzinfo=timezone.utc),
        provisional_receipt_number="PROV-0123456789",
    )
    html = _render_receipt_html(school, student, offline, [("Scolarité", Decimal("1000.00"))], Decimal("0"))
    assert "remplace le reçu provisoire n° PROV-0123456789" in html
    assert "17/11/2026 à 09:05" in html  # heure de Lomé (UTC+0)
    online = _render_receipt_html(school, student, Payment(**common), [("Scolarité", Decimal("1000.00"))], Decimal("0"))
    assert "provisoire" not in online


# === Liste gardée sur l'appareil =====================================================================================
async def test_offline_roster_lists_students_who_still_owe_with_their_fees(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "offroster", opening="0")
    school_id = ctx["school"]["id"]
    await _add_student(client, school_id, ctx["admin_headers"], f"N{uuid.uuid4().hex[:6]}", "Kofi", "Sansfrais")

    async def roster() -> dict:
        response = await client.get(f"/api/v1/cashier/offline-roster?school_id={school_id}", headers=ctx["headers"])
        assert response.status_code == 200, response.text
        return response.json()

    body = await roster()
    assert set(body) == ROSTER_KEYS
    assert body["cash_session_id"] == ctx["session"]["id"] and body["currency"] == "XOF" and body["truncated"] is False
    assert [s["id"] for s in body["students"]] == [ctx["student"]["id"]]  # l'élève sans frais n'y est pas
    student = body["students"][0]
    assert set(student) == ROSTER_STUDENT_KEYS  # projection minimale + frais, jamais le dossier complet
    assert student["current_class_name"] == "A"
    fee = student["fees"][0]
    assert fee["id"] == ctx["student_fee"]["id"]
    assert Decimal(fee["amount_due"]) == 50000 and Decimal(fee["balance"]) == 50000

    # Même calcul que la situation financière de l'élève.
    assert (await _post(client, _payment_payload(ctx, 20000), ctx["headers"])).status_code == 201
    fee = (await roster())["students"][0]["fees"][0]
    summary = (await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=ctx["admin_headers"])).json()
    assert Decimal(fee["amount_paid"]) == Decimal(summary["fees"][0]["amount_paid"]) == 20000
    assert Decimal(fee["balance"]) == Decimal(summary["fees"][0]["balance"]) == 30000

    # Tout payé : l'élève n'a plus rien à encaisser, il sort de la liste.
    assert (await _post(client, _payment_payload(ctx, 30000), ctx["headers"])).status_code == 201
    assert (await roster())["students"] == []


async def test_offline_roster_requires_an_open_cash_session_and_the_rights(client: AsyncClient) -> None:
    ctx = await _cashier_ctx(client, "offrosterauth", opening=None)
    school_id = ctx["school"]["id"]
    path = f"/api/v1/cashier/offline-roster?school_id={school_id}"

    closed = await client.get(path, headers=ctx["headers"])
    assert closed.status_code == 409
    assert closed.json()["detail"] == "An open cash session is required to prepare offline collection"
    # Administrateur sans caisse ouverte : il a les droits, mais n'encaisse pas -> pas de liste.
    assert (await client.get(path, headers=ctx["admin_headers"])).status_code == 409

    await open_cash_session(client, ctx["headers"], school_id)
    assert (await client.get(path, headers=ctx["headers"])).status_code == 200

    teacher = await _create_user_with_role(client, ctx["admin_headers"], school_id, "TEACHER", "offrosterauth.t")
    assert (await client.get(path, headers=teacher["headers"])).status_code == 403
    sibling = await add_school_to_organization(client, ctx["org"]["id"], "Ecole soeur", "ecole-soeur-off", ctx["admin_headers"])
    assert (
        await client.get(f"/api/v1/cashier/offline-roster?school_id={sibling['id']}", headers=ctx["headers"])
    ).status_code == 403
    other_org = await _full_fee_setup(client, "offrosterother")
    assert (await client.get(path, headers=other_org["admin_headers"])).status_code == 404
