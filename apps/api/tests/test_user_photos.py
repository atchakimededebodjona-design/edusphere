"""Photo d'identité des comptes et photos des élèves dans l'espace enseignant (2026-11-19, migration 0036).

- Le compte met, lit, remplace et retire SA photo (/auth/me/photo).
- L'administration de l'école met ou retire la photo d'un membre de son personnel (/users/{id}/photo),
  avec les règles d'autorité de la modification d'un compte ; jamais hors de son école.
- L'enseignant voit si ses élèves ont une photo (et la lit), sans pouvoir la changer.
- La suppression d'un compte par la plateforme efface aussi sa photo.
"""

import io
import uuid

from httpx import AsyncClient

from app.core.storage import storage
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.users.models import User
from tests.conftest import valid_image_bytes
from tests.pr17_helpers import create_platform_owner
from tests.test_notifications import _create_class, _create_student_in_class, _create_user_with_role, _setup_school
from tests.test_platform_account_removal import _assign_teacher

JPEG = valid_image_bytes("JPEG")
PNG = valid_image_bytes("PNG")


def _file(name: str, content: bytes, mime: str) -> dict:
    return {"file": (name, io.BytesIO(content), mime)}


async def _photo_path(user_id: str) -> str | None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        user = await db.get(User, uuid.UUID(user_id))
        assert user is not None
        return user.photo_path


async def _stored(path: str) -> bool:
    try:
        await storage.download(path)
        return True
    except Exception:
        return False


async def test_own_photo_put_read_replace_and_remove(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "ph-own")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "ph.own.t")
    headers = teacher["headers"]
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert me["user"]["has_photo"] is False
    assert (await client.get("/api/v1/auth/me/photo", headers=headers)).status_code == 404

    response = await client.post("/api/v1/auth/me/photo", files=_file("moi.jpg", JPEG, "image/jpeg"), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["has_photo"] is True
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["user"]["has_photo"] is True
    assert (await client.get("/api/v1/teacher/me", headers=headers)).json()["has_photo"] is True
    photo = await client.get("/api/v1/auth/me/photo", headers=headers)
    assert photo.status_code == 200 and photo.content == JPEG
    assert photo.headers["content-type"] == "image/jpeg"
    assert photo.headers["cache-control"] == "private, no-store"
    first_path = await _photo_path(teacher["user"]["id"])
    assert first_path is not None and first_path.startswith(f"users/{teacher['user']['id']}/")

    # Remplacée : l'ancien fichier est effacé.
    response = await client.post("/api/v1/auth/me/photo", files=_file("moi.png", PNG, "image/png"), headers=headers)
    assert response.status_code == 200, response.text
    assert (await client.get("/api/v1/auth/me/photo", headers=headers)).content == PNG
    assert not await _stored(first_path)

    second_path = await _photo_path(teacher["user"]["id"])
    assert second_path is not None
    assert (await client.delete("/api/v1/auth/me/photo", headers=headers)).status_code == 204
    assert (await client.get("/api/v1/auth/me/photo", headers=headers)).status_code == 404
    assert (await client.get("/api/v1/auth/me", headers=headers)).json()["user"]["has_photo"] is False
    assert not await _stored(second_path)
    assert (await client.delete("/api/v1/auth/me/photo", headers=headers)).status_code == 204  # idempotent


async def test_own_photo_rejects_non_images_and_anonymous(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "ph-bad")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "ph.bad.t")
    assert (await client.post("/api/v1/auth/me/photo", files=_file("moi.jpg", JPEG, "image/jpeg"))).status_code == 401
    for name, content, mime in (
        ("moi.jpg", b"pas une image", "image/jpeg"),
        ("moi.pdf", b"%PDF-1.4 faux", "application/pdf"),
        ("moi.gif", b"GIF89a....", "image/gif"),
    ):
        response = await client.post("/api/v1/auth/me/photo", files=_file(name, content, mime), headers=teacher["headers"])
        assert response.status_code in (400, 413, 415, 422), response.text
    assert await _photo_path(teacher["user"]["id"]) is None


