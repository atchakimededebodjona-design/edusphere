"""Caisse scolaire, lot 1 — rôle CAISSIER (backend/RBAC), migration 0025.

Parent → Caissier → paiement en espèces → confirmation immédiate → reçu → solde mis à jour.
Le CAISSIER consulte la situation financière, enregistre un paiement EN ESPÈCES et consulte
paiements/reçus ; il ne configure jamais les frais, n'ajuste jamais un montant dû et n'annule
jamais un paiement (permission distincte `payments.cancel`). Aucune intégration de paiement en
ligne dans ce lot.
"""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.fees.models import Payment
from app.modules.rbac.models import (
    ALL_ROLE_CODES,
    ISOLATED_GLOBAL_ROLE_CODES,
    NON_SCHOOL_ROLE_CODES,
    PLATFORM_ROLE_CODES,
    REUSABLE_ADMIN_ROLE_CODES,
    Role,
    UserRole,
)
from tests.conftest import add_school_to_organization, assign_role
from tests.test_fees import _create_user_with_role, _full_fee_setup, _payment_payload

FORBIDDEN_CASH_ONLY = "Cashiers can only record cash payments"


async def _cashier_env(client: AsyncClient, prefix: str) -> dict:
    ctx = await _full_fee_setup(client, prefix)
    ctx["cashier"] = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "CAISSIER", f"{prefix}.cashier")
    return ctx


async def _pay(client: AsyncClient, ctx: dict, headers: dict, amount: float = 1000, method: str = "CASH"):
    payload = _payment_payload(ctx, amount)
    payload["method"] = method
    return await client.post("/api/v1/payments", json=payload, headers=headers)


async def _payment_count(student_id: str) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = (await db.execute(select(Payment.id).where(Payment.student_id == uuid.UUID(student_id)))).all()
    return len(rows)


# === A. Rôle ==========================================================================================
async def test_a_cashier_role_and_permissions_exist_after_migration() -> None:
    async with AsyncSessionLocal() as db:
        role = (await db.execute(select(Role).where(Role.code == "CAISSIER"))).scalar_one()
        assert role.name == "Caissier" and role.is_system_role is True
        perms = {
            row[0]
            for row in (
                await db.execute(
                    text(
                        "SELECT p.code FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                        "JOIN permissions p ON p.id = rp.permission_id WHERE r.code = 'CAISSIER'"
                    )
                )
            ).all()
        }
        cancel_holders = {
            row[0]
            for row in (
                await db.execute(
                    text(
                        "SELECT r.code FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                        "JOIN permissions p ON p.id = rp.permission_id WHERE p.code = 'payments.cancel'"
                    )
                )
            ).all()
        }
        descriptions = dict(
            (
                await db.execute(text("SELECT code, description FROM permissions WHERE code IN ('payments.manage', 'payments.cancel')"))
            ).all()
        )
    assert perms == {"fees.read", "payments.read", "payments.manage"}
    assert cancel_holders == {"SUPER_ADMIN", "SCHOOL_ADMIN", "DIRECTOR", "ACCOUNTANT"}
    assert descriptions == {"payments.manage": "Enregistrer des paiements", "payments.cancel": "Annuler un paiement"}


def test_a_cashier_is_a_plain_school_role() -> None:
    assert "CAISSIER" in ALL_ROLE_CODES
    for global_set in (PLATFORM_ROLE_CODES, NON_SCHOOL_ROLE_CODES, ISOLATED_GLOBAL_ROLE_CODES, REUSABLE_ADMIN_ROLE_CODES):
        assert "CAISSIER" not in global_set


async def test_a_cashier_is_created_scoped_to_one_school(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashrole")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = (
            await db.execute(
                select(UserRole, Role.code)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id == uuid.UUID(ctx["cashier"]["user"]["id"]))
            )
        ).all()
    assert [(code, str(ur.organization_id), str(ur.school_id)) for ur, code in rows] == [
        ("CAISSIER", ctx["org"]["id"], ctx["school"]["id"])
    ]
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(ctx["cashier"]["user"]["id"]))
        settings = (
            await db.execute(text("SELECT current_setting('app.is_platform_wide', true), current_setting('app.tenant_org_ids', true)"))
        ).one()
        await db.rollback()
    assert tuple(settings) == ("false", ctx["org"]["id"])  # jamais platform-wide


