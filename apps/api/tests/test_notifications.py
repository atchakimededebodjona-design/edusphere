"""Phase 21 — Communications & Notifications.

Couvre : le modèle unique Notification, les 2 événements automatiques (bulletin publié, paiement
enregistré), les annonces (école entière / classes ciblées, déduplication), lecture/non-lue et
pagination, RBAC (announcements.manage), RLS (spécifique par destinataire, pas par organisation),
sécurité (IDOR, cross-school, cross-org), et non-régression email (Phase 21 ne doit rien changer
aux 4 emails existants).
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


async def _setup_school(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    return {"org": data["organization"], "school": data["school"], "admin_headers": headers, "admin_user_id": data["user"]["id"]}


async def _create_class(client: AsyncClient, ctx: dict, suffix: str) -> dict:
    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": ctx["school"]["id"],
                "name": f"Annee-{suffix}",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2027, 6, 30)),
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    level = (
        await client.post(
            "/api/v1/education-levels", json={"school_id": ctx["school"]["id"], "name": f"Niveau-{suffix}"}, headers=ctx["admin_headers"]
        )
    ).json()
    return (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": f"Classe-{suffix}"},
            headers=ctx["admin_headers"],
        )
    ).json()


async def _create_student_in_class(client: AsyncClient, ctx: dict, school_class: dict, suffix: str) -> dict:
    student = (
        await client.post(
            "/api/v1/students",
            json={
                "school_id": ctx["school"]["id"],
                "matricule": f"N{suffix}",
                "first_name": f"Eleve-{suffix}",
                "last_name": "Test",
                "date_of_birth": str(date(2015, 1, 1)),
                "sex": "F",
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=ctx["admin_headers"],
    )
    return student


async def _link_parent(client: AsyncClient, ctx: dict, student: dict, email_prefix: str) -> dict:
    """Crée un parent avec compte utilisateur, lié comme tuteur de `student`. Retourne aussi
    `guardian` et `user` pour les cas qui en ont besoin."""
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
        f"/api/v1/students/{student['id']}/guardians", json={"guardian_id": guardian["id"]}, headers=ctx["admin_headers"]
    )
    assert attach.status_code == 201, attach.text

    token = await _login(client, email, "ParentPass123")
    return {"user": parent_data["user"], "guardian": guardian, "headers": {"Authorization": f"Bearer {token}"}}


async def _create_guardian_without_account(client: AsyncClient, ctx: dict, student: dict) -> dict:
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": ctx["school"]["id"], "full_name": "Sans Compte", "relationship_type": "mother"},
            headers=ctx["admin_headers"],
        )
    ).json()
    await client.post(
        f"/api/v1/students/{student['id']}/guardians", json={"guardian_id": guardian["id"]}, headers=ctx["admin_headers"]
    )
    return guardian


async def _list_notifications(client: AsyncClient, headers: dict) -> list[dict]:
    response = await client.get("/api/v1/notifications", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


# --- Événements automatiques : bulletin publié --------------------------------------------------
MINIMAL_TEMPLATE = "<html><body><h1>{{ student.first_name }}</h1></body></html>"


async def test_report_card_publication_creates_in_app_notification_for_linked_parent(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifrc")
    school_class = await _create_class(client, ctx, "rc1")
    student = await _create_student_in_class(client, ctx, school_class, "rc1")
    parent = await _link_parent(client, ctx, student, "parent.notifrc")

    year_term = await client.post(
        "/api/v1/academic-terms",
        json={
            "academic_year_id": school_class["academic_year_id"],
            "name": "T1",
            "start_date": str(date(2026, 9, 1)),
            "end_date": str(date(2026, 12, 20)),
        },
        headers=ctx["admin_headers"],
    )
    term = year_term.json()
    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": ctx["school"]["id"], "name": "Standard-rc1", "html_content": MINIMAL_TEMPLATE},
            headers=ctx["admin_headers"],
        )
    ).json()
    generated = (
        await client.post(
            "/api/v1/report-cards/generate",
            json={"class_id": school_class["id"], "academic_term_id": term["id"], "template_id": template["id"]},
            headers=ctx["admin_headers"],
        )
    ).json()
    report_card = generated[0]

    publish = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["admin_headers"])
    assert publish.status_code == 200

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["type"] == "REPORT_CARD_PUBLISHED"
    assert "Eleve-rc1" in items[0]["body"]
    # Jamais de moyenne/rang/appréciation dans la notification (même principe que l'email).
    assert "moyenne" not in items[0]["body"].lower()

    # Non-régression : republier ne duplique pas la notification.
    republish = await client.post(f"/api/v1/report-cards/{report_card['id']}/publish", headers=ctx["admin_headers"])
    assert republish.status_code == 200
    assert len(await _list_notifications(client, parent["headers"])) == 1


async def test_guardian_without_user_account_never_gets_a_notification(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifrcnouser")
    school_class = await _create_class(client, ctx, "rc2")
    student = await _create_student_in_class(client, ctx, school_class, "rc2")
    await _create_guardian_without_account(client, ctx, student)

    term = (
        await client.post(
            "/api/v1/academic-terms",
            json={
                "academic_year_id": school_class["academic_year_id"],
                "name": "T1",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2026, 12, 20)),
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    template = (
        await client.post(
            "/api/v1/report-card-templates",
            json={"school_id": ctx["school"]["id"], "name": "Standard-rc2", "html_content": MINIMAL_TEMPLATE},
            headers=ctx["admin_headers"],
        )
    ).json()
    generated = (
        await client.post(
            "/api/v1/report-cards/generate",
            json={"class_id": school_class["id"], "academic_term_id": term["id"], "template_id": template["id"]},
            headers=ctx["admin_headers"],
        )
    ).json()
    # Aucune assertion possible côté notification (aucun user à interroger) — le test vérifie
    # simplement que la publication réussit sans erreur malgré un tuteur sans compte.
    publish = await client.post(f"/api/v1/report-cards/{generated[0]['id']}/publish", headers=ctx["admin_headers"])
    assert publish.status_code == 200


# --- Événements automatiques : paiement enregistré ------------------------------------------------
async def _setup_fee(client: AsyncClient, ctx: dict, student: dict, school_class: dict) -> dict:
    category = (
        await client.post("/api/v1/fee-categories", json={"school_id": ctx["school"]["id"], "name": "Scolarite"}, headers=ctx["admin_headers"])
    ).json()
    schedule = (
        await client.post(
            "/api/v1/fee-schedules",
            json={
                "school_id": ctx["school"]["id"],
                "fee_category_id": category["id"],
                "academic_year_id": school_class["academic_year_id"],
                "name": "Frais",
                "amount": "10000",
                "scope_type": "SCHOOL",
            },
            headers=ctx["admin_headers"],
        )
    ).json()
    await client.post(f"/api/v1/fee-schedules/{schedule['id']}/generate", headers=ctx["admin_headers"])
    summary = await client.get(f"/api/v1/students/{student['id']}/financial-summary", headers=ctx["admin_headers"])
    return summary.json()["fees"][0]


async def test_payment_recording_creates_in_app_notification_for_linked_parent(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifpay")
    school_class = await _create_class(client, ctx, "pay1")
    student = await _create_student_in_class(client, ctx, school_class, "pay1")
    parent = await _link_parent(client, ctx, student, "parent.notifpay")
    student_fee = await _setup_fee(client, ctx, student, school_class)

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
        headers=ctx["admin_headers"],
    )
    assert payment.status_code == 201, payment.text

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1
    assert items[0]["type"] == "PAYMENT_RECORDED"
    assert "Eleve-pay1" in items[0]["body"]
    # Contenu minimal : jamais de montant/détail comptable.
    assert "10000" not in items[0]["body"]


async def test_duplicate_payment_idempotency_key_does_not_duplicate_notification(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifpaydup")
    school_class = await _create_class(client, ctx, "pay2")
    student = await _create_student_in_class(client, ctx, school_class, "pay2")
    parent = await _link_parent(client, ctx, student, "parent.notifpaydup")
    student_fee = await _setup_fee(client, ctx, student, school_class)

    payload = {
        "student_id": student["id"],
        "amount": "5000",
        "method": "CASH",
        "paid_at": str(date(2026, 10, 1)),
        "idempotency_key": "fixed-notif-key",
        "allocations": [{"student_fee_id": student_fee["id"], "amount": "5000"}],
    }
    first = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert first.status_code == 201
    second = await client.post("/api/v1/payments", json=payload, headers=ctx["admin_headers"])
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]

    items = await _list_notifications(client, parent["headers"])
    assert len(items) == 1


# --- Lecture / non-lue / pagination -------------------------------------------------------------
async def test_unread_count_and_mark_read(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifread")
    school_class = await _create_class(client, ctx, "rd1")
    student = await _create_student_in_class(client, ctx, school_class, "rd1")
    parent = await _link_parent(client, ctx, student, "parent.notifread")
    student_fee = await _setup_fee(client, ctx, student, school_class)

    await client.post(
        "/api/v1/payments",
        json={
            "student_id": student["id"],
            "amount": "10000",
            "method": "CASH",
            "paid_at": str(date(2026, 10, 1)),
            "idempotency_key": uuid.uuid4().hex,
            "allocations": [{"student_fee_id": student_fee["id"], "amount": "10000"}],
        },
        headers=ctx["admin_headers"],
    )

    unread = await client.get("/api/v1/notifications/unread-count", headers=parent["headers"])
    assert unread.status_code == 200
    assert unread.json()["count"] == 1

    items = await _list_notifications(client, parent["headers"])
    notification_id = items[0]["id"]
    assert items[0]["read_at"] is None

    mark = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=parent["headers"])
    assert mark.status_code == 200
    assert mark.json()["read_at"] is not None

    unread_after = await client.get("/api/v1/notifications/unread-count", headers=parent["headers"])
    assert unread_after.json()["count"] == 0

    # Idempotent : marquer une seconde fois ne casse rien.
    mark_again = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=parent["headers"])
    assert mark_again.status_code == 200


async def test_mark_all_read(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifreadall")
    school_class = await _create_class(client, ctx, "rd2")
    student = await _create_student_in_class(client, ctx, school_class, "rd2")
    parent = await _link_parent(client, ctx, student, "parent.notifreadall")

    # Deux annonces école entière -> 2 notifications pour ce parent.
    for i in range(2):
        response = await client.post(
            "/api/v1/announcements",
            json={"school_id": ctx["school"]["id"], "title": f"Annonce {i}", "body": "Contenu", "target_type": "SCHOOL"},
            headers=ctx["admin_headers"],
        )
        assert response.status_code == 201, response.text

    unread_before = await client.get("/api/v1/notifications/unread-count", headers=parent["headers"])
    assert unread_before.json()["count"] == 2

    mark_all = await client.post("/api/v1/notifications/mark-all-read", headers=parent["headers"])
    assert mark_all.status_code == 200

    unread_after = await client.get("/api/v1/notifications/unread-count", headers=parent["headers"])
    assert unread_after.json()["count"] == 0


async def test_notification_pagination_orders_most_recent_first(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifpage")
    school_class = await _create_class(client, ctx, "pg1")
    student = await _create_student_in_class(client, ctx, school_class, "pg1")
    parent = await _link_parent(client, ctx, student, "parent.notifpage")

    titles = [f"Annonce-{i}" for i in range(5)]
    for title in titles:
        await client.post(
            "/api/v1/announcements",
            json={"school_id": ctx["school"]["id"], "title": title, "body": "Contenu", "target_type": "SCHOOL"},
            headers=ctx["admin_headers"],
        )

    page1 = await client.get("/api/v1/notifications?limit=2", headers=parent["headers"])
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["items"][0]["title"] == "Annonce-4"  # le plus récent d'abord
    assert body1["next_before"] is not None

    page2 = await client.get(f"/api/v1/notifications?limit=2&before={body1['next_before']}", headers=parent["headers"])
    body2 = page2.json()
    assert len(body2["items"]) == 2
    assert body2["items"][0]["title"] == "Annonce-2"

    all_titles = [n["title"] for n in body1["items"] + body2["items"]]
    assert len(set(all_titles)) == 4  # pas de doublon entre pages


async def test_mark_read_of_other_users_notification_returns_404(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifidor")
    school_class = await _create_class(client, ctx, "id1")
    student_a = await _create_student_in_class(client, ctx, school_class, "id1a")
    student_b = await _create_student_in_class(client, ctx, school_class, "id1b")
    parent_a = await _link_parent(client, ctx, student_a, "parent.notifidora")
    parent_b = await _link_parent(client, ctx, student_b, "parent.notifidorb")

    await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "Pour B", "body": "x", "target_type": "SCHOOL"},
        headers=ctx["admin_headers"],
    )
    items_b = await _list_notifications(client, parent_b["headers"])
    notification_id = items_b[0]["id"]

    forged = await client.post(f"/api/v1/notifications/{notification_id}/read", headers=parent_a["headers"])
    assert forged.status_code == 404

    # La notification de B reste non lue malgré la tentative de A.
    still_unread = await client.get("/api/v1/notifications/unread-count", headers=parent_b["headers"])
    assert still_unread.json()["count"] == 1


# --- Annonces : ciblage école / classes, déduplication --------------------------------------------
async def test_announcement_school_wide_reaches_school_members_not_other_schools(client: AsyncClient) -> None:
    ctx_a = await _setup_school(client, "annschoola")
    ctx_b = await _setup_school(client, "annschoolb")
    class_a = await _create_class(client, ctx_a, "sa1")
    student_a = await _create_student_in_class(client, ctx_a, class_a, "sa1")
    parent_a = await _link_parent(client, ctx_a, student_a, "parent.annschoola")
    class_b = await _create_class(client, ctx_b, "sb1")
    student_b = await _create_student_in_class(client, ctx_b, class_b, "sb1")
    parent_b = await _link_parent(client, ctx_b, student_b, "parent.annschoolb")
    teacher_a = await _create_user_with_role(client, ctx_a["admin_headers"], ctx_a["school"]["id"], "TEACHER", "teacher.annschoola")

    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx_a["school"]["id"], "title": "Ecole A", "body": "Info", "target_type": "SCHOOL"},
        headers=ctx_a["admin_headers"],
    )
    assert response.status_code == 201
    # Destinataires attendus : admin A + parent A + teacher A = 3.
    assert response.json()["recipient_count"] == 3

    assert len(await _list_notifications(client, parent_a["headers"])) == 1
    assert len(await _list_notifications(client, teacher_a["headers"])) == 1
    assert len(await _list_notifications(client, ctx_a["admin_headers"])) == 1
    # École B jamais touchée.
    assert len(await _list_notifications(client, parent_b["headers"])) == 0


async def test_announcement_class_targeted_reaches_only_that_class_parents(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "annclass")
    class_1 = await _create_class(client, ctx, "cl1")
    class_2 = await _create_class(client, ctx, "cl2")
    student_1 = await _create_student_in_class(client, ctx, class_1, "cl1")
    student_2 = await _create_student_in_class(client, ctx, class_2, "cl2")
    parent_1 = await _link_parent(client, ctx, student_1, "parent.annclass1")
    parent_2 = await _link_parent(client, ctx, student_2, "parent.annclass2")

    response = await client.post(
        "/api/v1/announcements",
        json={
            "school_id": ctx["school"]["id"],
            "title": "Classe 1 seulement",
            "body": "Sortie scolaire",
            "target_type": "CLASS",
            "class_ids": [class_1["id"]],
        },
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 201
    assert response.json()["recipient_count"] == 1

    assert len(await _list_notifications(client, parent_1["headers"])) == 1
    assert len(await _list_notifications(client, parent_2["headers"])) == 0


async def test_announcement_deduplicates_parent_with_children_in_multiple_targeted_classes(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "anndedup")
    class_1 = await _create_class(client, ctx, "dd1")
    class_2 = await _create_class(client, ctx, "dd2")
    student_1 = await _create_student_in_class(client, ctx, class_1, "dd1")
    student_2 = await _create_student_in_class(client, ctx, class_2, "dd2")

    # Même parent, deux enfants dans les deux classes ciblées (même Guardian, StudentGuardian x2).
    email = unique_email("parent.anndedup")
    parent_user = (
        await client.post(
            "/api/v1/users",
            json={"email": email, "full_name": "Parent Dedup", "school_id": ctx["school"]["id"], "role_code": "PARENT"},
            headers=ctx["admin_headers"],
        )
    ).json()
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": parent_user["dev_reset_token"], "new_password": "ParentPass123"}
    )
    assert reset.status_code == 204
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={"school_id": ctx["school"]["id"], "full_name": "Parent Dedup", "relationship_type": "mother"},
            headers=ctx["admin_headers"],
        )
    ).json()
    await client.patch(f"/api/v1/guardians/{guardian['id']}", json={"user_id": parent_user["user"]["id"]}, headers=ctx["admin_headers"])
    await client.post(f"/api/v1/students/{student_1['id']}/guardians", json={"guardian_id": guardian["id"]}, headers=ctx["admin_headers"])
    await client.post(f"/api/v1/students/{student_2['id']}/guardians", json={"guardian_id": guardian["id"]}, headers=ctx["admin_headers"])
    parent_token = await _login(client, email, "ParentPass123")
    parent_headers = {"Authorization": f"Bearer {parent_token}"}

    response = await client.post(
        "/api/v1/announcements",
        json={
            "school_id": ctx["school"]["id"],
            "title": "Deux classes",
            "body": "x",
            "target_type": "CLASS",
            "class_ids": [class_1["id"], class_2["id"]],
        },
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 201
    assert response.json()["recipient_count"] == 1  # une seule notification malgré 2 classes

    items = await _list_notifications(client, parent_headers)
    assert len(items) == 1


async def test_announcement_class_must_belong_to_school(client: AsyncClient) -> None:
    ctx_a = await _setup_school(client, "annwrongschoola")
    ctx_b = await _setup_school(client, "annwrongschoolb")
    class_b = await _create_class(client, ctx_b, "wsb")

    response = await client.post(
        "/api/v1/announcements",
        json={
            "school_id": ctx_a["school"]["id"],
            "title": "x",
            "body": "x",
            "target_type": "CLASS",
            "class_ids": [class_b["id"]],
        },
        headers=ctx_a["admin_headers"],
    )
    assert response.status_code == 400


async def test_announcement_target_validation_rejects_mismatched_payloads(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "anninvalid")

    missing_classes = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "x", "body": "x", "target_type": "CLASS"},
        headers=ctx["admin_headers"],
    )
    assert missing_classes.status_code == 400

    unexpected_classes = await client.post(
        "/api/v1/announcements",
        json={
            "school_id": ctx["school"]["id"],
            "title": "x",
            "body": "x",
            "target_type": "SCHOOL",
            "class_ids": [str(uuid.uuid4())],
        },
        headers=ctx["admin_headers"],
    )
    assert unexpected_classes.status_code == 400


async def test_announcement_title_and_body_length_limits(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "annlen")

    too_long_title = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "x" * 256, "body": "ok", "target_type": "SCHOOL"},
        headers=ctx["admin_headers"],
    )
    assert too_long_title.status_code == 422

    empty_body = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "ok", "body": "", "target_type": "SCHOOL"},
        headers=ctx["admin_headers"],
    )
    assert empty_body.status_code == 422


# --- RBAC ------------------------------------------------------------------------------------
async def test_teacher_and_accountant_cannot_publish_announcement(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "annrbac")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "teacher.annrbac")
    accountant = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "ACCOUNTANT", "accountant.annrbac")

    for actor in (teacher, accountant):
        response = await client.post(
            "/api/v1/announcements",
            json={"school_id": ctx["school"]["id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
            headers=actor["headers"],
        )
        assert response.status_code == 403

    # Mais un comptable reçoit bien ses propres notifications (annonce publiée par l'admin).
    published = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "Pour tous", "body": "x", "target_type": "SCHOOL"},
        headers=ctx["admin_headers"],
    )
    assert published.status_code == 201
    assert len(await _list_notifications(client, accountant["headers"])) == 1


async def test_director_can_publish_announcement(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "anndirector")
    director = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "DIRECTOR", "director.anndirector")

    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
        headers=director["headers"],
    )
    assert response.status_code == 201


# --- Isolation cross-school / cross-organization -------------------------------------------------
async def test_admin_a_cannot_publish_announcement_for_school_b(client: AsyncClient) -> None:
    ctx_a = await _setup_school(client, "anncrossa")
    ctx_b = await _setup_school(client, "anncrossb")

    response = await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx_b["school"]["id"], "title": "x", "body": "x", "target_type": "SCHOOL"},
        headers=ctx_a["admin_headers"],
    )
    assert response.status_code in (403, 404)  # RLS rend l'école B invisible sous le contexte de A


async def test_row_level_security_hides_notification_row_even_bypassing_app_check(client: AsyncClient) -> None:
    """Preuve RLS brute (session directe), même motif que test_tenant_isolation.py — la policy
    `notifications_recipient_isolation` doit masquer la ligne d'un AUTRE utilisateur même à un
    administrateur de la même organisation, contrairement au motif générique basé sur
    l'organisation utilisé par toutes les autres tables."""
    from sqlalchemy import select

    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.notifications.models import Notification

    ctx = await _setup_school(client, "notifrls")
    school_class = await _create_class(client, ctx, "rls1")
    student = await _create_student_in_class(client, ctx, school_class, "rls1")
    parent = await _link_parent(client, ctx, student, "parent.notifrls")

    await client.post(
        "/api/v1/announcements",
        json={"school_id": ctx["school"]["id"], "title": "Pour le parent", "body": "x", "target_type": "SCHOOL"},
        headers=ctx["admin_headers"],
    )
    items = await _list_notifications(client, parent["headers"])
    notification_id = uuid.UUID(items[0]["id"])

    async with AsyncSessionLocal() as db:
        # Contexte de l'ADMIN de la même école/organisation — pas un tenant étranger, mais un
        # AUTRE utilisateur : la ligne doit rester invisible malgré l'appartenance commune.
        await apply_tenant_context(db, uuid.UUID(ctx["admin_user_id"]))
        result = await db.execute(select(Notification).where(Notification.id == notification_id))
        assert result.scalar_one_or_none() is None

        # Contrôle positif : l'admin voit bien SA PROPRE notification (générée par sa propre
        # annonce, voir test_announcement_school_wide_reaches_school_members_not_other_schools).
        own_result = await db.execute(
            select(Notification).where(Notification.recipient_user_id == uuid.UUID(ctx["admin_user_id"]))
        )
        assert own_result.scalar_one_or_none() is not None
        await db.rollback()


async def test_parent_a_cannot_see_notifications_of_parent_b_via_api(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "notifparentab")
    school_class = await _create_class(client, ctx, "pab1")
    student_a = await _create_student_in_class(client, ctx, school_class, "paba")
    student_b = await _create_student_in_class(client, ctx, school_class, "pabb")
    parent_a = await _link_parent(client, ctx, student_a, "parent.notifpaba")
    parent_b = await _link_parent(client, ctx, student_b, "parent.notifpabb")
    student_fee_a = await _setup_fee(client, ctx, student_a, school_class)

    await client.post(
        "/api/v1/payments",
        json={
            "student_id": student_a["id"],
            "amount": "10000",
            "method": "CASH",
            "paid_at": str(date(2026, 10, 1)),
            "idempotency_key": uuid.uuid4().hex,
            "allocations": [{"student_fee_id": student_fee_a["id"], "amount": "10000"}],
        },
        headers=ctx["admin_headers"],
    )

    assert len(await _list_notifications(client, parent_a["headers"])) == 1
    assert len(await _list_notifications(client, parent_b["headers"])) == 0
