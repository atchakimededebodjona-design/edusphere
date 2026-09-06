from httpx import AsyncClient

from tests.conftest import assign_role, register_school, unique_email


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_create_new_teacher_returns_dev_reset_token(client: AsyncClient) -> None:
    data = await register_school(client, "usersnew")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    teacher_email = unique_email("teacher.usersnew")

    response = await client.post(
        "/api/v1/users",
        json={"email": teacher_email, "full_name": "Nouvelle Enseignante", "school_id": school_id, "role_code": "TEACHER"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["user"]["email"] == teacher_email
    assert body["dev_reset_token"] is not None
    assert any(r["role_code"] == "TEACHER" and r["school_id"] == school_id for r in body["roles"])

    # Le token de reset doit permettre de définir un mot de passe (endpoint déjà existant).
    reset_response = await client.post(
        "/api/v1/auth/reset-password",
        json={"token": body["dev_reset_token"], "new_password": "NewPassword123"},
    )
    assert reset_response.status_code == 204

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": teacher_email, "password": "NewPassword123"},
    )
    assert login_response.status_code == 200


async def test_create_with_existing_email_attaches_role_without_duplicate(client: AsyncClient) -> None:
    data = await register_school(client, "usersexisting")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    other_school = await register_school(client, "usersexisting-other")
    other_headers = {"Authorization": f"Bearer {await _login(client, other_school['user']['email'])}"}

    shared_email = unique_email("shared.teacher")
    first_response = await client.post(
        "/api/v1/users",
        json={"email": shared_email, "full_name": "Prof Partagé", "school_id": school_id, "role_code": "TEACHER"},
        headers=headers,
    )
    assert first_response.status_code == 201
    first_user_id = first_response.json()["user"]["id"]
    assert first_response.json()["dev_reset_token"] is not None

    second_response = await client.post(
        "/api/v1/users",
        json={
            "email": shared_email,
            "full_name": "Prof Partagé",
            "school_id": other_school["school"]["id"],
            "role_code": "TEACHER",
        },
        headers=other_headers,
    )
    assert second_response.status_code == 201
    assert second_response.json()["user"]["id"] == first_user_id
    # Le mot de passe existe déjà — pas de nouveau token de reset.
    assert second_response.json()["dev_reset_token"] is None
    # RLS sur user_roles limite la réponse au(x) rôle(s) visibles depuis le tenant de l'appelant
    # (l'admin de other_school) — le rôle de ce même utilisateur dans la première école n'est pas
    # exposé ici, ce qui est le comportement voulu (pas de fuite inter-tenant).
    roles = second_response.json()["roles"]
    assert len(roles) == 1
    assert roles[0]["school_id"] == other_school["school"]["id"]

    list_response = await client.get(f"/api/v1/users?school_id={school_id}", headers=headers)
    assert any(u["user"]["id"] == first_user_id for u in list_response.json())


async def test_rejects_platform_role(client: AsyncClient) -> None:
    data = await register_school(client, "usersplatform")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    response = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email("wannabe.superadmin"),
            "full_name": "Wannabe",
            "school_id": school_id,
            "role_code": "SUPER_ADMIN",
        },
        headers=headers,
    )
    assert response.status_code == 400


async def test_teacher_cannot_create_users(client: AsyncClient) -> None:
    data = await register_school(client, "usersteacher")
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    teacher_data = await register_school(client, "usersteacher-teacher")
    await assign_role(teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    response = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email("another.teacher"),
            "full_name": "Another",
            "school_id": school_id,
            "role_code": "TEACHER",
        },
        headers=headers_teacher,
    )
    assert response.status_code == 403


