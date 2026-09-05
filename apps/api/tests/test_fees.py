"""Phase 19 — School Fees & Billing.

Suite organisée en sections : modèles/frais, paiements (règles/idempotence/concurrence),
sécurité (RBAC, cross-school, cross-organization, RLS brute), parent (self-scoped), reçus.
"""

import asyncio
import uuid
from datetime import date

from httpx import AsyncClient

from tests.conftest import register_school, unique_email

STANDARD_PASSWORD = "SuperSecret123"


async def _login(client: AsyncClient, email: str, password: str = STANDARD_PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _create_user_with_role(client: AsyncClient, headers_admin: dict, school_id: str, role_code: str, email_prefix: str) -> dict:
    email = unique_email(email_prefix)
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": f"{role_code} Test", "school_id": school_id, "role_code": role_code},
        headers=headers_admin,
    )
    assert response.status_code == 201, response.text
    data = response.json()
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": data["dev_reset_token"], "new_password": "OtherPass123"}
    )
    assert reset.status_code == 204
    token = await _login(client, email, "OtherPass123")
    return {"user": data["user"], "headers": {"Authorization": f"Bearer {token}"}}


async def _setup_school_context(client: AsyncClient, org_prefix: str) -> dict:
    """Organisation + école + année/niveau/classe + un élève inscrit — le minimum nécessaire pour
    exercer le module frais (pas besoin de notes/présence/bulletins ici)."""
    data = await register_school(client, org_prefix)
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    suffix = uuid.uuid4().hex[:8]

    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": f"2026-2027-{suffix}",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2027, 6, 30)),
            },
            headers=headers_admin,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": f"CE1-{suffix}"}, headers=headers_admin)
    ).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers_admin,
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": f"F{suffix}",
                "first_name": "Ama",
                "last_name": "Elève",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "F",
            },
            headers=headers_admin,
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers_admin,
    )

    return {
        "org": data["organization"],
        "school": data["school"],
        "admin_headers": headers_admin,
        "admin_user_id": data["user"]["id"],
        "year": year,
        "level": level,
        "class": school_class,
        "student": student,
    }


async def _create_fee_schedule(client: AsyncClient, headers_admin: dict, ctx: dict, amount: float = 50000, **overrides) -> dict:
    payload = {
        "school_id": ctx["school"]["id"],
        "fee_category_id": ctx["category"]["id"],
        "academic_year_id": ctx["year"]["id"],
        "name": "Frais de scolarité",
        "amount": str(amount),
        "scope_type": "SCHOOL",
    }
    payload.update(overrides)
    response = await client.post("/api/v1/fee-schedules", json=payload, headers=headers_admin)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_category(client: AsyncClient, headers_admin: dict, school_id: str, name: str = "Scolarité") -> dict:
    response = await client.post("/api/v1/fee-categories", json={"school_id": school_id, "name": name}, headers=headers_admin)
    assert response.status_code == 201, response.text
    return response.json()


async def _full_fee_setup(client: AsyncClient, org_prefix: str) -> dict:
    ctx = await _setup_school_context(client, org_prefix)
    ctx["category"] = await _create_category(client, ctx["admin_headers"], ctx["school"]["id"])
    ctx["schedule"] = await _create_fee_schedule(client, ctx["admin_headers"], ctx)
    generate = await client.post(f"/api/v1/fee-schedules/{ctx['schedule']['id']}/generate", headers=ctx["admin_headers"])
    assert generate.status_code == 200, generate.text
    assert generate.json()["created_count"] == 1
    summary = await client.get(
        f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=ctx["admin_headers"]
    )
    assert summary.status_code == 200, summary.text
    ctx["student_fee"] = summary.json()["fees"][0]
    return ctx


def _payment_payload(ctx: dict, amount: float, idempotency_key: str | None = None) -> dict:
    return {
        "student_id": ctx["student"]["id"],
        "amount": str(amount),
        "method": "CASH",
        "paid_at": str(date(2026, 10, 1)),
        "reference": None,
        "idempotency_key": idempotency_key or uuid.uuid4().hex,
        "allocations": [{"student_fee_id": ctx["student_fee"]["id"], "amount": str(amount)}],
    }


# --- Modèles / frais -----------------------------------------------------------------------
async def test_create_fee_category_and_reject_duplicate(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "feecat")
    first = await _create_category(client, ctx["admin_headers"], ctx["school"]["id"], "Cantine")
    assert first["name"] == "Cantine"

    duplicate = await client.post(
        "/api/v1/fee-categories", json={"school_id": ctx["school"]["id"], "name": "Cantine"}, headers=ctx["admin_headers"]
    )
    assert duplicate.status_code == 409


