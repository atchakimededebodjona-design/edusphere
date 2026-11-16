import io

import pytest
from httpx import AsyncClient

from tests.conftest import assign_role, register_school, valid_image_bytes


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_upload_and_download_school_logo(client: AsyncClient) -> None:
    data = await register_school(client, "logoschool")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]

    png_bytes = valid_image_bytes("PNG")
    upload_response = await client.post(
        f"/api/v1/schools/{school_id}/logo",
        files={"file": ("logo.png", io.BytesIO(png_bytes), "image/png")},
        headers=headers,
    )
    assert upload_response.status_code == 200, upload_response.text
    assert upload_response.json()["logo_path"] is not None

    download_response = await client.get(f"/api/v1/schools/{school_id}/logo", headers=headers)
    assert download_response.status_code == 200
    assert download_response.headers["content-type"] == "image/png"
    assert download_response.content == png_bytes


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
        files={"file": ("logo.png", io.BytesIO(valid_image_bytes("PNG")), "image/png")},
        headers=headers_admin,
    )

    teacher_data = await register_school(client, "logoteacher-teacher")
    await assign_role(teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    read_response = await client.get(f"/api/v1/schools/{school_id}/logo", headers=headers_teacher)
    assert read_response.status_code == 200

    upload_attempt = await client.post(
        f"/api/v1/schools/{school_id}/logo",
        files={"file": ("logo2.png", io.BytesIO(valid_image_bytes("PNG")), "image/png")},
        headers=headers_teacher,
    )
    assert upload_attempt.status_code == 403


# --- Contrôle de l'envoi de logo (2026-11-16) ------------------------------------------------------
async def _upload_logo(client: AsyncClient, school_id: str, headers: dict, filename: str, content: bytes, mime: str):
    return await client.post(
        f"/api/v1/schools/{school_id}/logo", files={"file": (filename, io.BytesIO(content), mime)}, headers=headers
    )


async def test_logo_upload_rejects_oversized_file_and_keeps_previous_logo(client: AsyncClient) -> None:
    from app.modules.students.service import LOGO_MAX_BYTES

    data = await register_school(client, "logotoolarge")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    first = await _upload_logo(client, school_id, headers, "logo.png", valid_image_bytes("PNG"), "image/png")
    assert first.status_code == 200, first.text
    previous_path = first.json()["logo_path"]

    response = await _upload_logo(client, school_id, headers, "big.png", b"x" * (LOGO_MAX_BYTES + 1), "image/png")
    assert response.status_code == 422
    assert response.json()["detail"] == "Logo trop volumineux (maximum 2 Mio)."

    school = await client.get(f"/api/v1/schools/{school_id}", headers=headers)
    assert school.json()["logo_path"] == previous_path


@pytest.mark.parametrize(
    ("case", "filename", "image_format", "mime"),
    [
        ("not-an-image", "logo.png", None, "image/png"),  # se déclare PNG mais n'est pas une image
        ("gif", "logo.gif", "GIF", "image/gif"),  # vraie image, format non accepté
        ("renamed", "logo.jpg", "PNG", "image/jpeg"),  # vrai PNG renommé en .jpg
        ("empty", "logo.png", "", "image/png"),  # fichier vide
    ],
)
async def test_logo_upload_rejects_non_image_or_mismatched_file(
    client: AsyncClient, case: str, filename: str, image_format: str | None, mime: str
) -> None:
    data = await register_school(client, f"logobad-{case}")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    if image_format is None:
        content = b"fake-png-bytes"
    elif image_format == "":
        content = b""
    else:
        content = valid_image_bytes(image_format)

    response = await _upload_logo(client, school_id, headers, filename, content, mime)
    assert response.status_code == 422, response.text

    school = await client.get(f"/api/v1/schools/{school_id}", headers=headers)
    assert school.json()["logo_path"] is None