async def test_users_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "usersisoa")
    school_b = await register_school(client, "usersisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}

    # RLS rend la ligne `schools` invisible avant même le contrôle de permission applicatif
    # (même comportement que get_school en Phase 1, cf. test_academics_tenant_isolation).
    list_response = await client.get(f"/api/v1/users?school_id={school_b['school']['id']}", headers=headers_a)
    assert list_response.status_code == 404


# --- Phase 22 : gestion des comptes (rôle + activation/désactivation) --------------------------
async def _create_teacher(client: AsyncClient, headers: dict, school_id: str, prefix: str) -> dict:
    response = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email(f"teacher.{prefix}"),
            "full_name": "Enseignant Test",
            "school_id": school_id,
            "role_code": "TEACHER",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["user"]


async def test_update_user_role_replaces_school_scoped_role(client: AsyncClient) -> None:
    data = await register_school(client, "userseditrole")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    teacher = await _create_teacher(client, headers, school_id, "userseditrole")

    response = await client.patch(
        f"/api/v1/users/{teacher['id']}",
        json={"school_id": school_id, "role_code": "STAFF"},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert [r["role_code"] for r in body["roles"]] == ["STAFF"]


async def test_update_user_can_deactivate_and_reactivate(client: AsyncClient) -> None:
    data = await register_school(client, "usersdeactivate")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    teacher_email = unique_email("teacher.usersdeactivate")

    create_response = await client.post(
        "/api/v1/users",
        json={"email": teacher_email, "full_name": "Enseignant", "school_id": school_id, "role_code": "TEACHER"},
        headers=headers,
    )
    teacher = create_response.json()["user"]
    dev_reset_token = create_response.json()["dev_reset_token"]
    await client.post(
        "/api/v1/auth/reset-password", json={"token": dev_reset_token, "new_password": "TeacherPass123"}
    )

    deactivate_response = await client.patch(
        f"/api/v1/users/{teacher['id']}", json={"school_id": school_id, "is_active": False}, headers=headers
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["user"]["is_active"] is False

    login_blocked = await client.post(
        "/api/v1/auth/login", json={"email": teacher_email, "password": "TeacherPass123"}
    )
    assert login_blocked.status_code == 401

    reactivate_response = await client.patch(
        f"/api/v1/users/{teacher['id']}", json={"school_id": school_id, "is_active": True}, headers=headers
    )
    assert reactivate_response.status_code == 200
    assert reactivate_response.json()["user"]["is_active"] is True

    login_ok = await client.post("/api/v1/auth/login", json={"email": teacher_email, "password": "TeacherPass123"})
    assert login_ok.status_code == 200


async def test_update_user_cannot_modify_own_account(client: AsyncClient) -> None:
    data = await register_school(client, "usersselfedit")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    response = await client.patch(
        f"/api/v1/users/{data['user']['id']}", json={"school_id": school_id, "is_active": False}, headers=headers
    )
    assert response.status_code == 403


async def test_update_user_rejects_platform_role(client: AsyncClient) -> None:
    data = await register_school(client, "userseditplatform")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    teacher = await _create_teacher(client, headers, school_id, "userseditplatform")

    response = await client.patch(
        f"/api/v1/users/{teacher['id']}", json={"school_id": school_id, "role_code": "SUPER_ADMIN"}, headers=headers
    )
    assert response.status_code == 400


async def test_update_user_requires_at_least_one_field(client: AsyncClient) -> None:
    data = await register_school(client, "userseditempty")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    teacher = await _create_teacher(client, headers, school_id, "userseditempty")

    response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": school_id}, headers=headers)
    assert response.status_code == 400


async def test_update_user_rejects_user_with_no_role_in_school(client: AsyncClient) -> None:
    """Un utilisateur qui n'a aucune UserRole scopée à cette école précise (même s'il existe par
    ailleurs) ne doit jamais être modifiable via ce endpoint — 404, pas de fuite d'existence."""
    data = await register_school(client, "userseditnorole")
    other_school = await register_school(client, "userseditnorole-other")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}

    response = await client.patch(
        f"/api/v1/users/{other_school['user']['id']}",
        json={"school_id": data["school"]["id"], "is_active": False},
        headers=headers,
    )
    assert response.status_code == 404


async def test_update_user_cross_school_isolation(client: AsyncClient) -> None:
    """Un admin de School A ne doit jamais pouvoir modifier un utilisateur via le school_id de
    School B (RLS rend School B invisible avant même le contrôle applicatif)."""
    school_a = await register_school(client, "userseditisoa")
    school_b = await register_school(client, "userseditisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}
    teacher_b = await _create_teacher(client, headers_b, school_b["school"]["id"], "userseditisob")

    response = await client.patch(
        f"/api/v1/users/{teacher_b['id']}",
        json={"school_id": school_b["school"]["id"], "is_active": False},
        headers=headers_a,
    )
    assert response.status_code == 404


async def test_teacher_cannot_update_users(client: AsyncClient) -> None:
    data = await register_school(client, "userseditteacher")
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    teacher = await _create_teacher(client, headers_admin, school_id, "userseditteacher")

    other_teacher_data = await register_school(client, "userseditteacher-other")
    await assign_role(other_teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, other_teacher_data['user']['email'])}"}

    response = await client.patch(
        f"/api/v1/users/{teacher['id']}", json={"school_id": school_id, "is_active": False}, headers=headers_teacher
    )
    assert response.status_code == 403