async def test_fee_schedule_class_scope_requires_class_id(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "feescope")
    ctx["category"] = await _create_category(client, ctx["admin_headers"], ctx["school"]["id"])

    response = await client.post(
        "/api/v1/fee-schedules",
        json={
            "school_id": ctx["school"]["id"],
            "fee_category_id": ctx["category"]["id"],
            "academic_year_id": ctx["year"]["id"],
            "name": "Frais de classe",
            "amount": "1000",
            "scope_type": "CLASS",
        },
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 400


async def test_generate_student_fees_is_idempotent(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feegen")
    second = await client.post(f"/api/v1/fee-schedules/{ctx['schedule']['id']}/generate", headers=ctx["admin_headers"])
    assert second.status_code == 200
    assert second.json() == {"created_count": 0, "skipped_existing_count": 1}


async def test_financial_summary_reflects_amount_due(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feesummary")
    assert ctx["student_fee"]["amount_due"] == "50000.00"
    assert ctx["student_fee"]["status"] == "PENDING"
    assert ctx["student_fee"]["balance"] == "50000.00"


# --- Paiements : règles métier -------------------------------------------------------------
async def test_full_payment_marks_fee_as_paid_and_produces_receipt(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feepayfull")

    response = await client.post("/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"])
    assert response.status_code == 201, response.text
    payment = response.json()
    assert payment["status"] == "COMPLETED"
    assert payment["receipt_number"].startswith("RCPT-")

    summary = await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=ctx["admin_headers"])
    fee = summary.json()["fees"][0]
    assert fee["status"] == "PAID"
    assert fee["balance"] == "0.00"

    receipt = await client.get(f"/api/v1/payments/{payment['id']}/receipt.pdf", headers=ctx["admin_headers"])
    assert receipt.status_code == 200
    assert receipt.headers["content-type"] == "application/pdf"
    assert receipt.content[:4] == b"%PDF"


async def test_partial_payment_marks_fee_as_partially_paid(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feepaypartial")

    response = await client.post("/api/v1/payments", json=_payment_payload(ctx, 20000), headers=ctx["admin_headers"])
    assert response.status_code == 201, response.text

    summary = await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=ctx["admin_headers"])
    fee = summary.json()["fees"][0]
    assert fee["status"] == "PARTIALLY_PAID"
    assert fee["balance"] == "30000.00"


async def test_allocation_sum_must_equal_payment_amount(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feemismatch")
    payload = _payment_payload(ctx, 20000)
    payload["allocations"][0]["amount"] = "10000"  # ne correspond pas au montant du paiement

    response = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 422


async def test_payment_cannot_exceed_remaining_balance(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feeoverpay")

    response = await client.post("/api/v1/payments", json=_payment_payload(ctx, 60000), headers=ctx["admin_headers"])
    assert response.status_code == 422


async def test_negative_or_zero_payment_amount_rejected(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feenegative")
    payload = _payment_payload(ctx, 0)
    payload["allocations"][0]["amount"] = "0"

    response = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 422  # validation Pydantic (Field(gt=0))


async def test_payment_on_nonexistent_fee_returns_404(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feenoexist")
    payload = _payment_payload(ctx, 1000)
    payload["allocations"][0]["student_fee_id"] = str(uuid.uuid4())

    response = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 404


# --- Idempotence et concurrence -------------------------------------------------------------
async def test_duplicate_idempotency_key_does_not_create_a_second_payment(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feeidem")
    payload = _payment_payload(ctx, 20000, idempotency_key="fixed-key-1")

    first = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert first.status_code == 201
    second = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    listing = await client.get(f"/api/v1/payments?school_id={ctx['school']['id']}", headers=ctx["admin_headers"])
    assert len(listing.json()) == 1


async def test_concurrent_double_submission_creates_only_one_payment(client: AsyncClient) -> None:
    """Deux requêtes réellement concurrentes avec la même idempotency_key ne doivent produire
    qu'un seul paiement — le scénario de double-clic/double-soumission (Phase 19 §20)."""
    ctx = await _full_fee_setup(client, "feeconcurrent")
    payload = _payment_payload(ctx, 20000, idempotency_key="concurrent-key-1")

    results = await asyncio.gather(
        client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"]),
        client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"]),
    )
    assert all(r.status_code == 201 for r in results)
    assert results[0].json()["id"] == results[1].json()["id"]

    listing = await client.get(f"/api/v1/payments?school_id={ctx['school']['id']}", headers=ctx["admin_headers"])
    assert len(listing.json()) == 1


async def test_concurrent_payments_on_same_fee_never_overallocate(client: AsyncClient) -> None:
    """Deux paiements DIFFÉRENTS (clés d'idempotence distinctes) tentant chacun d'allouer 30000
    sur une obligation de 50000 en même temps : un seul doit réussir, l'autre doit être rejeté —
    jamais les deux (ce qui produirait un solde négatif)."""
    ctx = await _full_fee_setup(client, "feeraceoverlap")
    payload_a = _payment_payload(ctx, 30000)
    payload_b = _payment_payload(ctx, 30000)

    results = await asyncio.gather(
        client.post("/api/v1/payments", json=payload_a, headers=ctx["admin_headers"]),
        client.post("/api/v1/payments", json=payload_b, headers=ctx["admin_headers"]),
    )
    statuses = sorted(r.status_code for r in results)
    assert statuses == [201, 422], [r.text for r in results]

    summary = await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=ctx["admin_headers"])
    fee = summary.json()["fees"][0]
    assert fee["amount_paid"] == "30000.00"
    assert fee["balance"] == "20000.00"


# --- Annulation ------------------------------------------------------------------------------
async def test_cancel_payment_reverts_fee_status_and_balance(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feecancel")
    payment = (await client.post("/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"])).json()

    cancel = await client.post(
        f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "Erreur de saisie"}, headers=ctx["admin_headers"]
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"

    summary = await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=ctx["admin_headers"])
    fee = summary.json()["fees"][0]
    assert fee["status"] == "PENDING"
    assert fee["balance"] == "50000.00"


async def test_cancel_already_cancelled_payment_rejected(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feedoublecancel")
    payment = (await client.post("/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"])).json()
    await client.post(f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "x"}, headers=ctx["admin_headers"])

    second = await client.post(f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "x"}, headers=ctx["admin_headers"])
    assert second.status_code == 409


async def test_payment_amount_and_method_are_not_editable(client: AsyncClient) -> None:
    """Aucun endpoint PATCH n'existe sur un paiement — seule /cancel est exposée (immutabilité
    par absence de surface API, voir PHASE_19_DISCOVERY.md §19)."""
    ctx = await _full_fee_setup(client, "feeimmutable")
    payment = (await client.post("/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"])).json()

    response = await client.patch(f"/api/v1/payments/{payment['id']}", json={"amount": "1"}, headers=ctx["admin_headers"])
    assert response.status_code in (404, 405)


# --- RBAC ------------------------------------------------------------------------------------
async def test_teacher_cannot_manage_fees_or_payments(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feeteacher")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "teacher.fees")

    create_category = await client.post(
        "/api/v1/fee-categories", json={"school_id": ctx["school"]["id"], "name": "Autre"}, headers=teacher["headers"]
    )
    assert create_category.status_code == 403

    create_payment = await client.post("/api/v1/payments", json=_payment_payload(ctx, 1000), headers=teacher["headers"])
    assert create_payment.status_code == 403


async def test_accountant_can_record_payments_but_not_configure_fees(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feeaccountant")
    accountant = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "ACCOUNTANT", "accountant.fees")

    forbidden = await client.post(
        "/api/v1/fee-categories", json={"school_id": ctx["school"]["id"], "name": "Autre"}, headers=accountant["headers"]
    )
    assert forbidden.status_code == 403

    allowed = await client.post("/api/v1/payments", json=_payment_payload(ctx, 10000), headers=accountant["headers"])
    assert allowed.status_code == 201, allowed.text


# --- Isolation cross-organization / cross-school ---------------------------------------------
async def test_admin_a_cannot_record_payment_for_student_of_organization_b(client: AsyncClient) -> None:
    ctx_a = await _full_fee_setup(client, "feecrossa")
    ctx_b = await _full_fee_setup(client, "feecrossb")

    forged = dict(_payment_payload(ctx_b, 1000))
    forged["allocations"][0]["student_fee_id"] = ctx_b["student_fee"]["id"]
    response = await client.post("/api/v1/payments", json=forged, headers=ctx_a["admin_headers"])
    assert response.status_code == 404  # RLS rend l'élève de B invisible sous le contexte de A


async def test_admin_a_cannot_read_payments_of_organization_b(client: AsyncClient) -> None:
    ctx_a = await _full_fee_setup(client, "feecrossreada")
    ctx_b = await _full_fee_setup(client, "feecrossreadb")
    await client.post("/api/v1/payments", json=_payment_payload(ctx_b, 10000), headers=ctx_b["admin_headers"])

    response = await client.get(f"/api/v1/payments?school_id={ctx_b['school']['id']}", headers=ctx_a["admin_headers"])
    # RLS (schools_tenant_isolation) rend la ligne school de B invisible sous le contexte de A
    # avant même la vérification de permission applicative — _get_school_or_404 lève donc 404.
    assert response.status_code == 404


async def test_row_level_security_hides_payment_row_even_bypassing_app_check(client: AsyncClient) -> None:
    """Même preuve que test_tenant_isolation.py::test_row_level_security_hides_school_row_...
    mais pour `payments` : la garantie RLS elle-même, pas seulement le contrôle applicatif."""
    from sqlalchemy import select

    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.fees.models import Payment

    ctx_a = await _full_fee_setup(client, "feerlsa")
    ctx_b = await _full_fee_setup(client, "feerlsb")
    payment_b = (
        await client.post("/api/v1/payments", json=_payment_payload(ctx_b, 10000), headers=ctx_b["admin_headers"])
    ).json()

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(ctx_a["admin_user_id"]))
        result = await db.execute(select(Payment).where(Payment.id == uuid.UUID(payment_b["id"])))
        assert result.scalar_one_or_none() is None
        await db.rollback()


# --- Parent (lecture seule, self-scoped) -------------------------------------------------------
async def _link_parent(client: AsyncClient, ctx: dict, email_prefix: str) -> dict:
    email = unique_email(email_prefix)
    parent = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Parent Test", "school_id": ctx["school"]["id"], "role_code": "PARENT"},
        headers=ctx["admin_headers"],
    )
    assert parent.status_code == 201, parent.text
    parent_data = parent.json()
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": parent_data["dev_reset_token"], "new_password": "ParentPass123"}
    )
    assert reset.status_code == 204

    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": ctx["school"]["id"], "full_name": "Tuteur Test", "relationship_type": "father"},
            headers=ctx["admin_headers"],
        )
    ).json()
    link = await client.patch(
        f"/api/v1/guardians/{guardian['id']}", json={"user_id": parent_data["user"]["id"]}, headers=ctx["admin_headers"]
    )
    assert link.status_code == 200, link.text
    attach = await client.post(
        f"/api/v1/students/{ctx['student']['id']}/guardians", json={"guardian_id": guardian["id"]}, headers=ctx["admin_headers"]
    )
    assert attach.status_code == 201, attach.text

    token = await _login(client, email, "ParentPass123")
    return {"headers": {"Authorization": f"Bearer {token}"}}