async def test_school_admin_sets_and_removes_a_staff_photo(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "ph-admin")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "ph.admin.t")
    school_id = ctx["school"]["id"]
    target = teacher["user"]["id"]

    response = await client.post(
        f"/api/v1/users/{target}/photo",
        data={"school_id": school_id},
        files=_file("prof.jpg", JPEG, "image/jpeg"),
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 200, response.text
    assert response.json()["has_photo"] is True
    listed = (await client.get(f"/api/v1/users?school_id={school_id}", headers=ctx["admin_headers"])).json()
    assert next(row for row in listed if row["user"]["id"] == target)["user"]["has_photo"] is True
    read = await client.get(f"/api/v1/users/{target}/photo?school_id={school_id}", headers=ctx["admin_headers"])
    assert read.status_code == 200 and read.content == JPEG
    # L'enseignant retrouve dans son espace la photo mise par l'administration.
    assert (await client.get("/api/v1/auth/me/photo", headers=teacher["headers"])).content == JPEG

    # L'administrateur peut aussi mettre la sienne par cette route.
    own = await client.post(
        f"/api/v1/users/{ctx['admin_user_id']}/photo",
        data={"school_id": school_id},
        files=_file("admin.png", PNG, "image/png"),
        headers=ctx["admin_headers"],
    )
    assert own.status_code == 200, own.text

    removed = await client.delete(f"/api/v1/users/{target}/photo?school_id={school_id}", headers=ctx["admin_headers"])
    assert removed.status_code == 204
    assert (await client.get(f"/api/v1/users/{target}/photo?school_id={school_id}", headers=ctx["admin_headers"])).status_code == 404


async def test_staff_photo_stays_inside_the_school_and_its_managers(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "ph-scope")
    other = await _setup_school(client, "ph-scope-other")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "ph.scope.t")
    colleague = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "ph.scope.c")
    target = teacher["user"]["id"]
    upload = _file("prof.jpg", JPEG, "image/jpeg")

    # Un enseignant n'a pas `users.manage` : ni la photo d'un collègue, ni la lecture du personnel.
    response = await client.post(
        f"/api/v1/users/{target}/photo", data={"school_id": ctx["school"]["id"]}, files=upload, headers=colleague["headers"]
    )
    assert response.status_code == 403
    response = await client.get(f"/api/v1/users/{target}/photo?school_id={ctx['school']['id']}", headers=colleague["headers"])
    assert response.status_code == 403

    # L'administration d'une autre école : refus sur l'école A, et rien sur son école pour ce compte.
    response = await client.post(
        f"/api/v1/users/{target}/photo",
        data={"school_id": ctx["school"]["id"]},
        files=_file("prof.jpg", JPEG, "image/jpeg"),
        headers=other["admin_headers"],
    )
    assert response.status_code in (403, 404)
    response = await client.post(
        f"/api/v1/users/{target}/photo",
        data={"school_id": other["school"]["id"]},
        files=_file("prof.jpg", JPEG, "image/jpeg"),
        headers=other["admin_headers"],
    )
    assert response.status_code == 404
    response = await client.get(f"/api/v1/users/{target}/photo?school_id={other['school']['id']}", headers=other["admin_headers"])
    assert response.status_code == 404
    assert await _photo_path(target) is None

    # Compte inconnu de l'école.
    response = await client.post(
        f"/api/v1/users/{uuid.uuid4()}/photo",
        data={"school_id": ctx["school"]["id"]},
        files=_file("prof.jpg", JPEG, "image/jpeg"),
        headers=ctx["admin_headers"],
    )
    assert response.status_code == 404


async def test_teacher_sees_student_photos_but_cannot_change_them(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "ph-students")
    school_class = await _create_class(client, ctx, "ph.students")
    with_photo = await _create_student_in_class(client, ctx, school_class, "phs1")
    without_photo = await _create_student_in_class(client, ctx, school_class, "phs2")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "ph.students.t")
    await _assign_teacher(client, ctx, school_class, teacher["user"]["id"])
    uploaded = await client.post(
        f"/api/v1/students/{with_photo['id']}/photo", files=_file("eleve.jpg", JPEG, "image/jpeg"), headers=ctx["admin_headers"]
    )
    assert uploaded.status_code == 200, uploaded.text

    listed = (await client.get("/api/v1/teacher/students", headers=teacher["headers"])).json()
    flags = {row["id"]: row["has_photo"] for row in listed}
    assert flags == {with_photo["id"]: True, without_photo["id"]: False}
    by_class = (await client.get(f"/api/v1/teacher/classes/{school_class['id']}/students", headers=teacher["headers"])).json()
    assert {row["id"]: row["has_photo"] for row in by_class} == flags
    detail = (await client.get(f"/api/v1/teacher/students/{with_photo['id']}", headers=teacher["headers"])).json()
    assert detail["has_photo"] is True
    photo = await client.get(f"/api/v1/students/{with_photo['id']}/photo", headers=teacher["headers"])
    assert photo.status_code == 200 and photo.content == JPEG

    # Voir seulement : ni envoi ni retrait.
    response = await client.post(
        f"/api/v1/students/{without_photo['id']}/photo", files=_file("eleve.jpg", JPEG, "image/jpeg"), headers=teacher["headers"]
    )
    assert response.status_code == 403
    assert (await client.delete(f"/api/v1/students/{with_photo['id']}/photo", headers=teacher["headers"])).status_code == 403


async def test_deleting_an_account_erases_its_photo(client: AsyncClient) -> None:
    ctx = await _setup_school(client, "ph-erase")
    teacher = await _create_user_with_role(client, ctx["admin_headers"], ctx["school"]["id"], "TEACHER", "ph.erase.t")
    await client.post("/api/v1/auth/me/photo", files=_file("moi.jpg", JPEG, "image/jpeg"), headers=teacher["headers"])
    path = await _photo_path(teacher["user"]["id"])
    assert path is not None and await _stored(path)
    owner = await create_platform_owner(client, "pherase-owner")
    response = await client.post(
        f"/api/v1/platform/accounts/{teacher['user']['id']}/delete",
        json={"confirm_email": teacher["user"]["email"]},
        headers=owner["headers"],
    )
    assert response.status_code == 200, response.text
    assert await _photo_path(teacher["user"]["id"]) is None
    assert not await _stored(path)
