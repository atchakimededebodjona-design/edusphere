"""PR #14 — journal d'audit administratif.

Vérifie que chaque action sensible instrumentée (annulation de paiement, ajustement de frais,
changement de rôle/statut utilisateur, publication de bulletin, confirmation réelle de promotion/
affectation en masse) produit EXACTEMENT une entrée d'audit, jamais en dry_run, jamais en cas
d'échec de validation avant mutation, jamais en double sur une simple répétition d'un appel déjà
traité — et que GET /audit-logs respecte RBAC (audit.read) et l'isolation tenant (école/
organisation).
"""

import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.fees.models import StudentFee
from app.modules.users.models import User
from tests.conftest import create_platform_admin, register_school, unique_email

STANDARD_PASSWORD = "SuperSecret123"


async def _login(client: AsyncClient, email: str, password: str = STANDARD_PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _headers(client: AsyncClient, email: str, password: str = STANDARD_PASSWORD) -> dict:
    return {"Authorization": f"Bearer {await _login(client, email, password)}"}


async def _create_user_with_role(client: AsyncClient, headers_admin: dict, school_id: str, role_code: str, prefix: str) -> dict:
    email = unique_email(prefix)
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
    return {"user": data["user"], "headers": await _headers(client, email, "OtherPass123")}


async def _setup_school_context(client: AsyncClient, prefix: str) -> dict:
    """Organisation + école + année/niveau/classe + un élève inscrit — le minimum commun à tous
    les scénarios de ce fichier (frais, bulletins, promotion, affectation)."""
    data = await register_school(client, prefix)
    headers_admin = await _headers(client, data["user"]["email"])
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


async def _full_fee_setup(client: AsyncClient, prefix: str) -> dict:
    ctx = await _setup_school_context(client, prefix)
    school_id = ctx["school"]["id"]
    category = (
        await client.post("/api/v1/fee-categories", json={"school_id": school_id, "name": "Scolarité"}, headers=ctx["admin_headers"])
    ).json()
    schedule = (
        await client.post(
            "/api/v1/fee-schedules",
            json={
                "school_id": school_id,
                "fee_category_id": category["id"],
                "academic_year_id": ctx["year"]["id"],
                "name": "Frais de scolarité",
                "amount": "50000",
                "scope_type": "SCHOOL",
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    generate = await client.post(f"/api/v1/fee-schedules/{schedule['id']}/generate", headers=ctx["admin_headers"])
    assert generate.status_code == 200, generate.text
    summary = await client.get(f"/api/v1/students/{ctx['student']['id']}/financial-summary", headers=ctx["admin_headers"])
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


async def _audit_logs(client: AsyncClient, headers: dict, school_id: str, **filters) -> dict:
    params = {"school_id": school_id, **filters}
    response = await client.get("/api/v1/audit-logs", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _set_student_fee_cancelled(student_fee_id: str) -> None:
    """Il n'existe aucun endpoint pour annuler directement un StudentFee (seul un Payment peut
    être annulé) — valeur de statut atteinte uniquement par écriture directe, pour exercer le
    garde `if student_fee.status == "CANCELLED"` déjà existant de `update_student_fee`."""
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(update(StudentFee).where(StudentFee.id == uuid.UUID(student_fee_id)).values(status="CANCELLED"))
        await db.commit()


async def _delete_user(user_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        user = await db.get(User, uuid.UUID(user_id))
        assert user is not None
        await db.delete(user)
        await db.commit()


# --- 1. Annulation de paiement ------------------------------------------------------------------
async def test_audit_log_created_on_payment_cancellation(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "auditpaycancel")
    payment = (
        await client.post("/api/v1/payments", json=_payment_payload(ctx, 20000), headers=ctx["admin_headers"])
    ).json()

    cancel = await client.post(
        f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "Erreur de saisie"}, headers=ctx["admin_headers"]
    )
    assert cancel.status_code == 200, cancel.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="payment.cancelled")
    assert logs["total"] == 1
    entry = logs["items"][0]
    assert entry["entity_type"] == "Payment"
    assert entry["entity_id"] == payment["id"]
    assert "Erreur de saisie" in entry["summary"]
    assert entry["metadata"]["reason"] == "Erreur de saisie"


# --- 2. Ajustement du montant dû -----------------------------------------------------------------
async def test_audit_log_created_on_fee_amount_adjustment(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "auditfeeadjust")
    response = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}",
        json={"amount_due": "45000", "note": "Remise exceptionnelle"},
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="student_fee.amount_due_adjusted")
    assert logs["total"] == 1
    entry = logs["items"][0]
    assert entry["entity_type"] == "StudentFee"
    assert entry["metadata"]["previous_amount_due"] == "50000.00"
    assert entry["metadata"]["new_amount_due"] == "45000"


async def test_no_fee_amount_audit_on_due_date_only_change(client: AsyncClient) -> None:
    """Ajuster seulement la date d'échéance (jamais le montant) n'est pas l'opération sensible
    visée par ce PR — aucune entrée ne doit être créée."""
    ctx = await _full_fee_setup(client, "auditfeeduedate")
    response = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}",
        json={"due_date": str(date(2027, 1, 15))},
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"])
    assert logs["total"] == 0


async def test_no_audit_on_rejected_fee_adjustment(client: AsyncClient) -> None:
    """Échec de validation (frais déjà annulé) AVANT la ligne d'audit -> jamais de faux succès."""
    ctx = await _full_fee_setup(client, "auditfeerejected")
    await _set_student_fee_cancelled(ctx["student_fee"]["id"])

    response = await client.patch(
        f"/api/v1/student-fees/{ctx['student_fee']['id']}",
        json={"amount_due": "1000", "note": "Tentative sur frais annulé"},
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 409, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"])
    assert logs["total"] == 0


# --- 3/4. Changement de rôle / statut utilisateur ------------------------------------------------
async def test_audit_log_created_on_role_change(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditrolechange")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "auditrolechange.teacher")

    response = await client.patch(
        f"/api/v1/users/{teacher['user']['id']}",
        json={"school_id": ctx["school"]["id"], "role_code": "STAFF"},
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="user.role_changed")
    assert logs["total"] == 1
    entry = logs["items"][0]
    assert entry["entity_type"] == "User"
    assert entry["entity_id"] == teacher["user"]["id"]
    assert entry["metadata"]["previous_role_codes"] == ["TEACHER"]
    assert entry["metadata"]["new_role_code"] == "STAFF"


async def test_audit_log_created_on_status_change(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditstatuschange")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "auditstatuschange.teacher")

    response = await client.patch(
        f"/api/v1/users/{teacher['user']['id']}",
        json={"school_id": ctx["school"]["id"], "is_active": False},
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="user.status_changed")
    assert logs["total"] == 1
    entry = logs["items"][0]
    assert entry["metadata"]["previous_is_active"] is True
    assert entry["metadata"]["new_is_active"] is False


async def test_audit_log_created_twice_when_role_and_status_change_together(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditbothchange")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "auditbothchange.teacher")

    response = await client.patch(
        f"/api/v1/users/{teacher['user']['id']}",
        json={"school_id": ctx["school"]["id"], "role_code": "STAFF", "is_active": False},
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"])
    actions = sorted(item["action"] for item in logs["items"])
    assert actions == ["user.role_changed", "user.status_changed"]


# --- 5. Publication de bulletin -------------------------------------------------------------------
MINIMAL_TEMPLATE = """
<html><body>
<p>{{ student.first_name }} {{ student.last_name }} - {{ general_average }}</p>
<img src="{{ qr_code_data_uri }}" />
</body></html>
"""


async def _setup_graded_class(client: AsyncClient, headers: dict, school_id: str, ctx: dict) -> dict:
    term = (
        await client.post(
            "/api/v1/academic-terms",
            json={
                "academic_year_id": ctx["year"]["id"],
                "name": "Trimestre 1",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2026, 12, 20)),
            },
            headers=headers,
        )
    ).json()
    subject = (await client.post("/api/v1/subjects", json={"school_id": school_id, "name": "Mathématiques"}, headers=headers)).json()
    class_subject = (
        await client.post(
            f"/api/v1/classes/{ctx['class']['id']}/subjects", json={"subject_id": subject["id"], "coefficient": 1}, headers=headers
        )
    ).json()
    assessment_type = (
        await client.post("/api/v1/assessment-types", json={"school_id": school_id, "name": "Devoir"}, headers=headers)
    ).json()
    assessment = (
        await client.post(
            "/api/v1/assessments",
            json={
                "class_subject_id": class_subject["id"],
                "academic_term_id": term["id"],
                "assessment_type_id": assessment_type["id"],
                "name": "Devoir 1",
                "assessment_date": str(date(2026, 10, 1)),
            },
            headers=headers,
        )
    ).json()
    await client.post(
        "/api/v1/results",
        json={"assessment_id": assessment["id"], "results": [{"student_id": ctx["student"]["id"], "score": 15}]},
        headers=headers,
    )
    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": school_id, "name": "Standard", "html_content": MINIMAL_TEMPLATE},
            headers=headers,
        )
    ).json()
    return {"term": term, "template": template}


async def test_audit_log_created_on_report_card_publish(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditrcpublish")
    rc_ctx = await _setup_graded_class(client, ctx["admin_headers"], ctx["school"]["id"], ctx)

    generate = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": ctx["class"]["id"], "academic_term_id": rc_ctx["term"]["id"], "template_id": rc_ctx["template"]["id"]},
        headers=ctx["admin_headers"],
    )
    assert generate.status_code == 200, generate.text
    report_card = generate.json()[0]

    publish = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["admin_headers"])
    assert publish.status_code == 200, publish.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="report_card.published")
    assert logs["total"] == 1
    assert logs["items"][0]["entity_id"] == report_card["id"]


