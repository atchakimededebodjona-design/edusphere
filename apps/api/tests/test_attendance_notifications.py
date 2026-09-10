"""Phase 27 Sprint 1 — alerte automatique d'absence parent.

Couvre : notification créée uniquement quand un AttendanceRecord DEVIENT ABSENT (création directe,
ou correction PRESENT/LATE -> ABSENT), jamais pour PRESENT/LATE, jamais en double sur une
resoumission ABSENT -> ABSENT ou une correction ABSENT -> PRESENT, plusieurs tuteurs actifs notifiés
individuellement, aucun tuteur actif -> aucune erreur, isolation multi-tenant stricte, et
non-régression des notifications existantes (bulletin publié, paiement enregistré, annonces,
compteur non lu) — mêmes fixtures/conventions que test_attendance.py et test_notifications.py.
"""

import uuid
from datetime import date

from httpx import AsyncClient

from tests.conftest import register_school, unique_email

STANDARD_PASSWORD = "SuperSecret123"


async def _login(client: AsyncClient, email: str, password: str = STANDARD_PASSWORD) -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _setup_class_with_students(client: AsyncClient, headers: dict, school_id: str, n_students: int = 1) -> dict:
    """Même contenu que test_attendance.py::_setup_class_with_students (dupliqué plutôt
    qu'importé : aucun des deux fichiers de test n'importe l'autre dans ce dépôt, convention déjà
    suivie par test_report_cards_notifications.py vis-à-vis de test_report_cards.py)."""
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
            headers=headers,
        )
    ).json()
    term = (
        await client.post(
            "/api/v1/academic-terms",
            json={
                "academic_year_id": year["id"],
                "name": "Trimestre 1",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2026, 12, 20)),
            },
            headers=headers,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": f"CE1-{suffix}"}, headers=headers)
    ).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers,
        )
    ).json()

    students = []
    for i in range(n_students):
        student = (
            await client.post(
                "/api/v1/students",
                json={
                    "school_id": school_id,
                    "matricule": f"S{suffix}{i:03d}",
                    "first_name": f"Eleve{i}",
                    "last_name": "Test",
                    "date_of_birth": str(date(2015, 1, 1)),
                    "sex": "M" if i % 2 == 0 else "F",
                },
                headers=headers,
            )
        ).json()
        await client.post(
            f"/api/v1/students/{student['id']}/enrollments",
            json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
            headers=headers,
        )
        students.append(student)

    return {"year": year, "term": term, "level": level, "class": school_class, "students": students}


async def _create_session(client: AsyncClient, headers: dict, ctx: dict, session_date: date) -> dict:
    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": ctx["class"]["id"], "academic_term_id": ctx["term"]["id"], "session_date": str(session_date)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _submit_record(client: AsyncClient, headers: dict, session_id: str, student_id: str, status: str) -> dict:
    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": session_id, "records": [{"student_id": student_id, "status": status}]},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()[0]


async def _patch_record(client: AsyncClient, headers: dict, record_id: str, **fields) -> dict:
    response = await client.patch(f"/api/v1/attendance-records/{record_id}", json=fields, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


async def _link_parent(client: AsyncClient, admin_headers: dict, school_id: str, student_id: str, email_prefix: str) -> dict:
    """Même pattern que test_notifications.py::_link_parent — crée un parent avec compte
    utilisateur, lié comme tuteur ACTIF (au sens de ce sprint : `Guardian.user_id` non nul, seul
    signal utilisé par `resolve_guardian_user_ids_for_student`, voir inspection préalable)."""
    email = unique_email(email_prefix)
    parent = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Parent Test", "school_id": school_id, "role_code": "PARENT"},
        headers=admin_headers,
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
            json={"school_id": school_id, "full_name": "Tuteur Test", "relationship_type": "father"},
            headers=admin_headers,
        )
    ).json()
    link = await client.patch(
        f"/api/v1/guardians/{guardian['id']}", json={"user_id": parent_data["user"]["id"]}, headers=admin_headers
    )
    assert link.status_code == 200, link.text
    attach = await client.post(
        f"/api/v1/students/{student_id}/guardians", json={"guardian_id": guardian["id"]}, headers=admin_headers
    )
    assert attach.status_code == 201, attach.text

    token = await _login(client, email, "ParentPass123")
    return {"user": parent_data["user"], "guardian": guardian, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_guardian_without_account(client: AsyncClient, admin_headers: dict, school_id: str, student_id: str) -> dict:
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": school_id, "full_name": "Sans Compte", "relationship_type": "mother"},
            headers=admin_headers,
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student_id}/guardians", json={"guardian_id": guardian["id"]}, headers=admin_headers
    )
    return guardian


