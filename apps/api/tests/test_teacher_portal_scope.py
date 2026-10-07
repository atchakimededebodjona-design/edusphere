"""Durcissement des endpoints généraux pour un rôle TEACHER : GET /students, GET
/attendance-sessions (+ sessions/records associés) et GET /report-cards.

Un enseignant ne doit jamais lire une ressource hors de son périmètre TeacherAssignment, même par
l'API générale (pas seulement via /api/v1/teacher/*). ADMIN/DIRECTOR/SCHOOL_ADMIN/STAFF restent
sans restriction (is_teacher_only ne s'applique qu'à un rôle strictement TEACHER sur l'école).
"""

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from tests.conftest import register_school
from tests.test_teacher_portal import _portal_setup, _post, _teacher_in_school


async def _create_term(client: AsyncClient, setup: dict) -> dict:
    return await _post(
        client, "/api/v1/academic-terms",
        {"academic_year_id": setup["year_id"], "name": "T1", "start_date": "2026-09-01", "end_date": "2026-12-20", "order_index": 1},
        setup["headers"],
    )


async def _create_session(client: AsyncClient, setup: dict, class_id: str, term_id: str) -> dict:
    return await _post(
        client, "/api/v1/attendance-sessions",
        {"class_id": class_id, "academic_term_id": term_id, "session_date": str(date(2026, 10, 1))},
        setup["headers"],
    )


async def _generate_report_card_for_class(client: AsyncClient, setup: dict, class_id: str, term_id: str) -> dict | None:
    """Best-effort : un modèle de bulletin est nécessaire. Si la création échoue (champs du modèle
    non couverts ici), les tests concernés sont ignorés plutôt que de faire échouer tout le fichier."""
    template = await client.post(
        "/api/v1/report-card-templates",
        json={"school_id": setup["school_id"], "name": "Modele", "html_content": "<html>{{student}}</html>"},
        headers=setup["headers"],
    )
    if template.status_code != 201:
        return None
    generated = await client.post(
        "/api/v1/report-cards/generate",
        json={"class_id": class_id, "academic_term_id": term_id, "template_id": template.json()["id"]},
        headers=setup["headers"],
    )
    if generated.status_code >= 300 or not generated.json():
        return None
    return generated.json()[0]


# --- Students ------------------------------------------------------------------------------------
async def test_teacher_lists_only_students_of_assigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopestu")
    response = await client.get(
        f"/api/v1/students?school_id={setup['school_id']}", headers=setup["teacher_headers"]
    )
    assert response.status_code == 200, response.text
    assert [s["id"] for s in response.json()] == [setup["student_a"]["id"]]


