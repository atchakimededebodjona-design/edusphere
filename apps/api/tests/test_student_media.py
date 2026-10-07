"""Sprint "Fiche élève — UX, documents, photo et inscriptions" : durcissement des uploads
photo/document (validation réelle du contenu, nettoyage sans fichier orphelin, suppression de
photo, isolation tenant/RBAC) et des inscriptions (classe hors école, RBAC, isolation).

Les tests déjà existants (test_students.py, test_storage_security.py) couvrent le chemin heureux
de base et la traversée de chemin — ce fichier couvre spécifiquement les cas ajoutés par ce sprint.
"""

import io
import uuid as uuid_module
from datetime import date

import pytest
from fastapi import UploadFile
from httpx import AsyncClient

from tests.conftest import assign_role, register_school, valid_image_bytes, valid_pdf_bytes


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def _create_student(client: AsyncClient, headers: dict, school_id: str, matricule: str = "M0001") -> dict:
    response = await client.post(
        "/api/v1/students",
        json={
            "school_id": school_id,
            "matricule": matricule,
            "first_name": "Awa",
            "last_name": "Koffi",
            "date_of_birth": str(date(2015, 3, 12)),
            "sex": "F",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


# --- PHOTO : types valides -----------------------------------------------------------------------
async def test_photo_upload_accepts_png(client: AsyncClient) -> None:
    data = await register_school(client, "photopng")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.png", io.BytesIO(valid_image_bytes("PNG")), "image/png")},
    )
    assert response.status_code == 200, response.text


async def test_photo_upload_accepts_webp(client: AsyncClient) -> None:
    data = await register_school(client, "photowebp")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.webp", io.BytesIO(valid_image_bytes("WEBP")), "image/webp")},
    )
    assert response.status_code == 200, response.text


# --- PHOTO : rejets --------------------------------------------------------------------------------
async def test_photo_upload_rejects_oversized_file(client: AsyncClient) -> None:
    data = await register_school(client, "photobig")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    oversized = b"\xff" * (5 * 1024 * 1024 + 1)
    response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.jpg", io.BytesIO(oversized), "image/jpeg")},
    )
    assert response.status_code == 422


async def test_photo_upload_rejects_non_image_content(client: AsyncClient) -> None:
    """Le Content-Type déclaré ment (image/jpeg) mais le contenu réel est un PDF — la détection
    réelle (Pillow) doit rejeter, pas le Content-Type déclaré par le client."""
    data = await register_school(client, "photofake")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.jpg", io.BytesIO(valid_pdf_bytes()), "image/jpeg")},
    )
    assert response.status_code == 422


async def test_photo_upload_rejects_empty_file(client: AsyncClient) -> None:
    data = await register_school(client, "photoempty")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.jpg", io.BytesIO(b""), "image/jpeg")},
    )
    assert response.status_code == 422


# --- PHOTO : remplacement et suppression ------------------------------------------------------------
async def test_photo_replacement_deletes_old_file(client: AsyncClient) -> None:
    from app.core.storage import storage as shared_storage

    data = await register_school(client, "photoreplace")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    first = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo1.jpg", io.BytesIO(valid_image_bytes("JPEG")), "image/jpeg")},
    )
    old_path = first.json()["photo_path"]
    assert shared_storage._resolve(old_path).exists()  # type: ignore[attr-defined]

    second = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo2.png", io.BytesIO(valid_image_bytes("PNG")), "image/png")},
    )
    new_path = second.json()["photo_path"]
    assert new_path != old_path

    # L'ancien fichier a bien été supprimé après le commit réussi du nouveau chemin.
    assert not shared_storage._resolve(old_path).exists()  # type: ignore[attr-defined]
    assert shared_storage._resolve(new_path).exists()  # type: ignore[attr-defined]


async def test_delete_student_photo(client: AsyncClient) -> None:
    from app.core.storage import storage as shared_storage

    data = await register_school(client, "photodelete")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    upload = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.jpg", io.BytesIO(valid_image_bytes("JPEG")), "image/jpeg")},
    )
    photo_path = upload.json()["photo_path"]

    delete_response = await client.delete(f"/api/v1/students/{student['id']}/photo", headers=headers)
    assert delete_response.status_code == 204
    assert not shared_storage._resolve(photo_path).exists()  # type: ignore[attr-defined]

    get_response = await client.get(f"/api/v1/students/{student['id']}", headers=headers)
    assert get_response.json()["photo_path"] is None

    # Idempotent : une seconde suppression (déjà absente) ne doit pas échouer.
    second_delete = await client.delete(f"/api/v1/students/{student['id']}/photo", headers=headers)
    assert second_delete.status_code == 204