async def _list_notifications(client: AsyncClient, headers: dict) -> list[dict]:
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def _setup(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    admin_headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    ctx = await _setup_class_with_students(client, admin_headers, data["school"]["id"])
    session = await _create_session(client, admin_headers, ctx, date(2026, 10, 1))
    return {"admin_headers": admin_headers, "school_id": data["school"]["id"], "ctx": ctx, "session": session}


# --- TEST 1 : création directe ABSENT -> une notification pour le tuteur actif -------------------
async def test_absent_record_creation_notifies_active_guardian(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif1")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif1")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["type"] == "STUDENT_ABSENT"
    assert "Eleve0" in items[0]["body"]


# --- TEST 2 : PRESENT -> aucune notification -------------------------------------------------------
async def test_present_record_creates_no_absence_notification(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif2")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif2")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "PRESENT")

    assert await _list_notifications(client, parent["headers"]) == []


# --- TEST 3 : LATE -> aucune notification -----------------------------------------------------------
async def test_late_record_creates_no_absence_notification(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif3")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif3")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "LATE")

    assert await _list_notifications(client, parent["headers"]) == []


# --- TEST 4 : correction PRESENT -> ABSENT -> une notification -------------------------------------
async def test_correcting_present_to_absent_notifies_guardian(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif4")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif4")

    record = await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "PRESENT")
    assert await _list_notifications(client, parent["headers"]) == []

    await _patch_record(client, env["admin_headers"], record["id"], status="ABSENT")

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["type"] == "STUDENT_ABSENT"


# --- TEST 5 : correction ABSENT -> PRESENT -> aucune notification supplémentaire -------------------
async def test_correcting_absent_to_present_creates_no_new_absence_notification(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif5")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif5")

    # Création directe en ABSENT : notifie légitimement une fois (règle du TEST 1).
    record = await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    assert len(await _list_notifications(client, parent["headers"])) == 1

    await _patch_record(client, env["admin_headers"], record["id"], status="PRESENT")

    # Toujours une seule notification : la correction ABSENT -> PRESENT n'en ajoute pas.
    assert len(await _list_notifications(client, parent["headers"])) == 1


# --- TEST 6 : resoumission ABSENT -> ABSENT -> aucune notification supplémentaire ------------------
async def test_resubmitting_same_absent_status_does_not_duplicate_notification(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif6")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif6")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")
    assert len(await _list_notifications(client, parent["headers"])) == 1

    # Resoumission idempotente (même endpoint POST /attendance-records, même statut ABSENT) — le
    # chemin `upsert_records`, distinct de la correction PATCH testée en TEST 4/5.
    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    assert len(await _list_notifications(client, parent["headers"])) == 1