# --- 6/8. Promotion en masse (réel vs dry_run) -----------------------------------------------------
async def test_audit_log_created_on_real_bulk_promotion(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditpromoreal")
    target_year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": ctx["school"]["id"],
                "name": "2027-2028",
                "start_date": str(date(2027, 9, 1)),
                "end_date": str(date(2028, 6, 30)),
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    target_level = (
        await client.post(
            "/api/v1/education-levels", json={"school_id": ctx["school"]["id"], "name": f"CE2-{uuid.uuid4().hex[:8]}"},
            headers=ctx["admin_headers"],
        )
    ).json()
    target_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": target_year["id"], "education_level_id": target_level["id"], "name": "B"},
            headers=ctx["admin_headers"],
        )
    ).json()

    payload = {
        "source_academic_year_id": ctx["year"]["id"],
        "target_academic_year_id": target_year["id"],
        "class_mappings": [{"source_class_id": ctx["class"]["id"], "target_class_id": target_class["id"]}],
        "exit_dispositions": [],
        "student_ids": [ctx["student"]["id"]],
        "enrollment_date": "2027-09-01",
    }
    response = await client.post("/api/v1/students/bulk-promotion?dry_run=false", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="students.bulk_promoted")
    assert logs["total"] == 1
    assert logs["items"][0]["metadata"]["promoted_count"] == 1


