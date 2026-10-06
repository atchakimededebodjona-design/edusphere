import uuid
from datetime import date

from httpx import AsyncClient

from app.db.session import AsyncSessionLocal
from app.modules.users.models import User
from tests.conftest import assign_role, create_platform_admin, register_school


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _create_year(client: AsyncClient, headers: dict, school_id: str) -> dict:
    response = await client.post(
        "/api/v1/academic-years",
        json={
            "school_id": school_id,
            "name": "2026-2027",
            "start_date": str(date(2026, 9, 1)),
            "end_date": str(date(2027, 6, 30)),
            "is_current": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_level(client: AsyncClient, headers: dict, school_id: str, name: str = "CE1") -> dict:
    response = await client.post(
        "/api/v1/education-levels", json={"school_id": school_id, "name": name}, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_subject(client: AsyncClient, headers: dict, school_id: str, name: str = "Mathématiques") -> dict:
    response = await client.post("/api/v1/subjects", json={"school_id": school_id, "name": name}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_class(client: AsyncClient, headers: dict, year_id: str, level_id: str, name: str = "A") -> dict:
    response = await client.post(
        "/api/v1/classes",
        json={"academic_year_id": year_id, "education_level_id": level_id, "name": name},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_full_academic_setup_flow(client: AsyncClient) -> None:
    data = await register_school(client, "acadflow")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    year = await _create_year(client, headers, school_id)
    level = await _create_level(client, headers, school_id)
    subject = await _create_subject(client, headers, school_id)
    room_response = await client.post("/api/v1/rooms", json={"school_id": school_id, "name": "Salle 1"}, headers=headers)
    assert room_response.status_code == 201

    school_class = await _create_class(client, headers, year["id"], level["id"])
    assert school_class["education_level_id"] == level["id"]

    class_subject_response = await client.post(
        f"/api/v1/classes/{school_class['id']}/subjects",
        json={"subject_id": subject["id"], "coefficient": 3},
        headers=headers,
    )
    assert class_subject_response.status_code == 201
    assert class_subject_response.json()["coefficient"] == 3

    list_response = await client.get(f"/api/v1/classes/{school_class['id']}/subjects", headers=headers)
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


async def test_academic_year_duplicate_name_conflicts(client: AsyncClient) -> None:
    data = await register_school(client, "acadyear")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    await _create_year(client, headers, school_id)
    response = await client.post(
        "/api/v1/academic-years",
        json={
            "school_id": school_id,
            "name": "2026-2027",
            "start_date": str(date(2026, 9, 1)),
            "end_date": str(date(2027, 6, 30)),
        },
        headers=headers,
    )
    assert response.status_code == 409


async def test_class_requires_level_from_same_school(client: AsyncClient) -> None:
    school_a = await register_school(client, "acadlevela")
    school_b = await register_school(client, "acadlevelb")
    token_a = await _login(client, school_a["user"]["email"])
    token_b = await _login(client, school_b["user"]["email"])
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    year_a = await _create_year(client, headers_a, school_a["school"]["id"])
    level_b = await _create_level(client, headers_b, school_b["school"]["id"])

    response = await client.post(
        "/api/v1/classes",
        json={"academic_year_id": year_a["id"], "education_level_id": level_b["id"], "name": "A"},
        headers=headers_a,
    )
    assert response.status_code == 400


async def test_teacher_only_sees_assigned_classes(client: AsyncClient) -> None:
    data = await register_school(client, "acadteacher")
    token_admin = await _login(client, data["user"]["email"])
    headers_admin = {"Authorization": f"Bearer {token_admin}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    year = await _create_year(client, headers_admin, school_id)
    level = await _create_level(client, headers_admin, school_id)
    subject = await _create_subject(client, headers_admin, school_id)

    class_assigned = await _create_class(client, headers_admin, year["id"], level["id"], name="A")
    class_not_assigned = await _create_class(client, headers_admin, year["id"], level["id"], name="B")

    class_subject_response = await client.post(
        f"/api/v1/classes/{class_assigned['id']}/subjects",
        json={"subject_id": subject["id"]},
        headers=headers_admin,
    )
    assert class_subject_response.status_code == 201

    teacher_data = await register_school(client, "acadteacher-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    teacher_email = teacher_data["user"]["email"]
    await assign_role(teacher_user_id, "TEACHER", organization_id=organization_id, school_id=school_id)

    assign_response = await client.post(
        f"/api/v1/classes/{class_assigned['id']}/teachers",
        json={"user_id": teacher_user_id, "subject_id": subject["id"]},
        headers=headers_admin,
    )
    assert assign_response.status_code == 201

    # L'admin voit toujours les deux classes.
    admin_list = await client.get(f"/api/v1/classes?school_id={school_id}", headers=headers_admin)
    assert {c["id"] for c in admin_list.json()} == {class_assigned["id"], class_not_assigned["id"]}

    # L'enseignant ne voit que la classe où il est affecté.
    token_teacher = await _login(client, teacher_email)
    headers_teacher = {"Authorization": f"Bearer {token_teacher}"}
    teacher_list = await client.get(f"/api/v1/classes?school_id={school_id}", headers=headers_teacher)
    assert teacher_list.status_code == 200
    assert {c["id"] for c in teacher_list.json()} == {class_assigned["id"]}

    # L'enseignant ne peut pas gérer (créer un niveau, etc.) — lecture seule.
    manage_attempt = await client.post(
        "/api/v1/education-levels", json={"school_id": school_id, "name": "CM2"}, headers=headers_teacher
    )
    assert manage_attempt.status_code == 403


async def test_academics_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "acadisoa")
    school_b = await register_school(client, "acadisob")
    token_a = await _login(client, school_a["user"]["email"])
    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    subject_b = await _create_subject(client, headers_b, school_b["school"]["id"])
    year_b = await _create_year(client, headers_b, school_b["school"]["id"])

    # A ne peut pas lister les matières de B — RLS rend la ligne `schools` invisible avant
    # même le contrôle de permission applicatif (même comportement que get_school en Phase 1).
    list_response = await client.get(f"/api/v1/subjects?school_id={school_b['school']['id']}", headers=headers_a)
    assert list_response.status_code == 404

    # A ne peut pas lister les périodes d'une VRAIE année scolaire de B (RLS + contrôle
    # applicatif) même en connaissant son id.
    terms_response = await client.get(f"/api/v1/academic-terms?academic_year_id={year_b['id']}", headers=headers_a)
    assert terms_response.status_code == 404

    # A ne peut pas créer une classe dans l'année scolaire de B.
    level_a = await _create_level(client, headers_a, school_a["school"]["id"])
    create_response = await client.post(
        "/api/v1/classes",
        json={"academic_year_id": year_b["id"], "education_level_id": level_a["id"], "name": "A"},
        headers=headers_a,
    )
    assert create_response.status_code == 404

    assert subject_b["name"] == "Mathématiques"


# --- Affectation des enseignants : règles de validation backend ---------------------------------
async def _school_setup(client: AsyncClient, prefix: str) -> dict:
    """Organisation + école + admin + année/niveau/matière, avec une classe et la matière attachée."""
    data = await register_school(client, prefix)
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    year = await _create_year(client, headers, school_id)
    level = await _create_level(client, headers, school_id)
    subject = await _create_subject(client, headers, school_id)
    school_class = await _create_class(client, headers, year["id"], level["id"])
    attached = await client.post(
        f"/api/v1/classes/{school_class['id']}/subjects", json={"subject_id": subject["id"]}, headers=headers
    )
    assert attached.status_code == 201, attached.text
    return {
        "headers": headers,
        "school_id": school_id,
        "organization_id": data["organization"]["id"],
        "year_id": year["id"],
        "level_id": level["id"],
        "class_id": school_class["id"],
        "subject_id": subject["id"],
    }


async def _user_with_role(client: AsyncClient, prefix: str, role: str, org_id: str, school_id: str | None) -> str:
    data = await register_school(client, prefix)
    user_id = data["user"]["id"]
    await assign_role(user_id, role, organization_id=org_id, school_id=school_id)
    return user_id


async def _assign(client: AsyncClient, setup: dict, user_id: str):
    return await client.post(
        f"/api/v1/classes/{setup['class_id']}/teachers",
        json={"user_id": user_id, "subject_id": setup["subject_id"]},
        headers=setup["headers"],
    )


async def _assignments(client: AsyncClient, class_id: str, headers: dict) -> list:
    response = await client.get(f"/api/v1/classes/{class_id}/teachers", headers=headers)
    assert response.status_code == 200
    return response.json()


async def test_assign_valid_school_teacher_succeeds(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasgood")
    teacher = await _user_with_role(client, "tasgoodt", "TEACHER", setup["organization_id"], setup["school_id"])

    response = await _assign(client, setup, teacher)
    assert response.status_code == 201, response.text
    assert response.json()["user_id"] == teacher
    assert len(await _assignments(client, setup["class_id"], setup["headers"])) == 1


async def test_assign_rejects_non_teacher_role(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasrole")
    school_admin = await _user_with_role(client, "tasroleadm", "SCHOOL_ADMIN", setup["organization_id"], setup["school_id"])

    response = await _assign(client, setup, school_admin)
    assert response.status_code == 400
    assert await _assignments(client, setup["class_id"], setup["headers"]) == []


async def test_assign_rejects_teacher_of_another_school_same_organization(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasxschool")
    other_school = await client.post(
        "/api/v1/schools",
        json={"organization_id": setup["organization_id"], "name": "Autre ecole", "slug": "autre"},
        headers=setup["headers"],
    )
    assert other_school.status_code == 201, other_school.text
    teacher = await _user_with_role(client, "tasxschoolt", "TEACHER", setup["organization_id"], other_school.json()["id"])

    response = await _assign(client, setup, teacher)
    assert response.status_code == 400
    assert await _assignments(client, setup["class_id"], setup["headers"]) == []


async def test_assign_rejects_teacher_of_another_organization(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasxorg")
    other = await register_school(client, "tasxorgother")
    teacher = await _user_with_role(client, "tasxorgt", "TEACHER", other["organization"]["id"], other["school"]["id"])

    response = await _assign(client, setup, teacher)
    assert response.status_code == 400
    assert await _assignments(client, setup["class_id"], setup["headers"]) == []


async def test_assign_rejects_org_wide_teacher_role_without_school(client: AsyncClient) -> None:
    """Le rôle TEACHER doit être rattaché à l'école de la classe (pas un rôle org-wide, school NULL)."""
    setup = await _school_setup(client, "tasorgwide")
    teacher = await _user_with_role(client, "tasorgwidet", "TEACHER", setup["organization_id"], None)

    response = await _assign(client, setup, teacher)
    assert response.status_code == 400


async def test_assign_rejects_platform_admin_even_with_teacher_role(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasplat")
    platform = await create_platform_admin(client, "tasplatadmin")
    await assign_role(platform["user_id"], "TEACHER", organization_id=setup["organization_id"], school_id=setup["school_id"])

    response = await _assign(client, setup, platform["user_id"])
    assert response.status_code == 400


async def test_assign_rejects_inactive_teacher(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasinactive")
    teacher = await _user_with_role(client, "tasinactivet", "TEACHER", setup["organization_id"], setup["school_id"])
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uuid.UUID(teacher))
        user.is_active = False
        await db.commit()

    response = await _assign(client, setup, teacher)
    assert response.status_code == 400


async def test_assign_rejects_unknown_user(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasunknown")
    response = await _assign(client, setup, str(uuid.uuid4()))
    assert response.status_code == 400


async def test_assign_rejects_subject_not_attached_to_class(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasnotattached")
    teacher = await _user_with_role(client, "tasnotattachedt", "TEACHER", setup["organization_id"], setup["school_id"])
    other_subject = await _create_subject(client, setup["headers"], setup["school_id"], name="Histoire")

    response = await client.post(
        f"/api/v1/classes/{setup['class_id']}/teachers",
        json={"user_id": teacher, "subject_id": other_subject["id"]},
        headers=setup["headers"],
    )
    assert response.status_code == 400


async def test_duplicate_assignment_conflicts(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasdup")
    teacher = await _user_with_role(client, "tasdupt", "TEACHER", setup["organization_id"], setup["school_id"])
    assert (await _assign(client, setup, teacher)).status_code == 201

    response = await _assign(client, setup, teacher)
    assert response.status_code == 409


async def test_update_assignment_changes_teacher(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasupd")
    first = await _user_with_role(client, "tasupdf", "TEACHER", setup["organization_id"], setup["school_id"])
    second = await _user_with_role(client, "tasupds", "TEACHER", setup["organization_id"], setup["school_id"])
    assignment = (await _assign(client, setup, first)).json()

    response = await client.patch(
        f"/api/v1/classes/{setup['class_id']}/teachers/{assignment['id']}",
        json={"user_id": second},
        headers=setup["headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["user_id"] == second
    assert [a["user_id"] for a in await _assignments(client, setup["class_id"], setup["headers"])] == [second]


async def test_update_assignment_with_invalid_teacher_keeps_original(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasupdbad")
    teacher = await _user_with_role(client, "tasupdbadt", "TEACHER", setup["organization_id"], setup["school_id"])
    school_admin = await _user_with_role(client, "tasupdbadadm", "SCHOOL_ADMIN", setup["organization_id"], setup["school_id"])
    assignment = (await _assign(client, setup, teacher)).json()

    response = await client.patch(
        f"/api/v1/classes/{setup['class_id']}/teachers/{assignment['id']}",
        json={"user_id": school_admin},
        headers=setup["headers"],
    )
    assert response.status_code == 400
    assert [a["user_id"] for a in await _assignments(client, setup["class_id"], setup["headers"])] == [teacher]


async def test_assignment_of_another_class_is_not_reachable_through_this_class(client: AsyncClient) -> None:
    setup = await _school_setup(client, "tasxclass")
    teacher = await _user_with_role(client, "tasxclasst", "TEACHER", setup["organization_id"], setup["school_id"])
    assignment = (await _assign(client, setup, teacher)).json()
    other_class = await _create_class(client, setup["headers"], setup["year_id"], setup["level_id"], name="Z")

    patched = await client.patch(
        f"/api/v1/classes/{other_class['id']}/teachers/{assignment['id']}",
        json={"user_id": teacher},
        headers=setup["headers"],
    )
    assert patched.status_code == 404
    deleted = await client.delete(
        f"/api/v1/classes/{other_class['id']}/teachers/{assignment['id']}", headers=setup["headers"]
    )
    assert deleted.status_code == 404
    assert [a["id"] for a in await _assignments(client, setup["class_id"], setup["headers"])] == [assignment["id"]]


async def test_cross_school_assignment_cannot_be_deleted_through_own_class(client: AsyncClient) -> None:
    """Régression : DELETE ne vérifiait pas que l'affectation appartenait à la classe de l'URL. Un
    admin de l'école A pouvait supprimer l'affectation d'une classe de l'école B."""
    mine = await _school_setup(client, "tasdelmine")
    theirs = await _school_setup(client, "tasdeltheirs")
    their_teacher = await _user_with_role(client, "tasdeltheirt", "TEACHER", theirs["organization_id"], theirs["school_id"])
    their_assignment = (await _assign(client, theirs, their_teacher)).json()

    response = await client.delete(
        f"/api/v1/classes/{mine['class_id']}/teachers/{their_assignment['id']}", headers=mine["headers"]
    )
    assert response.status_code == 404
    assert [a["id"] for a in await _assignments(client, theirs["class_id"], theirs["headers"])] == [their_assignment["id"]]