# === B. Autorisations =================================================================================
async def test_b_cashier_reads_summary_records_cash_and_reads_payments(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashok")
    headers = ctx["cashier"]["headers"]
    summary = await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=headers)
    assert summary.status_code == 200

    paid = await _pay(client, ctx, headers, 15000)
    assert paid.status_code == 201, paid.text
    payment = paid.json()
    assert payment["status"] == "COMPLETED" and payment["receipt_number"]
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        stored = await db.get(Payment, uuid.UUID(payment["id"]))
        assert stored is not None
        assert str(stored.recorded_by) == ctx["cashier"]["user"]["id"]  # le caissier est tracé

    listed = await client.get(f"/api/v1/payments?school_id={ctx['school']['id']}", headers=headers)
    assert listed.status_code == 200 and payment["id"] in {p["id"] for p in listed.json()}
    receipt = await client.get(f"/api/v1/payments/{payment['id']}/receipt.pdf", headers=headers)
    assert receipt.status_code == 200
    after = await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=headers)
    assert after.json() != summary.json()  # solde mis à jour


async def test_b_cashier_cannot_configure_fees_adjust_due_or_cancel(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashno")
    headers = ctx["cashier"]["headers"]
    school_id = ctx["school"]["id"]
    assert (await client.post("/api/v1/fee-categories", json={"school_id": school_id, "name": "Intrus"}, headers=headers)).status_code == 403
    schedule = {
        "school_id": school_id,
        "fee_category_id": ctx["category"]["id"],
        "academic_year_id": ctx["year"]["id"],
        "name": "Barème intrus",
        "amount": "1000",
        "scope_type": "SCHOOL",
    }
    assert (await client.post("/api/v1/fee-schedules", json=schedule, headers=headers)).status_code == 403
    generate = await client.post(f"/api/v1/fee-schedules/{ctx['schedule']['id']}/generate", headers=headers)
    assert generate.status_code == 403
    adjust = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}", json={"amount_due": "1", "note": "Intrus"}, headers=headers
    )
    assert adjust.status_code == 403
    paid = await _pay(client, ctx, headers, 2000)
    assert paid.status_code == 201
    cancel = await client.post(f"/api/v1/payments/{paid.json()['id']}/cancel", json={"reason": "Erreur"}, headers=headers)
    assert cancel.status_code == 403
    listed = await client.get(f"/api/v1/payments?school_id={school_id}", headers=ctx["admin_headers"])
    assert next(p for p in listed.json() if p["id"] == paid.json()["id"])["status"] == "COMPLETED"


async def test_b_cashier_has_no_audit_access(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashaudit")
    response = await client.get(f"/api/v1/audit-logs?school_id={ctx['school']['id']}", headers=ctx["cashier"]["headers"])
    assert response.status_code == 403


# === C. Méthode de paiement ==============================================================================
@pytest.mark.parametrize(
    ("method", "expected"),
    [("CASH", 201), ("BANK_TRANSFER", 403), ("CHEQUE", 403), ("AGENT_DEPOSIT", 403), ("OTHER", 403)],
)
async def test_c_cashier_cash_only(client: AsyncClient, method: str, expected: int) -> None:
    ctx = await _cashier_env(client, f"cashm{method[:4].lower()}")
    response = await _pay(client, ctx, ctx["cashier"]["headers"], 1000, method)
    assert response.status_code == expected, response.text
    if expected == 403:
        assert response.json()["detail"] == FORBIDDEN_CASH_ONLY
        assert await _payment_count(ctx["student"]["id"]) == 0  # aucun paiement créé


@pytest.mark.parametrize("method", ["BANK_TRANSFER", "CHEQUE", "AGENT_DEPOSIT", "OTHER"])
async def test_c_other_roles_keep_all_methods(client: AsyncClient, method: str) -> None:
    """Compatibilité : les méthodes existantes restent valides pour les rôles non caissiers."""
    ctx = await _full_fee_setup(client, f"cashlegacy{method[:4].lower()}")
    accountant = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "ACCOUNTANT", "cashlegacy.acc")
    for headers in (ctx["admin_headers"], accountant["headers"]):
        assert (await _pay(client, ctx, headers, 1000, method)).status_code == 201


async def test_c_cashier_holding_accountant_role_in_same_school_keeps_accountant_rights(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashmixed")
    await assign_role(ctx["cashier"]["user"]["id"], "ACCOUNTANT", ctx["org"]["id"], ctx["school"]["id"])
    assert (await _pay(client, ctx, ctx["cashier"]["headers"], 1000, "BANK_TRANSFER")).status_code == 201


# === D. Annulation ===========================================================================================
@pytest.mark.parametrize("role_code", ["SCHOOL_ADMIN", "DIRECTOR", "ACCOUNTANT"])
async def test_d_supervisor_roles_can_cancel(client: AsyncClient, role_code: str) -> None:
    ctx = await _cashier_env(client, f"cashcancel{role_code[:4].lower()}")
    paid = await _pay(client, ctx, ctx["cashier"]["headers"], 3000)
    assert paid.status_code == 201
    if role_code == "SCHOOL_ADMIN":
        headers = ctx["admin_headers"]
    else:
        headers = (await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], role_code, "cashcancel.sup"))["headers"]
    cancel = await client.post(f"/api/v1/payments/{paid.json()['id']}/cancel", json={"reason": "Erreur de saisie"}, headers=headers)
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"
    # COMPLETED -> CANCELLED uniquement, jamais de retour ni de réécriture.
    again = await client.post(f"/api/v1/payments/{paid.json()['id']}/cancel", json={"reason": "Encore"}, headers=headers)
    assert again.status_code == 409