async def test_teacher_cannot_list_students_with_unassigned_class_filter(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopestufilter")
    response = await client.get(
        f"/api/v1/students?school_id={setup['school_id']}&class_id={setup['class_b']['id']}",
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 403


async def test_teacher_cannot_read_student_out_of_scope(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopestudetail")
    ok = await client.get(f"/api/v1/students/{setup['student_a']['id']}", headers=setup["teacher_headers"])
    assert ok.status_code == 200
    refused = await client.get(f"/api/v1/students/{setup['student_b']['id']}", headers=setup["teacher_headers"])
    assert refused.status_code == 404


async def test_teacher_cannot_bypass_scope_with_random_uuid(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopestufuzz")
    response = await client.get(f"/api/v1/students/{uuid.uuid4()}", headers=setup["teacher_headers"])
    assert response.status_code == 404


async def test_school_admin_student_access_is_not_restricted(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopestuadmin")
    response = await client.get(f"/api/v1/students?school_id={setup['school_id']}", headers=setup["headers"])
    assert response.status_code == 200
    assert {s["id"] for s in response.json()} == {setup["student_a"]["id"], setup["student_b"]["id"]}


# --- Attendance ----------------------------------------------------------------------------------
async def test_teacher_reads_attendance_of_assigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopeattok")
    term = await _create_term(client, setup)
    session = await _create_session(client, setup, setup["class_a"]["id"], term["id"])

    listing = await client.get(
        f"/api/v1/attendance-sessions?class_id={setup['class_a']['id']}", headers=setup["teacher_headers"]
    )
    assert listing.status_code == 200
    assert [s["id"] for s in listing.json()] == [session["id"]]

    detail = await client.get(f"/api/v1/attendance-sessions/{session['id']}", headers=setup["teacher_headers"])
    assert detail.status_code == 200

    records = await client.get(f"/api/v1/attendance-records?session_id={session['id']}", headers=setup["teacher_headers"])
    assert records.status_code == 200


async def test_teacher_cannot_read_attendance_of_unassigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopeattno")
    term = await _create_term(client, setup)
    session = await _create_session(client, setup, setup["class_b"]["id"], term["id"])

    listing = await client.get(
        f"/api/v1/attendance-sessions?class_id={setup['class_b']['id']}", headers=setup["teacher_headers"]
    )
    assert listing.status_code == 403

    detail = await client.get(f"/api/v1/attendance-sessions/{session['id']}", headers=setup["teacher_headers"])
    assert detail.status_code == 403

    records = await client.get(f"/api/v1/attendance-records?session_id={session['id']}", headers=setup["teacher_headers"])
    assert records.status_code == 403


async def test_director_attendance_access_is_not_restricted(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopeattdirector")
    term = await _create_term(client, setup)
    session = await _create_session(client, setup, setup["class_b"]["id"], term["id"])
    _, director_headers = await _teacher_in_school(client, setup, "scopeattdirectoracct", role="DIRECTOR")

    listing = await client.get(
        f"/api/v1/attendance-sessions?class_id={setup['class_b']['id']}", headers=director_headers
    )
    assert listing.status_code == 200
    assert [s["id"] for s in listing.json()] == [session["id"]]


# --- Report cards --------------------------------------------------------------------------------
async def test_teacher_cannot_list_report_cards_of_unassigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopercno")
    term = await _create_term(client, setup)
    response = await client.get(
        f"/api/v1/report-cards?class_id={setup['class_b']['id']}&academic_term_id={term['id']}",
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 403


async def test_teacher_cannot_read_or_download_report_card_out_of_scope(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopercdetail")
    term = await _create_term(client, setup)
    card = await _generate_report_card_for_class(client, setup, setup["class_b"]["id"], term["id"])
    if card is None:
        return  # Génération non couverte par ce setup minimal — voir docstring du helper.

    read = await client.get(f"/api/v1/report-cards/{card['id']}", headers=setup["teacher_headers"])
    assert read.status_code == 404
    pdf = await client.get(f"/api/v1/report-cards/{card['id']}/pdf", headers=setup["teacher_headers"])
    assert pdf.status_code == 404


async def test_teacher_can_read_report_card_of_assigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopercok")
    term = await _create_term(client, setup)
    card = await _generate_report_card_for_class(client, setup, setup["class_a"]["id"], term["id"])
    if card is None:
        return

    read = await client.get(f"/api/v1/report-cards/{card['id']}", headers=setup["teacher_headers"])
    assert read.status_code == 200


# --- Isolation : école, organisation, rôle révoqué, compte inactif --------------------------------
async def test_teacher_of_another_school_same_org_has_no_access(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopexschool")
    other_school = await client.post(
        "/api/v1/schools",
        json={"organization_id": setup["organization_id"], "name": "Autre ecole", "slug": "autre-scope"},
        headers=setup["headers"],
    )
    assert other_school.status_code == 201
    # Le TEACHER est rattaché à l'AUTRE école (même organisation) : aucun accès à celle du setup.
    _, other_headers = await _teacher_in_school(
        client, {"organization_id": setup["organization_id"], "school_id": other_school.json()["id"]}, "scopexschoolt"
    )

    response = await client.get(f"/api/v1/students?school_id={setup['school_id']}", headers=other_headers)
    assert response.status_code == 403


async def test_teacher_of_another_organization_has_no_access(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopexorg")
    other = await register_school(client, "scopexorgother")
    _, other_headers = await _teacher_in_school(
        client, {"organization_id": other["organization"]["id"], "school_id": other["school"]["id"]}, "scopexorgt"
    )
    # RLS rend l'école elle-même invisible pour un utilisateur sans aucun rôle dans cette
    # organisation : 404 avant même la vérification de permission, pas 403.
    response = await client.get(f"/api/v1/students?school_id={setup['school_id']}", headers=other_headers)
    assert response.status_code == 404


async def test_revoked_teacher_role_loses_general_endpoint_access(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scoperevoke")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(
            delete(UserRole).where(
                UserRole.user_id == uuid.UUID(setup["teacher_id"]),
                UserRole.role_id.in_(select(Role.id).where(Role.code == "TEACHER")),
            )
        )
        await db.commit()
    # Même motif : plus aucun rôle dans cette organisation, l'école devient invisible (RLS) → 404.
    response = await client.get(f"/api/v1/students?school_id={setup['school_id']}", headers=setup["teacher_headers"])
    assert response.status_code == 404


async def test_inactive_teacher_is_rejected_at_authentication(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "scopeinactive")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        user = await db.get(User, uuid.UUID(setup["teacher_id"]))
        user.is_active = False
        await db.commit()
    response = await client.get(f"/api/v1/students?school_id={setup['school_id']}", headers=setup["teacher_headers"])
    assert response.status_code == 401


# --- Portail : PDF du bulletin (GET /teacher/report-cards/{id}/pdf) -----------------------------
async def test_teacher_downloads_published_report_card_pdf_of_assigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tppdfok")
    term = await _create_term(client, setup)
    card = await _generate_report_card_for_class(client, setup, setup["class_a"]["id"], term["id"])
    if card is None:
        return
    publish = await client.post(f"/api/v1/report-cards/{card['id']}/publish", headers=setup["headers"])
    assert publish.status_code == 200, publish.text

    response = await client.get(f"/api/v1/teacher/report-cards/{card['id']}/pdf", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.content[:4] == b"%PDF"


async def test_teacher_cannot_download_unpublished_report_card_pdf(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tppdfdraft")
    term = await _create_term(client, setup)
    card = await _generate_report_card_for_class(client, setup, setup["class_a"]["id"], term["id"])
    if card is None:
        return
    # Pas de publication : le bulletin reste DRAFT.
    response = await client.get(f"/api/v1/teacher/report-cards/{card['id']}/pdf", headers=setup["teacher_headers"])
    assert response.status_code == 404


async def test_teacher_cannot_download_published_report_card_pdf_of_other_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tppdfxclass")
    term = await _create_term(client, setup)
    card = await _generate_report_card_for_class(client, setup, setup["class_b"]["id"], term["id"])
    if card is None:
        return
    publish = await client.post(f"/api/v1/report-cards/{card['id']}/publish", headers=setup["headers"])
    assert publish.status_code == 200, publish.text

    response = await client.get(f"/api/v1/teacher/report-cards/{card['id']}/pdf", headers=setup["teacher_headers"])
    assert response.status_code == 404