async def test_no_audit_log_on_dry_run_promotion(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditpromodry")
    target_year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": ctx["school"]["id"],
                "name": "2027-2028",
                "start_date": str(date(2027, 9, 1)),
                "end_date": str(date(2028, 6, 30)),
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    target_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": target_year["id"], "education_level_id": ctx["level"]["id"], "name": "B"},
            headers=ctx["admin_headers"],
        )
    ).json()

    payload = {
        "source_academic_year_id": ctx["year"]["id"],
        "target_academic_year_id": target_year["id"],
        "class_mappings": [{"source_class_id": ctx["class"]["id"], "target_class_id": target_class["id"]}],
        "exit_dispositions": [],
        "student_ids": [ctx["student"]["id"]],
        "enrollment_date": "2027-09-01",
    }
    response = await client.post("/api/v1/students/bulk-promotion?dry_run=true", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"])
    assert logs["total"] == 0


async def test_no_audit_on_blocked_promotion_capacity(client: AsyncClient) -> None:
    """Capacité insuffisante -> 409, bloquant AVANT toute mutation -> aucun audit."""
    ctx = await _setup_school_context(client, "auditpromoblocked")
    target_year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": ctx["school"]["id"],
                "name": "2027-2028",
                "start_date": str(date(2027, 9, 1)),
                "end_date": str(date(2028, 6, 30)),
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    target_class = (
        await client.post(
            "/api/v1/classes",
            json={
                "academic_year_id": target_year["id"], "education_level_id": ctx["level"]["id"], "name": "B", "capacity": 0,
            },
            headers=ctx["admin_headers"],
        )
    ).json()

    payload = {
        "source_academic_year_id": ctx["year"]["id"],
        "target_academic_year_id": target_year["id"],
        "class_mappings": [{"source_class_id": ctx["class"]["id"], "target_class_id": target_class["id"]}],
        "exit_dispositions": [],
        "student_ids": [ctx["student"]["id"]],
        "enrollment_date": "2027-09-01",
    }
    response = await client.post("/api/v1/students/bulk-promotion?dry_run=false", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 409, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"])
    assert logs["total"] == 0


# --- 7/8. Affectation en masse (réel vs dry_run) ---------------------------------------------------
async def test_audit_log_created_on_real_bulk_assignment(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditassignreal")
    unassigned_student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": ctx["school"]["id"],
                "matricule": f"G{uuid.uuid4().hex[:8]}",
                "first_name": "Kofi",
                "last_name": "Elève",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "M",
            },
            headers=ctx["admin_headers"],
        )
    ).json()

    payload = {
        "student_ids": [unassigned_student["id"]],
        "academic_year_id": ctx["year"]["id"],
        "class_id": ctx["class"]["id"],
        "enrollment_date": "2026-09-01",
    }
    response = await client.post("/api/v1/students/bulk-enrollment?dry_run=false", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="students.bulk_assigned")
    assert logs["total"] == 1
    assert logs["items"][0]["entity_id"] == ctx["class"]["id"]
    assert logs["items"][0]["metadata"]["created_count"] == 1


