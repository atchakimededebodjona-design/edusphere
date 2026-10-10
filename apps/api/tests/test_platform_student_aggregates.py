"""suivi plateforme — ajustement produit : agrégats élèves (COUNT) pour PLATFORM_OWNER et PARTNER_ADMIN.

Autorisé : total plateforme (tableau de bord), nombre d'élèves et d'élèves actifs PAR ÉCOLE
(/platform/schools ; /partner/schools pour les seules écoles du partenaire). Interdit : toute
donnée individuelle d'élève, par quelque route que ce soit — et sans jamais accorder
`students.read` (ni aucune permission scolaire) à ces deux rôles.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.core.permissions import get_all_permission_codes, get_scoped_permission_codes
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.users.models import User
from tests.conftest import register_school
from tests.pr17_helpers import auth, create_partner, create_platform_owner, enroll_school_as_partner

PLATFORM_SCHOOL_KEYS = {
    "id",
    "name",
    "organization_id",
    "slug",
    "created_at",
    "acquisition_source",
    "student_count",
    "active_student_count",
}
PARTNER_SCHOOL_KEYS = {
    "school_id",
    "school_name",
    "organization_id",
    "organization_name",
    "enrolled_at",
    "status",
    "student_count",
    "active_student_count",
}
DASHBOARD_KEYS = {
    "organization_count",
    "school_count",
    "user_count",
    "student_count",
    "partner_count",
    "enrollment_count",
}


async def _add_students(client: AsyncClient, admin_headers: dict[str, str], school_id: str, n: int) -> list[dict]:
    marker = f"Ident{uuid.uuid4().hex[:8]}"
    students = []
    for i in range(n):
        response = await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": f"{marker}M{i}",
                "first_name": f"{marker}Prenom{i}",
                "last_name": f"{marker}Nom{i}",
                "date_of_birth": "2014-03-0" + str(i + 1),
                "sex": "F" if i % 2 else "M",
            },
            headers=admin_headers,
        )
        assert response.status_code == 201, response.text
        students.append(response.json())
    return students


async def _set_status(student_id: str, status: str) -> None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(
            text("UPDATE students SET status = :s WHERE id = :id"), {"s": status, "id": uuid.UUID(student_id)}
        )
        await db.commit()


def _assert_no_individual_data(body_text: str, students: list[dict]) -> None:
    for student in students:
        for value in (student["id"], student["matricule"], student["first_name"], student["last_name"]):
            assert value not in body_text, value


async def _platform_school(client: AsyncClient, headers: dict[str, str], school_id: str, extra: str = "") -> dict:
    body = (await client.get(f"/api/v1/platform/schools?page=1&page_size=100{extra}", headers=headers)).json()
    return next(item for item in body["items"] if item["id"] == school_id)


# 1. Total plateforme agrégé via le tableau de bord ------------------------------------------------
async def test_platform_owner_reads_aggregated_platform_student_total(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "aggtotal")
    school = await register_school(client, "aggtotalschool")
    before = (await client.get("/api/v1/platform/dashboard", headers=owner["headers"])).json()
    students = await _add_students(client, auth(school["tokens"]["access_token"]), school["school"]["id"], 3)
    response = await client.get("/api/v1/platform/dashboard", headers=owner["headers"])
    assert response.status_code == 200
    after = response.json()
    assert set(after) == DASHBOARD_KEYS
    assert all(isinstance(value, int) for value in after.values())
    assert after["student_count"] == before["student_count"] + 3
    _assert_no_individual_data(response.text, students)


# 2. Nombre d'élèves d'une école précise via /platform/schools ------------------------------------
async def test_platform_owner_reads_per_school_student_counts(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "aggschool")
    school = await register_school(client, "aggschoolx")
    empty = await register_school(client, "aggschoolempty")
    students = await _add_students(client, auth(school["tokens"]["access_token"]), school["school"]["id"], 3)
    await _set_status(students[0]["id"], "WITHDRAWN")

    item = await _platform_school(client, owner["headers"], school["school"]["id"])
    assert set(item) == PLATFORM_SCHOOL_KEYS
    assert item["student_count"] == 3
    assert item["active_student_count"] == 2
    empty_item = await _platform_school(client, owner["headers"], empty["school"]["id"])
    assert (empty_item["student_count"], empty_item["active_student_count"]) == (0, 0)


# 3. Régression : GET /students toujours 403 -------------------------------------------------------
async def test_platform_owner_still_gets_403_on_students_list(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "agg403")
    school = await register_school(client, "agg403school")
    students = await _add_students(client, auth(school["tokens"]["access_token"]), school["school"]["id"], 1)
    response = await client.get(f"/api/v1/students?school_id={school['school']['id']}", headers=owner["headers"])
    assert response.status_code == 403
    _assert_no_individual_data(response.text, students)


# 4. Aucune fiche élève individuelle, par aucune route ---------------------------------------------
async def test_platform_owner_cannot_retrieve_any_individual_student(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "aggindiv")
    school = await register_school(client, "aggindivschool")
    students = await _add_students(client, auth(school["tokens"]["access_token"]), school["school"]["id"], 1)
    student_id = students[0]["id"]
    for path in (
        f"/api/v1/students/{student_id}",
        f"/api/v1/students/{student_id}/photo",
        f"/api/v1/students/{student_id}/documents",
        f"/api/v1/students/{student_id}/guardians",
        f"/api/v1/students/{student_id}/enrollments",
        f"/api/v1/students/{student_id}/exits",
        f"/api/v1/students/{student_id}/averages",
        f"/api/v1/students/{student_id}/attendance-summary?academic_term_id={uuid.uuid4()}",
        f"/api/v1/students/{student_id}/financial-summary",
        f"/api/v1/student-exits?school_id={school['school']['id']}",
        f"/api/v1/students?school_id={school['school']['id']}&search={students[0]['last_name']}",
    ):
        response = await client.get(path, headers=owner["headers"])
        assert response.status_code == 403, (path, response.status_code, response.text)
        _assert_no_individual_data(response.text, students)


# 5. Impossible de détourner l'agrégation pour obtenir une donnée individuelle ----------------------
async def test_aggregation_endpoint_cannot_be_narrowed_or_leak_individual_data(client: AsyncClient) -> None:
    """/platform/schools n'accepte que page/page_size : tout autre paramètre (filtre élève,
    recherche, statut, identifiant) est ignoré — la réponse est identique et ne contient que des
    entiers pour les agrégats. Même pour une école à UN seul élève, aucune donnée permettant de
    l'identifier (id, matricule, nom, prénom, date de naissance, sexe) n'apparaît jamais."""
    owner = await create_platform_owner(client, "aggabuse")
    school = await register_school(client, "aggabuseschool")
    other = await register_school(client, "aggabuseother")
    students = await _add_students(client, auth(school["tokens"]["access_token"]), school["school"]["id"], 1)
    await _add_students(client, auth(other["tokens"]["access_token"]), other["school"]["id"], 2)
    student = students[0]

    baseline = await _platform_school(client, owner["headers"], school["school"]["id"])
    assert (baseline["student_count"], baseline["active_student_count"]) == (1, 1)

    forged_params = [
        f"&student_id={student['id']}",
        f"&matricule={student['matricule']}",
        f"&search={student['last_name']}",
        f"&first_name={student['first_name']}",
        "&status=WITHDRAWN&sex=F&date_of_birth=2014-03-01",
        f"&school_id={other['school']['id']}&class_id={uuid.uuid4()}",
        "&fields=first_name,last_name,matricule&include=students&expand=students",
    ]
    for extra in forged_params:
        response = await client.get(f"/api/v1/platform/schools?page=1&page_size=100{extra}", headers=owner["headers"])
        assert response.status_code == 200, extra
        _assert_no_individual_data(response.text, students)
        assert "date_of_birth" not in response.text and "matricule" not in response.text
        item = next(i for i in response.json()["items"] if i["id"] == school["school"]["id"])
        assert item == baseline, extra  # jamais restreint ni enrichi par un paramètre client
        for entry in response.json()["items"]:
            assert set(entry) == PLATFORM_SCHOOL_KEYS
            assert type(entry["student_count"]) is int and type(entry["active_student_count"]) is int

    dashboard = await client.get(
        f"/api/v1/platform/dashboard?school_id={school['school']['id']}&student_id={student['id']}",
        headers=owner["headers"],
    )
    assert set(dashboard.json()) == DASHBOARD_KEYS
    _assert_no_individual_data(dashboard.text, students)


# 6. PARTNER_ADMIN : agrégats de SES écoles uniquement --------------------------------------------
async def test_partner_sees_aggregates_only_for_its_own_schools(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "aggpartner")
    partner_a = await create_partner(client, owner["headers"], "aggpartnera")
    partner_b = await create_partner(client, owner["headers"], "aggpartnerb")
    school_a = await enroll_school_as_partner(client, partner_a["headers"], "aggpartnerschoola")
    school_b = await enroll_school_as_partner(client, partner_b["headers"], "aggpartnerschoolb")
    students_a = await _add_students(client, school_a["admin_headers"], school_a["school"]["id"], 2)
    students_b = await _add_students(client, school_b["admin_headers"], school_b["school"]["id"], 3)
    await _set_status(students_a[1]["id"], "GRADUATED")

    forged = f"?partner_id={partner_b['partner']['id']}&school_id={school_b['school']['id']}"
    for suffix in ("", forged):
        response = await client.get(f"/api/v1/partner/schools{suffix}", headers=partner_a["headers"])
        assert response.status_code == 200
        body = response.json()
        assert [s["school_id"] for s in body] == [school_a["school"]["id"]]
        assert set(body[0]) == PARTNER_SCHOOL_KEYS
        assert (body[0]["student_count"], body[0]["active_student_count"]) == (2, 1)
        _assert_no_individual_data(response.text, students_a + students_b)

    body_b = (await client.get("/api/v1/partner/schools", headers=partner_b["headers"])).json()
    assert [(s["school_id"], s["student_count"]) for s in body_b] == [(school_b["school"]["id"], 3)]


# 7. PARTNER_ADMIN : jamais de donnée individuelle (régression) ------------------------------------
async def test_partner_never_sees_individual_students_of_its_own_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "aggpartnerind")
    partner = await create_partner(client, owner["headers"], "aggpartnerind")
    school = await enroll_school_as_partner(client, partner["headers"], "aggpartnerindschool")
    students = await _add_students(client, school["admin_headers"], school["school"]["id"], 1)
    for path in (
        f"/api/v1/students?school_id={school['school']['id']}",
        f"/api/v1/students/{students[0]['id']}",
        f"/api/v1/students/{students[0]['id']}/guardians",
        f"/api/v1/students/{students[0]['id']}/financial-summary",
        "/api/v1/partner/dashboard",
        "/api/v1/partner/accounts",
    ):
        response = await client.get(path, headers=partner["headers"])
        if path.startswith("/api/v1/partner/"):
            assert response.status_code == 200
        else:
            assert response.status_code in (403, 404), (path, response.status_code)
        _assert_no_individual_data(response.text, students)


# 8. Ni students.read ni aucune permission scolaire n'a été ajoutée -------------------------------
async def test_students_read_not_granted_to_owner_or_partner_catalog_and_effective() -> None:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                text(
                    "SELECT r.code, p.code FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                    "JOIN permissions p ON p.id = rp.permission_id "
                    "WHERE r.code IN ('PLATFORM_OWNER', 'PARTNER_ADMIN') AND p.code NOT LIKE 'platform.%' "
                    "AND p.code NOT LIKE 'partner.%'"
                )
            )
        ).all()
        students_read_holders = {
            row[0]
            for row in (
                await db.execute(
                    text(
                        "SELECT r.code FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                        "JOIN permissions p ON p.id = rp.permission_id WHERE p.code = 'students.read'"
                    )
                )
            ).all()
        }
    assert rows == []
    assert "PLATFORM_OWNER" not in students_read_holders
    assert "PARTNER_ADMIN" not in students_read_holders


async def test_students_read_absent_from_effective_permissions_of_owner_and_partner(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "aggperm")
    partner = await create_partner(client, owner["headers"], "aggperm")
    school = await enroll_school_as_partner(client, partner["headers"], "aggpermschool")
    for user_id in (owner["user_id"], partner["user_id"]):
        async with AsyncSessionLocal() as db:
            await apply_tenant_context(db, uuid.UUID(user_id))
            user = await db.get(User, uuid.UUID(user_id))
            assert user is not None
            all_codes = await get_all_permission_codes(db, user)
            scoped = await get_scoped_permission_codes(
                db,
                user,
                organization_id=uuid.UUID(school["organization"]["id"]),
                school_id=uuid.UUID(school["school"]["id"]),
            )
            await db.rollback()
        for codes in (all_codes, scoped):
            assert "students.read" not in codes and "students.manage" not in codes
            assert all(code.startswith(("platform.", "partner.")) for code in codes)
