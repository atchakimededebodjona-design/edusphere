from httpx import AsyncClient

from tests.conftest import assign_role, register_school


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_school_admin_can_manage_own_school(client: AsyncClient) -> None:
    data = await register_school(client, "rbacadmin")
    token = await _login(client, data["user"]["email"])
    school_id = data["school"]["id"]

    response = await client.patch(
        f"/api/v1/schools/{school_id}",
        json={"name": "Nouveau nom"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Nouveau nom"


async def test_teacher_can_read_but_not_manage_school(client: AsyncClient) -> None:
    data = await register_school(client, "rbacteacher")
    organization_id = data["organization"]["id"]
    school_id = data["school"]["id"]

    # Il n'existe pas encore d'endpoint d'invitation d'utilisateur en Phase 1 (différé) : on
    # crée un second compte via register (qui force SCHOOL_ADMIN), puis on retire ce rôle et on
    # attribue TEACHER à la place, scopé à l'école — ce que ferait un futur endpoint d'invitation.
    teacher_data = await register_school(client, "rbacteacher-teacher")
    teacher_user_id = teacher_data["user"]["id"]
    teacher_email = teacher_data["user"]["email"]

    await assign_role(teacher_user_id, "TEACHER", organization_id=organization_id, school_id=school_id)

    token = await _login(client, teacher_email)
    headers = {"Authorization": f"Bearer {token}"}

    read_response = await client.get(f"/api/v1/schools/{school_id}", headers=headers)
    assert read_response.status_code == 200

    manage_response = await client.patch(
        f"/api/v1/schools/{school_id}", json={"name": "Hacked"}, headers=headers
    )
    assert manage_response.status_code == 403


async def test_list_organizations_requires_platform_role(client: AsyncClient) -> None:
    data = await register_school(client, "rbaclist")
    token = await _login(client, data["user"]["email"])

    response = await client.get("/api/v1/organizations", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


async def test_platform_support_can_list_organizations_read_only(client: AsyncClient) -> None:
    data = await register_school(client, "rbacplatform")
    user_id = data["user"]["id"]
    email = data["user"]["email"]
    organization_id = data["organization"]["id"]

    # Retire le SCHOOL_ADMIN par défaut pour isoler le comportement de PLATFORM_SUPPORT seul.
    import uuid as uuid_module

    from sqlalchemy import delete

    from app.core.tenancy import set_platform_wide_context
    from app.db.session import AsyncSessionLocal
    from app.modules.rbac.models import UserRole

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)  # user_roles a RLS activé, cf. tests/conftest.py
        await db.execute(delete(UserRole).where(UserRole.user_id == uuid_module.UUID(user_id)))
        await db.commit()

    await assign_role(user_id, "PLATFORM_SUPPORT", organization_id=None, school_id=None)

    token = await _login(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    list_response = await client.get("/api/v1/organizations", headers=headers)
    assert list_response.status_code == 200
    slugs = {org["slug"] for org in list_response.json()}
    assert data["organization"]["slug"] in slugs

    manage_response = await client.patch(
        f"/api/v1/organizations/{organization_id}", json={"name": "Renamed"}, headers=headers
    )
    assert manage_response.status_code == 403


async def test_roles_and_permissions_catalog_readable_when_authenticated(client: AsyncClient) -> None:
    data = await register_school(client, "rbaccatalog")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}

    roles_response = await client.get("/api/v1/roles", headers=headers)
    assert roles_response.status_code == 200
    role_codes = {r["code"] for r in roles_response.json()}
    assert {"SUPER_ADMIN", "SCHOOL_ADMIN", "TEACHER", "STUDENT"}.issubset(role_codes)

    permissions_response = await client.get("/api/v1/permissions", headers=headers)
    assert permissions_response.status_code == 200
    assert len(permissions_response.json()) > 0


async def test_roles_catalog_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/roles")
    assert response.status_code == 401