async def test_d_cashier_gets_403_on_cancel(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashcancelno")
    paid = await _pay(client, ctx, ctx["admin_headers"], 3000)
    response = await client.post(f"/api/v1/payments/{paid.json()['id']}/cancel", json={"reason": "X"}, headers=ctx["cashier"]["headers"])
    assert response.status_code == 403


async def test_d_no_payment_rewrite_route_exists(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashpatch")
    paid = await _pay(client, ctx, ctx["admin_headers"], 3000)
    for method in ("PATCH", "PUT", "DELETE"):
        response = await client.request(method, f"/api/v1/payments/{paid.json()['id']}", json={"amount": "1"}, headers=ctx["admin_headers"])
        # Aucune route de réécriture d'un paiement n'existe (seules /cancel et /receipt.pdf).
        assert response.status_code in (404, 405), method
    listed = await client.get(f"/api/v1/payments?school_id={ctx['school']['id']}", headers=ctx["admin_headers"])
    stored = next(p for p in listed.json() if p["id"] == paid.json()["id"])
    assert stored["status"] == "COMPLETED" and stored["amount"] == paid.json()["amount"]


# === E. Isolation ============================================================================================
async def test_e_cashier_cannot_pay_on_sibling_school_of_same_org(client: AsyncClient) -> None:
    ctx = await _cashier_env(client, "cashsib")
    sibling = await add_school_to_organization(client, ctx["org"]["id"], "Ecole soeur", "ecole-soeur", ctx["admin_headers"])
    sibling_student = await client.post(
        "/api/v1/students",
        json={
            "school_id": sibling["id"],
            "matricule": f"S{uuid.uuid4().hex[:8]}",
            "first_name": "Kofi",
            "last_name": "Soeur",
            "date_of_birth": str(date(2015, 1, 1)),
            "sex": "M",
        },
        headers=ctx["admin_headers"],
    )
    assert sibling_student.status_code == 201, sibling_student.text
    payload = _payment_payload(ctx, 1000)
    payload["student_id"] = sibling_student.json()["id"]
    response = await client.post("/api/v1/payments", json=payload, headers=ctx["cashier"]["headers"])
    assert response.status_code == 403
    summary = await client.get(f"/api/v1/students/{sibling_student.json()['id']}/financial-summary", headers=ctx["cashier"]["headers"])
    assert summary.status_code == 403
    assert (await client.get(f"/api/v1/payments?school_id={sibling['id']}", headers=ctx["cashier"]["headers"])).status_code == 403


async def test_e_cashier_cannot_reach_another_organization(client: AsyncClient) -> None:
    ctx_a = await _cashier_env(client, "cashorga")
    ctx_b = await _full_fee_setup(client, "cashorgb")
    headers = ctx_a["cashier"]["headers"]
    payload = _payment_payload(ctx_b, 1000)
    assert (await client.post("/api/v1/payments", json=payload, headers=headers)).status_code in (403, 404)
    assert (await client.get(f"/api/v1/students/{ctx_b['student']['id']}/financial-summary", headers=headers)).status_code in (403, 404)
    assert (await client.get(f"/api/v1/payments?school_id={ctx_b['school']['id']}", headers=headers)).status_code in (403, 404)
    assert await _payment_count(ctx_b["student"]["id"]) == 0


async def test_e_rls_hides_other_organization_payments_from_cashier_session(client: AsyncClient) -> None:
    ctx_a = await _cashier_env(client, "cashrlsa")
    ctx_b = await _full_fee_setup(client, "cashrlsb")
    paid_b = await _pay(client, ctx_b, ctx_b["admin_headers"], 1000)
    paid_a = await _pay(client, ctx_a, ctx_a["cashier"]["headers"], 1000)
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(ctx_a["cashier"]["user"]["id"]))
        visible = {
            str(row[0])
            for row in (
                await db.execute(
                    select(Payment.id).where(Payment.id.in_([uuid.UUID(paid_a.json()["id"]), uuid.UUID(paid_b.json()["id"])]))
                )
            ).all()
        }
        await db.rollback()
    assert visible == {paid_a.json()["id"]}
