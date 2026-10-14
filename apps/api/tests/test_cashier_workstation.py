"""Caisse scolaire, lot 2 — endpoints dédiés au poste de caisse (`/cashier/*`).

Le CAISSIER n'a pas `students.read` (lot 1) : la recherche d'élève dédiée ne doit ni élargir ses
permissions, ni exposer le dossier complet, ni introduire une liste complète des élèves.
"""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient

from tests.conftest import add_school_to_organization
from tests.test_fees import _create_user_with_role, _full_fee_setup, _payment_payload

SEARCH_KEYS = {"id", "matricule", "first_name", "last_name", "current_class_name"}


async def _env(client: AsyncClient, prefix: str) -> dict:
    ctx = await _full_fee_setup(client, prefix)
    ctx["cashier"] = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "CAISSIER", f"{prefix}.cashier")
    return ctx


async def _search(client: AsyncClient, school_id: str, term: str, headers: dict, **extra: str):
    params = {"school_id": school_id, "search": term, **extra}
    return await client.get("/api/v1/cashier/students/search", params=params, headers=headers)


async def _add_student(client: AsyncClient, school_id: str, headers: dict, matricule: str, first: str, last: str) -> dict:
    response = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_id,
            "matricule": matricule,
            "first_name": first,
            "last_name": last,
            "date_of_birth": str(date(2015, 1, 1)),
            "sex": "M",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# === Recherche ========================================================================================
async def test_cashier_searches_own_school_by_matricule_first_and_last_name(client: AsyncClient) -> None:
    ctx = await _env(client, "cwsearch")
    headers = ctx["cashier"]["headers"]
    student = ctx["student"]
    for term in (student["matricule"], student["matricule"].lower(), "ama", "AMA", "Elève"):
        response = await _search(client, ctx["school"]["id"], term, headers)
        assert response.status_code == 200, (term, response.text)
        results = response.json()
        assert [r["id"] for r in results] == [student["id"]], term
        assert set(results[0]) == SEARCH_KEYS  # projection minimale, jamais le dossier complet
        assert results[0]["current_class_name"] == "A"
    assert (await _search(client, ctx["school"]["id"], "zzzz-introuvable", headers)).json() == []


async def test_search_requires_a_real_term_and_never_lists_every_student(client: AsyncClient) -> None:
    ctx = await _env(client, "cwterm")
    headers = ctx["cashier"]["headers"]
    school_id = ctx["school"]["id"]
    missing = await client.get(f"/api/v1/cashier/students/search?school_id={school_id}", headers=headers)
    assert missing.status_code == 422
    for term in ("", "a", "  b  "):
        assert (await _search(client, school_id, term, headers)).status_code == 422, repr(term)
    # Jokers SQL échappés : "%%" ou "__" ne deviennent jamais un "tout lister".
    for wildcard in ("%%", "__", "%_"):
        response = await _search(client, school_id, wildcard, headers)
        assert response.status_code == 200 and response.json() == [], wildcard
    assert (await _search(client, school_id, "ama", headers, limit="51")).status_code == 422


async def test_search_results_are_capped(client: AsyncClient) -> None:
    ctx = await _env(client, "cwcap")
    suffix = uuid.uuid4().hex[:6]
    for i in range(4):
        await _add_student(client, ctx["school"]["id"], ctx["admin_headers"], f"CAP{suffix}{i}", "Kossi", f"Cap{i}")
    response = await _search(client, ctx["school"]["id"], f"CAP{suffix}", ctx["cashier"]["headers"], limit="3")
    assert response.status_code == 200
    assert len(response.json()) == 3


async def test_cashier_cannot_search_sibling_school_of_same_organization(client: AsyncClient) -> None:
    ctx = await _env(client, "cwsib")
    sibling = await add_school_to_organization(client, ctx["org"]["id"], "Ecole soeur", "ecole-soeur", ctx["admin_headers"])
    await _add_student(client, sibling["id"], ctx["admin_headers"], f"SIB{uuid.uuid4().hex[:6]}", "Ama", "Soeur")
    response = await _search(client, sibling["id"], "ama", ctx["cashier"]["headers"])
    assert response.status_code == 403


async def test_cashier_cannot_search_another_organization(client: AsyncClient) -> None:
    ctx_a = await _env(client, "cworga")
    ctx_b = await _full_fee_setup(client, "cworgb")
    response = await _search(client, ctx_b["school"]["id"], "ama", ctx_a["cashier"]["headers"])
    assert response.status_code == 404  # école invisible sous RLS, même convention que GET /payments


@pytest.mark.parametrize("role_code", ["TEACHER", "STAFF", "PARENT"])
async def test_unauthorized_roles_cannot_use_cashier_search(client: AsyncClient, role_code: str) -> None:
    ctx = await _full_fee_setup(client, f"cwdeny{role_code[:4].lower()}")
    other = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], role_code, "cwdeny.user")
    assert (await _search(client, ctx["school"]["id"], "ama", other["headers"])).status_code == 403


@pytest.mark.parametrize("role_code", ["ACCOUNTANT", "DIRECTOR"])
async def test_other_payment_roles_can_use_cashier_search(client: AsyncClient, role_code: str) -> None:
    ctx = await _full_fee_setup(client, f"cwallow{role_code[:4].lower()}")
    user = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], role_code, "cwallow.user")
    response = await _search(client, ctx["school"]["id"], "ama", user["headers"])
    assert response.status_code == 200 and [r["id"] for r in response.json()] == [ctx["student"]["id"]]
    assert (await _search(client, ctx["school"]["id"], "ama", ctx["admin_headers"])).status_code == 200


