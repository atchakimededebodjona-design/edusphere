import io

from httpx import AsyncClient

from tests.conftest import assign_role, register_school


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_upload_and_download_school_logo(client: AsyncClient) -> None:
    data = await register_school(client, "logoschool")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    upload_response = await client.post(
        f"/api/v1/schools/{school_id}/logo",
        files={"file": ("logo.png", io.BytesIO(b"fake-png-bytes"), "image/png")},
        headers=headers,
    )
    assert upload_response.status_code == 200, upload_response.text
    assert upload_response.json()["logo_path"] is not None

    download_response = await client.get(f"/api/v1/schools/{school_id}/logo", headers=headers)
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "image/png"
    assert download_response.content == b"fake-png-bytes"


async def test_school_logo_not_found_before_upload(client: AsyncClient) -> None:
    data = await register_school(client, "nologoschool")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    response = await client.get(f"/api/v1/schools/{school_id}/logo", headers=headers)
    assert response.status_code == 404


async def test_teacher_can_read_logo_but_not_upload(client: AsyncClient) -> None:
    data = await register_school(client, "logoteacher")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    await client.post(
        f"/api/v1/schools/{school_id}/logo",
        files={"file": ("logo.png", io.BytesIO(b"fake-png-bytes"), "image/png")},
        headers=headers_admin,
    )

    teacher_data = await register_school(client, "logoteacher-teacher")
    await assign_role(teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    read_response = await client.get(f"/api/v1/schools/{school_id}/logo", headers=headers_teacher)
    assert read_response.status_code == 200

    upload_attempt = await client.post(
        f"/api/v1/schools/{school_id}/logo",
        files={"file": ("logo2.png", io.BytesIO(b"other-bytes"), "image/png")},
        headers=headers_teacher,
    )
    assert upload_attempt.status_code == 403