async def test_delete_student_photo_requires_manage_permission(client: AsyncClient) -> None:
    data = await register_school(client, "photodeleterbac")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    student = await _create_student(client, headers_admin, school_id)

    teacher_data = await register_school(client, "photodeleterbac-teacher")
    await assign_role(teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    response = await client.delete(f"/api/v1/students/{student['id']}/photo", headers=headers_teacher)
    assert response.status_code in (403, 404)


async def test_delete_student_photo_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "photodeleteisoa")
    school_b = await register_school(client, "photodeleteisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    student_a = await _create_student(client, headers_a, school_a["school"]["id"])
    await client.post(
        f"/api/v1/students/{student_a['id']}/photo",
        headers=headers_a,
        files={"file": ("photo.jpg", io.BytesIO(valid_image_bytes("JPEG")), "image/jpeg")},
    )

    response = await client.delete(f"/api/v1/students/{student_a['id']}/photo", headers=headers_b)
    assert response.status_code == 404


async def test_photo_upload_db_failure_does_not_leave_orphan_file(client: AsyncClient) -> None:
    """Simule un échec de `db.flush()` après que le fichier ait déjà été écrit sur le stockage —
    le fichier nouvellement uploadé doit être supprimé, jamais laissé orphelin (router.py::
    upload_student_photo, bloc try/except).

    Appelle la fonction du routeur directement (plutôt que via HTTP) avec une session dédiée dont
    seul `flush` est patché à l'instance : patcher `AsyncSession.flush` au niveau classe casserait
    l'autoflush de TOUTE requête (authentification incluse), empêchant même l'upload d'atteindre
    le stockage — même principe que test_email.py::test_create_or_attach_user_does_not_send_
    welcome_email_if_commit_fails."""
    from app.core.storage import storage as shared_storage
    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.students.models import Student
    from app.modules.students.router import upload_student_photo
    from app.modules.users.models import User

    data = await register_school(client, "photorollback")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    user_id = uuid_module.UUID(data["user"]["id"])
    student_id = uuid_module.UUID(student["id"])

    async def failing_flush() -> None:
        raise RuntimeError("flush simulé en échec (test rollback)")

    uploaded_path: str | None = None
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, user_id)
        current_user = await db.get(User, user_id)
        assert current_user is not None
        setattr(db, "flush", failing_flush)

        upload = UploadFile(file=io.BytesIO(valid_image_bytes("JPEG")), filename="photo.jpg")
        with pytest.raises(RuntimeError):
            await upload_student_photo(student_id, db, current_user, upload)

        # Retire le patch avant toute requête de vérification : `failing_flush` ignore le "rien à
        # faire" que `Session.flush()` gère normalement en interne, et casserait l'autoflush d'un
        # simple SELECT qui suit. Le `db.rollback()` fait dans router.py a aussi effacé le contexte
        # RLS (SET LOCAL ne survit pas à un rollback) : on le réapplique avant de requêter à nouveau,
        # sans quoi la ligne deviendrait invisible sous RLS (exactement comme un tenant étranger).
        delattr(db, "flush")
        await apply_tenant_context(db, user_id)
        student_obj = await db.get(Student, student_id)
        assert student_obj is not None
        uploaded_path = student_obj.photo_path

    assert uploaded_path is None

    get_response = await client.get(f"/api/v1/students/{student['id']}", headers=headers)
    assert get_response.json()["photo_path"] is None

    student_dir = shared_storage._resolve(f"students/{student['id']}")  # type: ignore[attr-defined]
    leftover_files = [p for p in student_dir.rglob("*") if p.is_file()] if student_dir.exists() else []
    assert leftover_files == []


# --- DOCUMENTS : rejets -----------------------------------------------------------------------------
async def test_document_upload_rejects_oversized_file(client: AsyncClient) -> None:
    data = await register_school(client, "docbig")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    oversized = valid_pdf_bytes() + b"\x00" * (10 * 1024 * 1024)
    response = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers,
        data={"document_type": "Bulletin"},
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
    )
    assert response.status_code == 422


