from httpx import AsyncClient

from tests.conftest import create_platform_admin, register_school


async def test_platform_dashboard_accessible_with_zero_organizations(client: AsyncClient) -> None:
    admin = await create_platform_admin(client, "emptyplatform")
    headers = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}

    response = await client.get("/api/v1/platform/dashboard", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["organization_count"] >= 0
    assert body["school_count"] >= 0
    assert body["user_count"] >= 1  # au moins le compte plateforme lui-même
    assert body["student_count"] >= 0


async def test_platform_dashboard_counts_reflect_real_data(client: AsyncClient) -> None:
    admin = await create_platform_admin(client, "countplatform")
    headers = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}

    before = (await client.get("/api/v1/platform/dashboard", headers=headers)).json()
    await register_school(client, "countplatformschool")
    after = (await client.get("/api/v1/platform/dashboard", headers=headers)).json()

    assert after["organization_count"] == before["organization_count"] + 1
    assert after["school_count"] == before["school_count"] + 1
    assert after["user_count"] == before["user_count"] + 1


async def test_platform_dashboard_rejects_non_platform_admin(client: AsyncClient) -> None:
    data = await register_school(client, "notplatform")
    headers = {"Authorization": f"Bearer {data['tokens']['access_token']}"}

    response = await client.get("/api/v1/platform/dashboard", headers=headers)
    assert response.status_code == 403


async def test_platform_dashboard_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/platform/dashboard")
    assert response.status_code == 401


async def test_me_exposes_platform_admin_with_no_roles_scoped_to_tenant(client: AsyncClient) -> None:
    admin = await create_platform_admin(client, "meplatform")
    headers = {"Authorization": f"Bearer {admin['tokens']['access_token']}"}

    response = await client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["user"]["is_platform_admin"] is True
    assert body["roles"] == [{"role_code": "SUPER_ADMIN", "organization_id": None, "school_id": None}]
