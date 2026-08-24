from datetime import date

from httpx import AsyncClient

from tests.conftest import assign_role, register_school


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