async def test_document_upload_rejects_forbidden_mime(client: AsyncClient) -> None:
    data = await register_school(client, "docforbidden")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers,
        data={"document_type": "Bulletin"},
        files={"file": ("archive.zip", io.BytesIO(b"PK\x03\x04 fake zip content"), "application/zip")},
    )
    assert response.status_code == 422


async def test_document_upload_rejects_empty_document_type(client: AsyncClient) -> None:
    data = await register_school(client, "docnotype")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers,
        data={"document_type": "   "},
        files={"file": ("certificate.pdf", io.BytesIO(valid_pdf_bytes()), "application/pdf")},
    )
    assert response.status_code == 422


async def test_document_upload_accepts_image_and_saves_metadata(client: AsyncClient) -> None:
    data = await register_school(client, "docimage")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    content = valid_image_bytes("PNG")
    response = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers,
        data={"document_type": "Photo d'identité"},
        files={"file": ("id_photo.png", io.BytesIO(content), "image/png")},
    )
    assert response.status_code == 201, response.text
    document = response.json()
    assert document["mime_type"] == "image/png"
    assert document["file_size"] == len(content)


# --- DOCUMENTS : suppression / isolation / RBAC ------------------------------------------------------
async def test_document_deletion_removes_storage_file(client: AsyncClient) -> None:
    from app.core.storage import storage as shared_storage

    data = await register_school(client, "docdeletefile")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    upload = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers,
        data={"document_type": "Bulletin"},
        files={"file": ("bulletin.pdf", io.BytesIO(valid_pdf_bytes()), "application/pdf")},
    )
    document = upload.json()
    file_path = document["file_path"]
    assert shared_storage._resolve(file_path).exists()  # type: ignore[attr-defined]

    delete_response = await client.delete(
        f"/api/v1/students/{student['id']}/documents/{document['id']}", headers=headers
    )
    assert delete_response.status_code == 204
    assert not shared_storage._resolve(file_path).exists()  # type: ignore[attr-defined]


async def test_document_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "docisoa")
    school_b = await register_school(client, "docisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    student_a = await _create_student(client, headers_a, school_a["school"]["id"])
    upload = await client.post(
        f"/api/v1/students/{student_a['id']}/documents",
        headers=headers_a,
        data={"document_type": "Bulletin"},
        files={"file": ("bulletin.pdf", io.BytesIO(valid_pdf_bytes()), "application/pdf")},
    )
    document = upload.json()

    download_response = await client.get(
        f"/api/v1/students/{student_a['id']}/documents/{document['id']}", headers=headers_b
    )
    assert download_response.status_code == 404

    delete_response = await client.delete(
        f"/api/v1/students/{student_a['id']}/documents/{document['id']}", headers=headers_b
    )
    assert delete_response.status_code == 404


async def test_document_actions_require_permission_per_action(client: AsyncClient) -> None:
    data = await register_school(client, "docrbac")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]
    student = await _create_student(client, headers_admin, school_id)

    upload = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers_admin,
        data={"document_type": "Bulletin"},
        files={"file": ("bulletin.pdf", io.BytesIO(valid_pdf_bytes()), "application/pdf")},
    )
    document = upload.json()

    # PARENT n'a NI students.read NI students.manage (voir rbac/seed.py) — contrairement à TEACHER,
    # qui a students.read de base (ce test vérifie donc un rôle sans aucune des deux permissions,
    # pas un rôle scoping par affectation de classe — hors périmètre de ce sprint).
    parent_data = await register_school(client, "docrbac-parent")
    await assign_role(parent_data["user"]["id"], "PARENT", organization_id=organization_id, school_id=school_id)
    headers_parent = {"Authorization": f"Bearer {await _login(client, parent_data['user']['email'])}"}

    read_response = await client.get(
        f"/api/v1/students/{student['id']}/documents/{document['id']}", headers=headers_parent
    )
    assert read_response.status_code == 403

    delete_response = await client.delete(
        f"/api/v1/students/{student['id']}/documents/{document['id']}", headers=headers_parent
    )
    assert delete_response.status_code == 403


