"""Phase 27 Sprint 1.2 — rappels automatiques de frais scolaires en retard.

Couvre : éligibilité (non échu / échu+solde>0 / payé intégralement / partiellement payé / CANCELLED
/ due_date NULL / solde nul), idempotence (double exécution du job, notification déjà existante),
plusieurs tuteurs (avec et sans compte), et isolation multi-tenant sur une exécution du job qui
traite toutes les organisations en une fois. Le job n'a pas de route HTTP dédiée (voir Discovery —
« ne pas appeler une route HTTP interne ») : les tests l'exécutent directement via
`send_overdue_fee_reminders`, puis vérifient l'effet observable via l'API `/notifications`
existante, même convention que test_attendance_notifications.py.
"""

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.fees.models import StudentFee
from app.modules.fees.overdue_reminders import send_overdue_fee_reminders
from app.modules.notifications.models import Notification
from tests.conftest import register_school, unique_email

STANDARD_PASSWORD = "SuperSecret123"
PAST_DUE_DATE = date(2020, 1, 1)
FUTURE_DUE_DATE = date(2099, 1, 1)


async def _login(client: AsyncClient, email: str, password: str = STANDARD_PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _run_job() -> None:
    async with AsyncSessionLocal() as db:
        await send_overdue_fee_reminders(db)


async def _setup_student(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    admin_headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
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
            headers=admin_headers,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": f"CE1-{suffix}"}, headers=admin_headers)
    ).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=admin_headers,
        )
    ).json()
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": f"F{suffix}",
                "first_name": "Koffi",
                "last_name": "Test",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "M",
            },
            headers=admin_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=admin_headers,
    )

    return {
        "org": data["organization"],
        "school_id": school_id,
        "admin_headers": admin_headers,
        "year": year,
        "student": student,
    }


async def _create_student_fee(client: AsyncClient, env: dict, due_date: date | None, amount: str = "50000") -> dict:
    """Crée une catégorie + un barème SCHOOL avec `due_date`, l'affecte à l'élève déjà inscrit et
    retourne le `StudentFee` créé (via financial-summary, seule vue qui expose son solde)."""
    suffix = uuid.uuid4().hex[:8]
    category = (
        await client.post(
            "/api/v1/fee-categories", json={"school_id": env["school_id"], "name": f"Scolarite-{suffix}"}, headers=env["admin_headers"]
        )
    ).json()
    schedule_payload = {
        "school_id": env["school_id"],
        "fee_category_id": category["id"],
        "academic_year_id": env["year"]["id"],
        "name": f"Tranche-{suffix}",
        "amount": amount,
        "scope_type": "SCHOOL",
    }
    if due_date is not None:
        schedule_payload["due_date"] = str(due_date)
    schedule = (await client.post("/api/v1/fee-schedules", json=schedule_payload, headers=env["admin_headers"])).json()
    generate = await client.post(f"/api/v1/fee-schedules/{schedule['id']}/generate", headers=env["admin_headers"])
    assert generate.status_code == 200, generate.text

    summary = (
        await client.get(f"/api/v1/students/{env['student']['id']}/financial-summary", headers=env["admin_headers"])
    ).json()
    fee = next(f for f in summary["fees"] if f["fee_schedule_id"] == schedule["id"])
    return fee


async def _pay(client: AsyncClient, env: dict, fee_id: str, amount: str) -> None:
    response = await client.post(
        "/api/v1/payments",
        json={
            "student_id": env["student"]["id"],
            "amount": amount,
            "method": "CASH",
            "paid_at": str(date(2026, 9, 5)),
            "idempotency_key": uuid.uuid4().hex,
            "allocations": [{"student_fee_id": fee_id, "amount": amount}],
        },
        headers=env["admin_headers"],
    )
    assert response.status_code == 201, response.text


async def _cancel_fee_directly(fee_id: str) -> None:
    """Aucun endpoint ne permet de passer un `StudentFee` à `CANCELLED` (voir Discovery) — accès
    direct en base, même motif que `tests/conftest.py::assign_role` pour un état sans endpoint."""
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        fee = await db.get(StudentFee, uuid.UUID(fee_id))
        assert fee is not None
        fee.status = "CANCELLED"
        await db.commit()