# --- TEST 7 : plusieurs tuteurs actifs -> une notification par tuteur ------------------------------
async def test_multiple_active_guardians_each_receive_one_notification(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif7")
    student = env["ctx"]["students"][0]
    parent_a = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif7a")
    parent_b = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif7b")

    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    assert len(await _list_notifications(client, parent_a["headers"])) == 1
    assert len(await _list_notifications(client, parent_b["headers"])) == 1


# --- TEST 8 : aucun tuteur actif -> pas d'erreur, pas de notification ------------------------------
async def test_student_without_active_guardian_records_absence_without_error(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif8")
    student = env["ctx"]["students"][0]
    # Tuteur SANS compte utilisateur — attaché, mais jamais destinataire possible (voir
    # `resolve_guardian_user_ids_for_student`). Aucun tuteur avec compte du tout ici.
    await _create_guardian_without_account(client, env["admin_headers"], env["school_id"], student["id"])

    response = await client.post(
        "/api/v1/attendance-records",
        json={"session_id": env["session"]["id"], "records": [{"student_id": student["id"], "status": "ABSENT"}]},
        headers=env["admin_headers"],
    )
    assert response.status_code == 201, response.text
    assert response.json()[0]["status"] == "ABSENT"


# --- TEST 9 : isolation multi-tenant -----------------------------------------------------------------
async def test_absence_notification_never_crosses_organizations(client: AsyncClient) -> None:
    env_a = await _setup(client, "absnotif9a")
    env_b = await _setup(client, "absnotif9b")
    student_a = env_a["ctx"]["students"][0]
    student_b = env_b["ctx"]["students"][0]
    parent_a = await _link_parent(client, env_a["admin_headers"], env_a["school_id"], student_a["id"], "parent.absnotif9a")
    parent_b = await _link_parent(client, env_b["admin_headers"], env_b["school_id"], student_b["id"], "parent.absnotif9b")

    await _submit_record(client, env_a["admin_headers"], env_a["session"]["id"], student_a["id"], "ABSENT")

    assert len(await _list_notifications(client, parent_a["headers"])) == 1
    # Organisation B jamais touchée par une absence déclarée dans l'organisation A.
    assert await _list_notifications(client, parent_b["headers"]) == []


# --- TEST 10 : non-régression des notifications existantes -----------------------------------------
async def test_existing_notification_flows_are_not_regressed_by_absence_feature(client: AsyncClient) -> None:
    env = await _setup(client, "absnotif10")
    student = env["ctx"]["students"][0]
    parent = await _link_parent(client, env["admin_headers"], env["school_id"], student["id"], "parent.absnotif10")

    # Annonce école entière -> 1 notification ANNOUNCEMENT pour ce parent.
    announcement = await client.post(
        "/api/v1/announcements",
        json={"school_id": env["school_id"], "title": "Info", "body": "Contenu", "target_type": "SCHOOL"},
        headers=env["admin_headers"],
    )
    assert announcement.status_code == 201

    # Bulletin publié -> 1 notification REPORT_CARD_PUBLISHED.
    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={
                "school_id": env["school_id"],
                "name": "Standard-absnotif10",
                "html_content": "<html><body><h1>{{ student.first_name }}</h1></body></html>",
            },
            headers=env["admin_headers"],
        )
    ).json()
    generated = (
        await client.post(
            "/api/v1/report-cards/generate",
            json={
                "class_id": env["ctx"]["class"]["id"],
                "academic_term_id": env["ctx"]["term"]["id"],
                "template_id": template["id"],
            },
            headers=env["admin_headers"],
        )
    ).json()
    publish = await client.post(f"/api/v1/report-cards/{generated[0]['id']}/publish", headers=env["admin_headers"])
    assert publish.status_code == 200

    # Paiement enregistré -> 1 notification PAYMENT_RECORDED.
    category = (
        await client.post(
            "/api/v1/fee-categories", json={"school_id": env["school_id"], "name": "Scolarite"}, headers=env["admin_headers"]
        )
    ).json()
    schedule = (
        await client.post(
            "/api/v1/fee-schedules",
            json={
                "school_id": env["school_id"],
                "fee_category_id": category["id"],
                "academic_year_id": env["ctx"]["year"]["id"],
                "name": "Frais",
                "amount": "10000",
                "scope_type": "SCHOOL",
            },
            headers=env["admin_headers"],
        )
    ).json()
    await client.post(f"/api/v1/fee-schedules/{schedule['id']}/generate", headers=env["admin_headers"])
    student_fee = (
        await client.get(f"/api/v1/students/{student['id']}/financial-summary", headers=env["admin_headers"])
    ).json()["fees"][0]
    payment = await client.post(
        "/api/v1/payments",
        json={
            "student_id": student["id"],
            "amount": "10000",
            "method": "CASH",
            "paid_at": str(date(2026, 10, 1)),
            "idempotency_key": uuid.uuid4().hex,
            "allocations": [{"student_fee_id": student_fee["id"], "amount": "10000"}],
        },
        headers=env["admin_headers"],
    )
    assert payment.status_code == 201, payment.text

    # Absence -> 1 notification STUDENT_ABSENT (cette fonctionnalité).
    await _submit_record(client, env["admin_headers"], env["session"]["id"], student["id"], "ABSENT")

    items = await _list_notifications(client, parent["headers"])
    types = sorted(item["type"] for item in items)
    assert types == ["ANNOUNCEMENT", "PAYMENT_RECORDED", "REPORT_CARD_PUBLISHED", "STUDENT_ABSENT"]

    unread = await client.get("/api/v1/notifications/unread-count", headers=parent["headers"])
    assert unread.json()["count"] == 4

    mark_all = await client.post("/api/v1/notifications/mark-all-read", headers=parent["headers"])
    assert mark_all.status_code == 200
    unread_after = await client.get("/api/v1/notifications/unread-count", headers=parent["headers"])
    assert unread_after.json()["count"] == 0
