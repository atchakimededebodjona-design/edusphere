from httpx import AsyncClient

from tests.conftest import register_school, unique_email, unique_slug


async def test_register_creates_organization_school_admin_and_tokens(client: AsyncClient) -> None:
    data = await register_school(client, "regtest")

    assert data["organization"]["slug"].startswith("regtest")
    assert data["school"]["organization_id"] == data["organization"]["id"]
    assert data["user"]["is_platform_admin"] is False
    assert data["tokens"]["access_token"]
    assert data["tokens"]["refresh_token"]


async def test_register_never_grants_platform_admin(client: AsyncClient) -> None:
    data = await register_school(client, "noplatform")
    assert data["user"]["is_platform_admin"] is False

    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {data['tokens']['access_token']}"}
    )
    role_codes = {r["role_code"] for r in me.json()["roles"]}
    assert role_codes == {"SCHOOL_ADMIN"}
    assert "SUPER_ADMIN" not in role_codes
    assert "PLATFORM_SUPPORT" not in role_codes


async def test_register_duplicate_email_conflicts(client: AsyncClient) -> None:
    email = unique_email("dup")
    payload = {
        "organization_name": "Dup Group",
        "organization_slug": unique_slug("dup"),
        "country_code": "TG",
        "school_name": "Dup School",
        "school_slug": "principale",
        "admin_full_name": "Dup Admin",
        "admin_email": email,
        "admin_password": "SuperSecret123",
    }
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    payload["organization_slug"] = unique_slug("dup2")
    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


async def test_login_success(client: AsyncClient) -> None:
    data = await register_school(client, "login")
    email = data["user"]["email"]

    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]


async def test_login_wrong_password_rejected(client: AsyncClient) -> None:
    data = await register_school(client, "badpass")
    email = data["user"]["email"]

    response = await client.post("/api/v1/auth/login", json={"email": email, "password": "WrongPassword"})
    assert response.status_code == 401


async def test_login_unknown_email_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@edusphere-pytest.tg", "password": "whatever123"}
    )
    assert response.status_code == 401


async def test_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


async def test_me_rejects_garbage_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


async def test_refresh_rotates_token_and_invalidates_old_one(client: AsyncClient) -> None:
    data = await register_school(client, "refresh")
    old_refresh = data["tokens"]["refresh_token"]

    first_refresh = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert first_refresh.status_code == 200
    new_refresh = first_refresh.json()["refresh_token"]
    assert new_refresh != old_refresh

    reuse_old = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert reuse_old.status_code == 401

    reuse_new = await client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert reuse_new.status_code == 200


async def test_refresh_rejects_garbage_token(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "totally-made-up"})
    assert response.status_code == 401


async def test_logout_revokes_session(client: AsyncClient) -> None:
    data = await register_school(client, "logout")
    refresh_token = data["tokens"]["refresh_token"]

    logout_response = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_response.status_code == 204

    refresh_after_logout = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_after_logout.status_code == 401


async def test_password_reset_flow(client: AsyncClient) -> None:
    data = await register_school(client, "reset")
    email = data["user"]["email"]

    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 202
    dev_token = forgot.json()["dev_token"]
    assert dev_token  # exposé uniquement hors "production", cf. service.request_password_reset

    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": dev_token, "new_password": "BrandNewPass1"}
    )
    assert reset.status_code == 204

    old_login = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert old_login.status_code == 401

    new_login = await client.post("/api/v1/auth/login", json={"email": email, "password": "BrandNewPass1"})
    assert new_login.status_code == 200

    reuse_token = await client.post(
        "/api/v1/auth/reset-password", json={"token": dev_token, "new_password": "AnotherOne123"}
    )
    assert reuse_token.status_code == 400


async def test_forgot_password_unknown_email_does_not_leak(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/forgot-password", json={"email": "ghost@edusphere-pytest.tg"})
    assert response.status_code == 202
    assert response.json()["dev_token"] is None


async def test_sessions_list_and_remote_revoke(client: AsyncClient) -> None:
    data = await register_school(client, "sessions")
    email = data["user"]["email"]

    login = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "SuperSecret123", "device_id": "device-x"}
    )
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    sessions_response = await client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions_response.status_code == 200
    sessions = sessions_response.json()
    assert len(sessions) >= 2  # la session du register() + celle du login()

    session_id = sessions[0]["id"]
    delete_response = await client.delete(f"/api/v1/auth/sessions/{session_id}", headers=headers)
    assert delete_response.status_code == 204

    sessions_after = await client.get("/api/v1/auth/sessions", headers=headers)
    remaining_ids = {s["id"] for s in sessions_after.json()}
    assert session_id not in remaining_ids