async def _link_parent(client: AsyncClient, env: dict, email_prefix: str) -> dict:
    """Même pattern que test_attendance_notifications.py::_link_parent — parent avec compte,
    lié comme tuteur ACTIF (`Guardian.user_id` non nul) à l'élève de cet environnement."""
    email = unique_email(email_prefix)
    parent = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Parent Test", "school_id": env["school_id"], "role_code": "PARENT"},
        headers=env["admin_headers"],
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
            json={"school_id": env["school_id"], "full_name": "Tuteur Test", "relationship_type": "father"},
            headers=env["admin_headers"],
        )
    ).json()
    link = await client.patch(
        f"/api/v1/guardians/{guardian['id']}", json={"user_id": parent_data["user"]["id"]}, headers=env["admin_headers"]
    )
    assert link.status_code == 200, link.text
    attach = await client.post(
        f"/api/v1/students/{env['student']['id']}/guardians", json={"guardian_id": guardian["id"]}, headers=env["admin_headers"]
    )
    assert attach.status_code == 201, attach.text

    token = await _login(client, email, "ParentPass123")
    return {"user": parent_data["user"], "guardian": guardian, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_guardian_without_account(client: AsyncClient, env: dict) -> dict:
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": env["school_id"], "full_name": "Sans Compte", "relationship_type": "mother"},
            headers=env["admin_headers"],
        )
    ).json()
    await client.post(
        f"/api/v1/students/{env['student']['id']}/guardians", json={"guardian_id": guardian["id"]}, headers=env["admin_headers"]
    )
    return guardian


async def _list_notifications(client: AsyncClient, headers: dict) -> list[dict]:
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _list_fee_overdue_notifications(client: AsyncClient, headers: dict) -> list[dict]:
    """`_pay` déclenche légitimement la notification PAYMENT_RECORDED déjà existante (Phase 21) —
    hors périmètre de ce sprint : les tests qui enregistrent un paiement filtrent sur FEE_OVERDUE
    pour ne pas confondre cet effet attendu avec une régression."""
    items = await _list_notifications(client, headers)
    return [item for item in items if item["type"] == "FEE_OVERDUE"]


async def _count_fee_overdue_notifications(school_id: str) -> int:
    """Lecture directe (aucun endpoint n'agrège les notifications par école) — utilisée pour
    vérifier positivement qu'aucune ligne FEE_OVERDUE n'a été créée, plutôt que de se contenter
    de « le job ne lève pas d'exception » (aucun destinataire n'existe dans ce cas pour interroger
    /notifications avec un token)."""
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.school_id == uuid.UUID(school_id), Notification.type == "FEE_OVERDUE")
        )
        return result.scalar_one()


# --- TEST 1 : frais non échu -> aucune notification -------------------------------------------------
async def test_fee_not_yet_due_creates_no_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue1")
    parent = await _link_parent(client, env, "parent.overdue1")
    await _create_student_fee(client, env, FUTURE_DUE_DATE)

    await _run_job()

    assert await _list_notifications(client, parent["headers"]) == []