async def test_parent_can_read_own_child_fees_and_receipt(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "feeparentok")
    payment = (await client.post("/api/v1/payments", json=_payment_payload(ctx, 50000), headers=ctx["admin_headers"])).json()
    parent = await _link_parent(client, ctx, "parent.feesok")

    summary = await client.get(f"/api/v1/parent/children/{ctx['student']['id']}/fees", headers=parent["headers"])
    assert summary.status_code == 200, summary.text
    assert summary.json()["balance"] == "0.00"

    receipt = await client.get(
        f"/api/v1/parent/children/{ctx['student']['id']}/payments/{payment['id']}/receipt.pdf", headers=parent["headers"]
    )
    assert receipt.status_code == 200
    assert receipt.headers["content-type"] == "application/pdf"


async def test_parent_cannot_read_fees_of_another_parents_child(client: AsyncClient) -> None:
    ctx_a = await _full_fee_setup(client, "feeparentcrossa")
    ctx_b = await _full_fee_setup(client, "feeparentcrossb")
    parent_a = await _link_parent(client, ctx_a, "parent.feescrossa")

    response = await client.get(f"/api/v1/parent/children/{ctx_b['student']['id']}/fees", headers=parent_a["headers"])
    assert response.status_code == 404


async def test_parent_cannot_download_receipt_of_another_child(client: AsyncClient) -> None:
    ctx_a = await _full_fee_setup(client, "feeparentrcpta")
    ctx_b = await _full_fee_setup(client, "feeparentrcptb")
    payment_b = (
        await client.post("/api/v1/payments", json=_payment_payload(ctx_b, 50000), headers=ctx_b["admin_headers"])
    ).json()
    parent_a = await _link_parent(client, ctx_a, "parent.feercpta")

    response = await client.get(
        f"/api/v1/parent/children/{ctx_b['student']['id']}/payments/{payment_b['id']}/receipt.pdf",
        headers=parent_a["headers"],
    )
    assert response.status_code == 404


async def test_parent_cannot_create_payment(client: AsyncClient) -> None:
    """Aucune route de paiement n'existe sous /parent/... — vérifie qu'un parent ne peut pas
    utiliser l'endpoint admin non plus (aucune permission RBAC ne lui est jamais accordée)."""
    ctx = await _full_fee_setup(client, "feeparentnowrite")
    parent = await _link_parent(client, ctx, "parent.feesnowrite")

    response = await client.post("/api/v1/payments", json=_payment_payload(ctx, 1000), headers=parent["headers"])
    assert response.status_code == 403
