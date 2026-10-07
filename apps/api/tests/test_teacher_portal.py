"""Portail enseignant : périmètre serveur (TeacherAssignment), accès par rôle et isolation.

Un enseignant ne voit que ses classes, ses élèves et ses matières ; toute ressource hors périmètre
répond 404 (comme une ressource inexistante). Les endpoints d'écriture existants (présences, notes)
refusent déjà les classes/matières non affectées : on le vérifie ici aussi.
"""

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import delete, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.rbac.models import Role, UserRole
from tests.conftest import assign_role, create_platform_admin, register_school

PASSWORD = "SuperSecret123"


async def _login(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _post(client: AsyncClient, path: str, payload: dict, headers: dict) -> dict:
    response = await client.post(path, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _school_with_two_classes(client: AsyncClient, prefix: str) -> dict:
    """Une école, deux classes (A et B), deux matières. Classe A : Maths + Français ; classe B : Histoire."""
    data = await register_school(client, prefix)
    headers = await _login(client, data["user"]["email"])
    school_id = data["school"]["id"]
    year = await _post(
        client, "/api/v1/academic-years",
        {"school_id": school_id, "name": "2026-2027", "start_date": "2026-09-01", "end_date": "2027-06-30", "is_current": True},
        headers,
    )
    level = await _post(client, "/api/v1/education-levels", {"school_id": school_id, "name": "CM2"}, headers)
    maths = await _post(client, "/api/v1/subjects", {"school_id": school_id, "name": "Mathematiques"}, headers)
    francais = await _post(client, "/api/v1/subjects", {"school_id": school_id, "name": "Francais"}, headers)
    histoire = await _post(client, "/api/v1/subjects", {"school_id": school_id, "name": "Histoire"}, headers)
    class_a = await _post(
        client, "/api/v1/classes",
        {"academic_year_id": year["id"], "education_level_id": level["id"], "name": "CM2-A"}, headers,
    )
    class_b = await _post(
        client, "/api/v1/classes",
        {"academic_year_id": year["id"], "education_level_id": level["id"], "name": "CM2-B"}, headers,
    )
    cs_maths = await _post(client, f"/api/v1/classes/{class_a['id']}/subjects", {"subject_id": maths["id"], "coefficient": 2}, headers)
    cs_francais = await _post(client, f"/api/v1/classes/{class_a['id']}/subjects", {"subject_id": francais["id"]}, headers)
    cs_histoire_b = await _post(client, f"/api/v1/classes/{class_b['id']}/subjects", {"subject_id": histoire["id"]}, headers)
    return {
        "data": data,
        "headers": headers,
        "school_id": school_id,
        "organization_id": data["organization"]["id"],
        "year_id": year["id"],
        "level_id": level["id"],
        "class_a": class_a,
        "class_b": class_b,
        "maths": maths,
        "francais": francais,
        "histoire": histoire,
        "cs_maths": cs_maths,
        "cs_francais": cs_francais,
        "cs_histoire_b": cs_histoire_b,
    }


async def _teacher_in_school(client: AsyncClient, setup: dict, prefix: str, role: str = "TEACHER") -> tuple[str, dict]:
    other = await register_school(client, f"{prefix}acct")
    await assign_role(other["user"]["id"], role, organization_id=setup["organization_id"], school_id=setup["school_id"])
    headers = await _login(client, other["user"]["email"])
    return other["user"]["id"], headers


async def _student_in_class(client: AsyncClient, setup: dict, class_id: str, last_name: str) -> dict:
    student = await _post(
        client, "/api/v1/students",
        {
            "school_id": setup["school_id"], "matricule": f"M{uuid.uuid4().hex[:10]}", "first_name": "Eleve", "last_name": last_name,
            "date_of_birth": "2014-03-04", "sex": "F",
        },
        setup["headers"],
    )
    await _post(
        client, f"/api/v1/students/{student['id']}/enrollments",
        {"class_id": class_id, "academic_year_id": setup["year_id"], "enrollment_date": "2026-09-01"},
        setup["headers"],
    )
    return student


async def _assign_teacher(client: AsyncClient, setup: dict, teacher_id: str, class_id: str, subject_id: str) -> None:
    await _post(client, f"/api/v1/classes/{class_id}/teachers", {"user_id": teacher_id, "subject_id": subject_id}, setup["headers"])


async def _portal_setup(client: AsyncClient, prefix: str) -> dict:
    """Affectations : enseignant T sur CM2-A (Maths, Français). Élèves : un en A, un en B."""
    setup = await _school_with_two_classes(client, prefix)
    teacher_id, teacher_headers = await _teacher_in_school(client, setup, f"{prefix}t")
    await _assign_teacher(client, setup, teacher_id, setup["class_a"]["id"], setup["maths"]["id"])
    await _assign_teacher(client, setup, teacher_id, setup["class_a"]["id"], setup["francais"]["id"])
    student_a = await _student_in_class(client, setup, setup["class_a"]["id"], f"{prefix}Alpha")
    student_b = await _student_in_class(client, setup, setup["class_b"]["id"], f"{prefix}Beta")
    setup.update({"teacher_id": teacher_id, "teacher_headers": teacher_headers, "student_a": student_a, "student_b": student_b})
    return setup


# --- Périmètre : classes, élèves, matières -----------------------------------------------------
async def test_teacher_sees_own_class_only(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpclass")
    response = await client.get("/api/v1/teacher/classes", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    assert [c["id"] for c in response.json()] == [setup["class_a"]["id"]]


async def test_teacher_cannot_open_unassigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpotherclass")
    response = await client.get(f"/api/v1/teacher/classes/{setup['class_b']['id']}", headers=setup["teacher_headers"])
    assert response.status_code == 404


async def test_teacher_sees_students_of_own_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpstudents")
    response = await client.get(f"/api/v1/teacher/classes/{setup['class_a']['id']}/students", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    assert [s["id"] for s in response.json()] == [setup["student_a"]["id"]]


async def test_teacher_cannot_see_students_of_unassigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpstudentsb")
    headers = setup["teacher_headers"]
    class_b = setup["class_b"]["id"]

    listing = await client.get(f"/api/v1/teacher/classes/{class_b}/students", headers=headers)
    assert listing.status_code == 404

    everyone = await client.get("/api/v1/teacher/students", headers=headers)
    assert setup["student_b"]["id"] not in {s["id"] for s in everyone.json()}

    detail = await client.get(f"/api/v1/teacher/students/{setup['student_b']['id']}", headers=headers)
    assert detail.status_code == 404


async def test_teacher_sees_own_subjects_only(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpsubjects")
    response = await client.get(f"/api/v1/teacher/classes/{setup['class_a']['id']}", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    subject_ids = {s["subject_id"] for s in response.json()["subjects"]}
    assert subject_ids == {setup["maths"]["id"], setup["francais"]["id"]}
    assert setup["histoire"]["id"] not in subject_ids


async def test_teacher_dashboard_counts_are_scoped(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpdash")
    response = await client.get("/api/v1/teacher/dashboard", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["class_count"] == 1
    assert body["subject_count"] == 2
    assert body["student_count"] == 1


async def test_student_detail_is_read_only_summary(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpdetail")
    response = await client.get(f"/api/v1/teacher/students/{setup['student_a']['id']}", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["classes"] == [{"class_id": setup["class_a"]["id"], "class_name": "CM2-A"}]
    assert "address" not in body and "guardians" not in body and "documents" not in body


# --- Écritures existantes : refus hors affectation ---------------------------------------------
async def test_teacher_cannot_grade_unassigned_subject(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpgradeno")
    term = await _post(
        client, "/api/v1/academic-terms",
        {"academic_year_id": setup["year_id"], "name": "T1", "start_date": "2026-09-01", "end_date": "2026-12-20", "order_index": 1},
        setup["headers"],
    )
    atype = await _post(client, "/api/v1/assessment-types", {"school_id": setup["school_id"], "name": "Devoir", "weight": 1}, setup["headers"])
    response = await client.post(
        "/api/v1/assessments",
        json={
            "class_subject_id": setup["cs_histoire_b"]["id"],
            "academic_term_id": term["id"],
            "assessment_type_id": atype["id"],
            "name": "Devoir histoire",
            "max_score": 20,
            "assessment_date": str(date(2026, 10, 1)),
        },
        headers=setup["teacher_headers"],
    )
    assert response.status_code in (403, 404), response.text


async def test_teacher_cannot_take_attendance_of_unassigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpattno")
    term = await _post(
        client, "/api/v1/academic-terms",
        {"academic_year_id": setup["year_id"], "name": "T1", "start_date": "2026-09-01", "end_date": "2026-12-20", "order_index": 1},
        setup["headers"],
    )
    response = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": setup["class_b"]["id"], "academic_term_id": term["id"], "session_date": str(date(2026, 10, 1))},
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 403, response.text


async def test_teacher_can_take_attendance_of_own_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpattyes")
    term = await _post(
        client, "/api/v1/academic-terms",
        {"academic_year_id": setup["year_id"], "name": "T1", "start_date": "2026-09-01", "end_date": "2026-12-20", "order_index": 1},
        setup["headers"],
    )
    session = await client.post(
        "/api/v1/attendance-sessions",
        json={"class_id": setup["class_a"]["id"], "academic_term_id": term["id"], "session_date": str(date(2026, 10, 1))},
        headers=setup["teacher_headers"],
    )
    assert session.status_code == 201, session.text
    listing = await client.get(
        f"/api/v1/teacher/classes/{setup['class_a']['id']}/attendance-sessions", headers=setup["teacher_headers"]
    )
    assert listing.status_code == 200
    assert [s["id"] for s in listing.json()] == [session.json()["id"]]

    other = await client.get(
        f"/api/v1/teacher/classes/{setup['class_b']['id']}/attendance-sessions", headers=setup["teacher_headers"]
    )
    assert other.status_code == 404


# --- Bulletins : périmètre et publication ------------------------------------------------------
async def test_teacher_cannot_read_report_cards_of_other_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpreport")
    response = await client.get(
        f"/api/v1/teacher/classes/{setup['class_b']['id']}/report-cards", headers=setup["teacher_headers"]
    )
    assert response.status_code == 404
    pdf = await client.get(f"/api/v1/teacher/report-cards/{uuid.uuid4()}/pdf", headers=setup["teacher_headers"])
    assert pdf.status_code == 404


# --- Rôles : seuls les enseignants accèdent au portail -----------------------------------------
async def test_staff_cannot_access_teacher_portal(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpstaff")
    _, staff_headers = await _teacher_in_school(client, setup, "tpstaffacct", role="STAFF")
    assert (await client.get("/api/v1/teacher/me", headers=staff_headers)).status_code == 403
    assert (await client.get("/api/v1/teacher/classes", headers=staff_headers)).status_code == 403


async def test_school_admin_and_director_are_not_limited_by_teacher_scope(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpadmin")
    # Le SCHOOL_ADMIN de l'école garde la vue complète de l'administration (non limitée par le périmètre).
    listing = await client.get(f"/api/v1/classes?school_id={setup['school_id']}", headers=setup["headers"])
    assert {c["id"] for c in listing.json()} == {setup["class_a"]["id"], setup["class_b"]["id"]}
    # ... mais n'a pas accès au portail enseignant (rôle TEACHER requis).
    assert (await client.get("/api/v1/teacher/classes", headers=setup["headers"])).status_code == 403

    _, director_headers = await _teacher_in_school(client, setup, "tpdirector", role="DIRECTOR")
    assert (await client.get("/api/v1/teacher/dashboard", headers=director_headers)).status_code == 403


async def test_platform_admin_cannot_access_teacher_portal(client: AsyncClient) -> None:
    admin = await create_platform_admin(client, "tpplatform")
    headers = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}
    assert (await client.get("/api/v1/teacher/me", headers=headers)).status_code == 403


async def test_platform_admin_with_teacher_role_is_refused(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpplatteach")
    admin = await create_platform_admin(client, "tpplatteachadm")
    await assign_role(admin["user_id"], "TEACHER", organization_id=setup["organization_id"], school_id=setup["school_id"])
    headers = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}
    assert (await client.get("/api/v1/teacher/classes", headers=headers)).status_code == 403


async def test_revoked_teacher_role_loses_portal_access(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tprevoke")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(
            delete(UserRole).where(
                UserRole.user_id == uuid.UUID(setup["teacher_id"]),
                UserRole.role_id.in_(select(Role.id).where(Role.code == "TEACHER")),
            )
        )
        await db.commit()
    assert (await client.get("/api/v1/teacher/classes", headers=setup["teacher_headers"])).status_code == 403


# --- Isolation : école, organisation, tenant ---------------------------------------------------
async def test_teacher_role_in_other_school_gives_no_scope_here(client: AsyncClient) -> None:
    """Enseignant TEACHER de l'école 2 (même organisation) : aucun accès aux classes de l'école 1."""
    setup = await _portal_setup(client, "tpxschool")
    other_school = await client.post(
        "/api/v1/schools",
        json={"organization_id": setup["organization_id"], "name": "Autre ecole", "slug": "autre-tp"},
        headers=setup["headers"],
    )
    assert other_school.status_code == 201, other_school.text
    other_teacher, other_headers = await _teacher_in_school(client, setup, "tpxschoolt")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(delete(UserRole).where(UserRole.user_id == uuid.UUID(other_teacher)))
        db.add(UserRole(id=uuid.uuid4(), user_id=uuid.UUID(other_teacher), role_id=(await db.execute(select(Role.id).where(Role.code == "TEACHER"))).scalar_one(), organization_id=setup["organization_id"], school_id=uuid.UUID(other_school.json()["id"])))
        await db.commit()

    assert (await client.get("/api/v1/teacher/classes", headers=other_headers)).json() == []
    assert (await client.get(f"/api/v1/teacher/classes/{setup['class_a']['id']}", headers=other_headers)).status_code == 404


async def test_teacher_of_another_organization_cannot_see_classes(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpxorg")
    other = await register_school(client, "tpxorgother")
    other_teacher, other_headers = await _teacher_in_school(client, {**setup, "organization_id": other["organization"]["id"], "school_id": other["school"]["id"]}, "tpxorgt")
    assert (await client.get("/api/v1/teacher/classes", headers=other_headers)).json() == []
    assert (await client.get(f"/api/v1/teacher/classes/{setup['class_a']['id']}", headers=other_headers)).status_code == 404
    assert (await client.get(f"/api/v1/teacher/students/{setup['student_a']['id']}", headers=other_headers)).status_code == 404


async def test_teacher_me_lists_only_teacher_schools(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpme")
    response = await client.get("/api/v1/teacher/me", headers=setup["teacher_headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["roles"] == ["TEACHER"]
    assert [s["id"] for s in body["schools"]] == [setup["school_id"]]
    assert "is_platform_admin" not in body


async def test_teacher_cannot_create_students_from_portal(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpnocreate")
    response = await client.post(
        "/api/v1/students",
        json={"school_id": setup["school_id"], "matricule": "MX-NOPE", "first_name": "X", "last_name": "Y", "date_of_birth": "2014-01-01", "sex": "M"},
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 403


# --- Moyennes : réutilise grades/router.py (déjà scopé enseignant), pas de nouvelle logique ----
async def test_teacher_reads_class_performance_for_assigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpperfok")
    term = await _post(
        client, "/api/v1/academic-terms",
        {"academic_year_id": setup["year_id"], "name": "T1", "start_date": "2026-09-01", "end_date": "2026-12-20", "order_index": 1},
        setup["headers"],
    )
    response = await client.get(
        f"/api/v1/classes/{setup['class_a']['id']}/performance?academic_term_id={term['id']}",
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["class_id"] == setup["class_a"]["id"]


async def test_teacher_cannot_read_class_performance_for_unassigned_class(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpperfno")
    term = await _post(
        client, "/api/v1/academic-terms",
        {"academic_year_id": setup["year_id"], "name": "T1", "start_date": "2026-09-01", "end_date": "2026-12-20", "order_index": 1},
        setup["headers"],
    )
    response = await client.get(
        f"/api/v1/classes/{setup['class_b']['id']}/performance?academic_term_id={term['id']}",
        headers=setup["teacher_headers"],
    )
    assert response.status_code == 403


async def test_teacher_reads_student_averages_scoped_to_assigned_subject(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpavgok")
    response = await client.get(
        f"/api/v1/students/{setup['student_a']['id']}/averages", headers=setup["teacher_headers"]
    )
    assert response.status_code == 200, response.text


async def test_teacher_cannot_read_averages_of_student_out_of_scope(client: AsyncClient) -> None:
    setup = await _portal_setup(client, "tpavgno")
    response = await client.get(
        f"/api/v1/students/{setup['student_b']['id']}/averages", headers=setup["teacher_headers"]
    )
    # L'élève existe (404 impossible) mais ses moyennes de matière/générale sont vides : aucune
    # matière affectée dans sa classe, et l'enseignant n'y est pas affecté (voir
    # grades/router.py::get_student_averages).
    assert response.status_code == 200
    body = response.json()
    assert body["subject_averages"] == []
    assert body["term_averages"] == []