# --- TEST 2 : frais échu + solde > 0 -> une notification FEE_OVERDUE --------------------------------
async def test_overdue_fee_with_positive_balance_notifies_guardian(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue2")
    parent = await _link_parent(client, env, "parent.overdue2")
    await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")

    await _run_job()

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["type"] == "FEE_OVERDUE"
    assert "Koffi Test" in items[0]["body"]
    assert "50000" in items[0]["body"]


# --- TEST 3 : frais échu + paiement complet -> aucune notification ---------------------------------
async def test_fully_paid_overdue_fee_creates_no_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue3")
    parent = await _link_parent(client, env, "parent.overdue3")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")
    await _pay(client, env, fee["id"], "50000")

    await _run_job()

    assert await _list_fee_overdue_notifications(client, parent["headers"]) == []


# --- TEST 4 : frais échu + paiement partiel -> notification avec le solde restant ------------------
async def test_partially_paid_overdue_fee_notifies_with_remaining_balance(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue4")
    parent = await _link_parent(client, env, "parent.overdue4")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")
    await _pay(client, env, fee["id"], "20000")

    await _run_job()

    items = await _list_fee_overdue_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["type"] == "FEE_OVERDUE"
    assert "30000" in items[0]["body"]


# --- TEST 5 : exécuter le job deux fois -> exactement une notification -----------------------------
async def test_running_job_twice_does_not_duplicate_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue5")
    parent = await _link_parent(client, env, "parent.overdue5")
    await _create_student_fee(client, env, PAST_DUE_DATE)

    await _run_job()
    await _run_job()

    assert len(await _list_notifications(client, parent["headers"])) == 1


# --- TEST 6 : tuteur sans user_id -> aucune notification pour ce tuteur -----------------------------
async def test_guardian_without_user_account_receives_no_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue6")
    await _create_guardian_without_account(client, env)
    await _create_student_fee(client, env, PAST_DUE_DATE)

    await _run_job()

    assert await _count_fee_overdue_notifications(env["school_id"]) == 0


# --- TEST 7 : plusieurs tuteurs avec compte -> une notification pour chacun ------------------------
async def test_multiple_guardians_with_accounts_each_receive_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue7")
    parent_a = await _link_parent(client, env, "parent.overdue7a")
    parent_b = await _link_parent(client, env, "parent.overdue7b")
    await _create_guardian_without_account(client, env)
    await _create_student_fee(client, env, PAST_DUE_DATE)

    await _run_job()

    assert len(await _list_notifications(client, parent_a["headers"])) == 1
    assert len(await _list_notifications(client, parent_b["headers"])) == 1


# --- TEST 8 : isolation multi-tenant sur une exécution unique du job -------------------------------
async def test_overdue_reminder_never_crosses_organizations(client: AsyncClient) -> None:
    env_a = await _setup_student(client, "overdue8a")
    env_b = await _setup_student(client, "overdue8b")
    parent_a = await _link_parent(client, env_a, "parent.overdue8a")
    parent_b = await _link_parent(client, env_b, "parent.overdue8b")
    await _create_student_fee(client, env_a, PAST_DUE_DATE)
    await _create_student_fee(client, env_b, PAST_DUE_DATE)

    # Un seul job, plateforme entière : doit traiter A et B sans jamais mélanger leurs destinataires.
    await _run_job()

    assert len(await _list_notifications(client, parent_a["headers"])) == 1
    assert len(await _list_notifications(client, parent_b["headers"])) == 1
    assert await _list_notifications(client, parent_a["headers"]) != await _list_notifications(client, parent_b["headers"])


# --- TEST 9 : frais CANCELLED -> aucune notification -----------------------------------------------
async def test_cancelled_fee_creates_no_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue9")
    parent = await _link_parent(client, env, "parent.overdue9")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _cancel_fee_directly(fee["id"])

    await _run_job()

    assert await _list_notifications(client, parent["headers"]) == []


# --- TEST 10 : due_date NULL -> aucune notification -------------------------------------------------
async def test_fee_without_due_date_creates_no_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue10")
    parent = await _link_parent(client, env, "parent.overdue10")
    await _create_student_fee(client, env, due_date=None)

    await _run_job()

    assert await _list_notifications(client, parent["headers"]) == []


# --- TEST 11 : montant payé >= montant dû (plusieurs paiements) -> aucune notification --------------
async def test_fee_paid_in_full_via_multiple_payments_creates_no_notification(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue11")
    parent = await _link_parent(client, env, "parent.overdue11")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")
    await _pay(client, env, fee["id"], "30000")
    await _pay(client, env, fee["id"], "20000")

    await _run_job()

    assert await _list_fee_overdue_notifications(client, parent["headers"]) == []


# --- TEST 12 : notification déjà existante (créée hors du job) -> aucune duplication ----------------
async def test_pre_existing_notification_is_not_duplicated(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdue12")
    parent = await _link_parent(client, env, "parent.overdue12")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            Notification(
                id=uuid.uuid4(),
                school_id=uuid.UUID(env["school_id"]),
                organization_id=uuid.UUID(env["org"]["id"]),
                recipient_user_id=uuid.UUID(parent["user"]["id"]),
                type="FEE_OVERDUE",
                title="Paiement en retard",
                body="Notification pré-existante (test).",
                student_fee_id=uuid.UUID(fee["id"]),
            )
        )
        await db.commit()

    await _run_job()

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["body"] == "Notification pré-existante (test)."