async def test_no_audit_log_on_dry_run_assignment(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditassigndry")
    payload = {
        "student_ids": [ctx["student"]["id"]],
        "academic_year_id": ctx["year"]["id"],
        "class_id": ctx["class"]["id"],
        "enrollment_date": "2026-09-01",
    }
    response = await client.post("/api/v1/students/bulk-enrollment?dry_run=true", json=payload, headers=ctx["admin_headers"])
    assert response.status_code == 200, response.text

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"])
    assert logs["total"] == 0


# --- 9. RBAC ---------------------------------------------------------------------------------------
@pytest.mark.parametrize("role_code", ["TEACHER", "STAFF", "ACCOUNTANT"])
async def test_rbac_denies_non_supervisory_roles(client: AsyncClient, role_code: str) -> None:
    ctx = await _setup_school_context(client, f"auditrbac{role_code.lower()}")
    member = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], role_code, f"auditrbac{role_code.lower()}.m")

    response = await client.get("/api/v1/audit-logs", params={"school_id": ctx["school"]["id"]}, headers=member["headers"])
    assert response.status_code == 403, response.text


@pytest.mark.parametrize("role_code", ["SCHOOL_ADMIN", "DIRECTOR"])
async def test_rbac_allows_supervisory_roles(client: AsyncClient, role_code: str) -> None:
    prefix = f"auditrbacok{role_code.lower().replace('_', '')}"
    ctx = await _setup_school_context(client, prefix)
    if role_code == "SCHOOL_ADMIN":
        headers = ctx["admin_headers"]
    else:
        member = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], role_code, f"{prefix}.m")
        headers = member["headers"]

    response = await client.get("/api/v1/audit-logs", params={"school_id": ctx["school"]["id"]}, headers=headers)
    assert response.status_code == 200, response.text


# --- 10/11. Isolation tenant -------------------------------------------------------------------------
async def test_tenant_isolation_across_organizations(client: AsyncClient) -> None:
    ctx_a = await _full_fee_setup(client, "auditisoorga")
    ctx_b = await _full_fee_setup(client, "auditisoorgb")

    payment_a = (await client.post("/api/v1/payments", json=_payment_payload(ctx_a, 10000), headers=ctx_a["admin_headers"])).json()
    await client.post(f"/api/v1/payments/{payment_a['id']}/cancel", json={"reason": "a"}, headers=ctx_a["admin_headers"])
    payment_b = (await client.post("/api/v1/payments", json=_payment_payload(ctx_b, 10000), headers=ctx_b["admin_headers"])).json()
    await client.post(f"/api/v1/payments/{payment_b['id']}/cancel", json={"reason": "b"}, headers=ctx_b["admin_headers"])

    # L'admin de l'organisation A ne voit jamais les logs de l'école de l'organisation B — RLS
    # rend la ligne `schools` elle-même invisible avant même le contrôle de permission.
    cross_org_attempt = await client.get(
        "/api/v1/audit-logs", params={"school_id": ctx_b["school"]["id"]}, headers=ctx_a["admin_headers"]
    )
    assert cross_org_attempt.status_code == 404

    logs_a = await _audit_logs(client, ctx_a["admin_headers"], ctx_a["school"]["id"])
    assert logs_a["total"] == 1
    assert logs_a["items"][0]["entity_id"] == payment_a["id"]


async def test_school_level_isolation_via_platform_account(client: AsyncClient) -> None:
    """Même en bypass RLS total (compte plateforme), le filtre `school_id` de l'endpoint isole
    strictement les journaux de deux écoles — jamais une fuite par simple absence de filtre."""
    ctx_a = await _full_fee_setup(client, "auditisoschoola")
    ctx_b = await _full_fee_setup(client, "auditisoschoolb")

    payment_a = (await client.post("/api/v1/payments", json=_payment_payload(ctx_a, 10000), headers=ctx_a["admin_headers"])).json()
    await client.post(f"/api/v1/payments/{payment_a['id']}/cancel", json={"reason": "a"}, headers=ctx_a["admin_headers"])

    platform_admin = await create_platform_admin(client, "auditplatform")
    platform_headers = {"Authorization": f"Bearer {platform_admin['tokens']['access_token']}"}

    logs_school_a = await _audit_logs(client, platform_headers, ctx_a["school"]["id"])
    assert logs_school_a["total"] == 1
    logs_school_b = await _audit_logs(client, platform_headers, ctx_b["school"]["id"])
    assert logs_school_b["total"] == 0