async def test_cashier_still_has_no_access_to_student_list_or_record(client: AsyncClient) -> None:
    ctx = await _env(client, "cwnolist")
    headers = ctx["cashier"]["headers"]
    assert (await client.get(f"/api/v1/students?school_id={ctx['school']['id']}", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/students/{ctx['student']['id']}", headers=headers)).status_code == 403
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert "students.read" not in me["permissions"]


# === Encaissement depuis le poste de caisse (POST /payments existant) ====================================
async def test_cashier_flow_records_cash_and_keeps_lot1_restrictions(client: AsyncClient) -> None:
    ctx = await _env(client, "cwflow")
    headers = ctx["cashier"]["headers"]
    found = (await _search(client, ctx["school"]["id"], ctx["student"]["matricule"], headers)).json()
    assert found[0]["id"] == ctx["student"]["id"]

    paid = await client.post("/api/v1/payments", json=_payment_payload(ctx, 20000), headers=headers)
    assert paid.status_code == 201, paid.text
    summary = (await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=headers)).json()
    assert summary["fees"][0]["balance"] == "30000.00"

    cancel = await client.post(f"/api/v1/payments/{paid.json()['id']}/cancel", json={"reason": "X"}, headers=headers)
    assert cancel.status_code == 403
    transfer = _payment_payload(ctx, 1000)
    transfer["method"] = "BANK_TRANSFER"
    assert (await client.post("/api/v1/payments", json=transfer, headers=headers)).status_code == 403


# === Journal de caisse du jour ==============================================================================
async def test_cashier_day_lists_only_own_payments_with_student_identity(client: AsyncClient) -> None:
    ctx = await _env(client, "cwday")
    headers = ctx["cashier"]["headers"]
    today = date.today().isoformat()
    mine = _payment_payload(ctx, 15000)
    mine["paid_at"] = today
    mine_paid = (await client.post("/api/v1/payments", json=mine, headers=headers)).json()
    admin = _payment_payload(ctx, 5000)
    admin["paid_at"] = today
    admin_paid = (await client.post("/api/v1/payments", json=admin, headers=ctx["admin_headers"])).json()
    older = _payment_payload(ctx, 1000)  # autre jour : jamais dans le journal du jour
    older["paid_at"] = "2020-01-01"
    assert (await client.post("/api/v1/payments", json=older, headers=headers)).status_code == 201

    response = await client.get(f"/api/v1/cashier/payments?school_id={ctx['school']['id']}", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["day"] == today and body["currency"] == "XOF"
    assert [p["id"] for p in body["payments"]] == [mine_paid["id"]]  # jamais le paiement de l'admin
    entry = body["payments"][0]
    assert entry["receipt_number"] == mine_paid["receipt_number"]
    assert (entry["student_matricule"], entry["student_first_name"], entry["student_last_name"]) == (
        ctx["student"]["matricule"],
        "Ama",
        "Elève",
    )
    assert entry["method"] == "CASH" and entry["status"] == "COMPLETED"
    assert body["total_completed"] == "15000.00"

    admin_view = (await client.get(f"/api/v1/cashier/payments?school_id={ctx['school']['id']}", headers=ctx["admin_headers"])).json()
    assert [p["id"] for p in admin_view["payments"]] == [admin_paid["id"]]

    past = (await client.get(f"/api/v1/cashier/payments?school_id={ctx['school']['id']}&day=2020-01-01", headers=headers)).json()
    assert len(past["payments"]) == 1 and past["payments"][0]["paid_at"] == "2020-01-01"


async def test_cashier_day_excludes_cancelled_from_total(client: AsyncClient) -> None:
    ctx = await _env(client, "cwdaycancel")
    payload = _payment_payload(ctx, 7000)
    payload["paid_at"] = date.today().isoformat()
    paid = (await client.post("/api/v1/payments", json=payload, headers=ctx["cashier"]["headers"])).json()
    cancel = await client.post(f"/api/v1/payments/{paid['id']}/cancel", json={"reason": "Erreur"}, headers=ctx["admin_headers"])
    assert cancel.status_code == 200
    body = (await client.get(f"/api/v1/cashier/payments?school_id={ctx['school']['id']}", headers=ctx["cashier"]["headers"])).json()
    assert body["payments"][0]["status"] == "CANCELLED"
    assert body["total_completed"] == "0"


async def test_cashier_day_isolation(client: AsyncClient) -> None:
    ctx = await _env(client, "cwdayiso")
    other_org = await _full_fee_setup(client, "cwdayisob")
    sibling = await add_school_to_organization(client, ctx["org"]["id"], "Ecole soeur", "ecole-soeur", ctx["admin_headers"])
    headers = ctx["cashier"]["headers"]
    assert (await client.get(f"/api/v1/cashier/payments?school_id={sibling['id']}", headers=headers)).status_code == 403
    assert (await client.get(f"/api/v1/cashier/payments?school_id={other_org['school']['id']}", headers=headers)).status_code == 404
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "cwdayiso.t")
    assert (
        await client.get(f"/api/v1/cashier/payments?school_id={ctx['school']['id']}", headers=teacher["headers"])
    ).status_code == 403