async def test_document_upload_db_failure_does_not_leave_orphan_file(client: AsyncClient) -> None:
    """Même principe que test_photo_upload_db_failure_does_not_leave_orphan_file ci-dessus : appel
    direct de la fonction du routeur avec un `flush` patché à l'instance, jamais au niveau classe."""
    from app.core.storage import storage as shared_storage
    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.students.router import upload_student_document
    from app.modules.users.models import User

    data = await register_school(client, "docrollback")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    student = await _create_student(client, headers, data["school"]["id"])

    user_id = uuid_module.UUID(data["user"]["id"])
    student_id = uuid_module.UUID(student["id"])

    async def failing_flush() -> None:
        raise RuntimeError("flush simulé en échec (test rollback document)")

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, user_id)
        current_user = await db.get(User, user_id)
        assert current_user is not None
        setattr(db, "flush", failing_flush)

        upload = UploadFile(file=io.BytesIO(valid_pdf_bytes()), filename="bulletin.pdf")
        with pytest.raises(RuntimeError):
            await upload_student_document(student_id, db, current_user, "Bulletin", upload)
        delattr(db, "flush")

    list_response = await client.get(f"/api/v1/students/{student['id']}/documents", headers=headers)
    assert list_response.json() == []

    documents_dir = shared_storage._resolve(f"students/{student['id']}/documents")  # type: ignore[attr-defined]
    leftover_files = [p for p in documents_dir.rglob("*") if p.is_file()] if documents_dir.exists() else []
    assert leftover_files == []


# --- INSCRIPTIONS : classe hors école / RBAC / isolation ---------------------------------------------
async def test_enrollment_rejects_class_from_another_school(client: AsyncClient) -> None:
    school_a = await register_school(client, "enrollcrossa")
    school_b = await register_school(client, "enrollcrossb")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    year_b = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_b["school"]["id"],
                "name": "2026-2027",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2027, 6, 30)),
            },
            headers=headers_b,
        )
    ).json()
    level_b = (
        await client.post(
            "/api/v1/education-levels", json={"school_id": school_b["school"]["id"], "name": "CE1"}, headers=headers_b
        )
    ).json()
    class_b = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year_b["id"], "education_level_id": level_b["id"], "name": "A"},
            headers=headers_b,
        )
    ).json()

    student_a = await _create_student(client, headers_a, school_a["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student_a['id']}/enrollments",
        json={"class_id": class_b["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers_a,
    )
    assert response.status_code == 400


async def test_enrollment_requires_manage_permission(client: AsyncClient) -> None:
    data = await register_school(client, "enrollrbac")
    headers_admin = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    organization_id = data["organization"]["id"]

    year = (
        await client.post(
            "/api/v1/academic-years",
            json={
                "school_id": school_id,
                "name": "2026-2027",
                "start_date": str(date(2026, 9, 1)),
                "end_date": str(date(2027, 6, 30)),
            },
            headers=headers_admin,
        )
    ).json()
    level = (
        await client.post("/api/v1/education-levels", json={"school_id": school_id, "name": "CE1"}, headers=headers_admin)
    ).json()
    school_class = (
        await client.post(
            "/api/v1/classes",
            json={"academic_year_id": year["id"], "education_level_id": level["id"], "name": "A"},
            headers=headers_admin,
        )
    ).json()
    student = await _create_student(client, headers_admin, school_id)

    teacher_data = await register_school(client, "enrollrbac-teacher")
    await assign_role(teacher_data["user"]["id"], "TEACHER", organization_id=organization_id, school_id=school_id)
    headers_teacher = {"Authorization": f"Bearer {await _login(client, teacher_data['user']['email'])}"}

    response = await client.post(
        f"/api/v1/students/{student['id']}/enrollments",
        json={"class_id": school_class["id"], "enrollment_date": str(date(2026, 9, 1))},
        headers=headers_teacher,
    )
    assert response.status_code in (403, 404)


async def test_enrollment_list_tenant_isolation(client: AsyncClient) -> None:
    school_a = await register_school(client, "enrolllistisoa")
    school_b = await register_school(client, "enrolllistisob")
    headers_a = {"Authorization": f"Bearer {await _login(client, school_a['user']['email'])}"}
    headers_b = {"Authorization": f"Bearer {await _login(client, school_b['user']['email'])}"}

    student_a = await _create_student(client, headers_a, school_a["school"]["id"])

    response = await client.get(f"/api/v1/students/{student_a['id']}/enrollments", headers=headers_b)
    assert response.status_code == 404