# --- 12. Acteur supprimé -----------------------------------------------------------------------------
async def test_actor_deleted_keeps_audit_log_with_null_actor(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "auditactordeleted")
    accountant = await _create_user_with_role(
        client, ctx["admin_headers"], ctx["school"]["id"], "ACCOUNTANT", "auditactordeleted.acct"
    )
    payment = (
        await client.post("/api/v1/payments", json=_payment_payload(ctx, 10000), headers=accountant["headers"])
    ).json()
    cancel = await client.post(
        f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "test suppression acteur"}, headers=accountant["headers"]
    )
    assert cancel.status_code == 200, cancel.text

    accountant_email = accountant["user"]["email"]
    await _delete_user(accountant["user"]["id"])

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="payment.cancelled")
    assert logs["total"] == 1
    entry = logs["items"][0]
    assert entry["actor_user_id"] is None
    assert entry["actor_email"] == accountant_email


# --- 13. Absence de données sensibles -----------------------------------------------------------------
async def test_metadata_never_contains_sensitive_fields(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "auditnosensitive")
    payment = (await client.post("/api/v1/payments", json=_payment_payload(ctx, 10000), headers=ctx["admin_headers"])).json()
    await client.post(f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "r"}, headers=ctx["admin_headers"])

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"])
    forbidden_substrings = ("password", "hashed_password", "token", "secret", "hash")
    for entry in logs["items"]:
        metadata_text = str(entry["metadata"]).lower()
        for forbidden in forbidden_substrings:
            assert forbidden not in metadata_text


# --- 14. Pas de doublon sur retry (annulation déjà traitée) --------------------------------------------
async def test_no_duplicate_audit_on_retry_of_already_handled_action(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "auditretry")
    payment = (await client.post("/api/v1/payments", json=_payment_payload(ctx, 10000), headers=ctx["admin_headers"])).json()

    first = await client.post(f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "r"}, headers=ctx["admin_headers"])
    assert first.status_code == 200

    # Un retry réseau du même appel (ou un second clic) retombe sur le garde déjà existant
    # (`payment.status != "COMPLETED"`) AVANT la ligne d'audit — jamais un second enregistrement.
    second = await client.post(f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "r"}, headers=ctx["admin_headers"])
    assert second.status_code == 409

    logs = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="payment.cancelled")
    assert logs["total"] == 1


# --- 15/16. Pagination et filtres ----------------------------------------------------------------------
async def test_pagination(client: AsyncClient) -> None:
    ctx = await _setup_school_context(client, "auditpagination")
    for i in range(3):
        teacher = await _create_user_with_role(
            client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", f"auditpagination.t{i}"
        )
        await client.patch(
            f"/api/v1/users/{teacher['user']['id']}",
            json={"school_id": ctx["school"]["id"], "is_active": False},
            headers=ctx["admin_headers"],
        )

    page1 = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], page=1, page_size=2)
    assert page1["total"] == 3
    assert page1["total_pages"] == 2
    assert len(page1["items"]) == 2

    page2 = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], page=2, page_size=2)
    assert len(page2["items"]) == 1


async def test_filters_by_action_and_entity_type(client: AsyncClient) -> None:
    ctx = await _full_fee_setup(client, "auditfilters")
    payment = (await client.post("/api/v1/payments", json=_payment_payload(ctx, 10000), headers=ctx["admin_headers"])).json()
    await client.post(f"/api/v1/payments/{payment['id']}/cancel", json={"reason": "r"}, headers=ctx["admin_headers"])

    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "auditfilters.t")
    await client.patch(
        f"/api/v1/users/{teacher['user']['id']}",
        json={"school_id": ctx["school"]["id"], "is_active": False},
        headers=ctx["admin_headers"],
    )

    by_action = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], action="payment.cancelled")
    assert by_action["total"] == 1
    assert by_action["items"][0]["entity_type"] == "Payment"

    by_entity_type = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], entity_type="User")
    assert by_entity_type["total"] == 1
    assert by_entity_type["items"][0]["action"] == "user.status_changed"

    by_actor = await _audit_logs(
        client, ctx["admin_headers"], ctx["school"]["id"], actor_user_id=ctx["admin_user_id"]
    )
    assert by_actor["total"] == 2

    far_past = await _audit_logs(client, ctx["admin_headers"], ctx["school"]["id"], date_to="2020-01-01")
    assert far_past["total"] == 0
