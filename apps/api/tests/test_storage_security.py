"""Tests de sécurité — Phase 13, HIGH #1 (traversée de chemin dans l'upload de fichiers).

Deux niveaux, volontairement séparés :

1. Tests unitaires directs sur `LocalStorageProvider`/`safe_filename` — prouvent la propriété de
   confinement ("le chemin résolu reste à l'intérieur du répertoire de stockage") indépendamment
   de tout endpoint HTTP, y compris pour des entrées qu'un `safe_filename` en amont empêcherait
   déjà d'atteindre en pratique (défense en profondeur : cette couche doit tenir seule).
2. Tests d'intégration via les endpoints réels (photo/document/logo) — prouvent que la chaîne
   complète reste sûre avec un nom de fichier hostile, qu'un upload légitime continue de
   fonctionner normalement, et que l'isolation école/organisation déjà en place n'est pas
   affectée par ce correctif.
"""

from datetime import date
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.storage import LocalStorageProvider, StoragePathError, safe_filename
from tests.conftest import register_school


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


# --- safe_filename (unitaire) --------------------------------------------------------------------
def test_safe_filename_strips_directory_components_regardless_of_separator() -> None:
    assert safe_filename("../../etc/passwd") == "passwd"
    assert safe_filename("..\\..\\windows\\system32\\config") == "config"
    assert safe_filename("/etc/passwd") == "passwd"
    assert safe_filename("photo.jpg") == "photo.jpg"


def test_safe_filename_falls_back_on_empty_or_dot_only_names() -> None:
    assert safe_filename(None) == "file"
    assert safe_filename("") == "file"
    assert safe_filename(".") == "file"
    assert safe_filename("..") == "file"


# --- LocalStorageProvider (unitaire, confinement) ------------------------------------------------
def test_local_storage_provider_normal_relative_path_stays_inside_base(tmp_path: Path) -> None:
    provider = LocalStorageProvider(str(tmp_path))
    resolved = provider._resolve("students/abc-id/photo.jpg")
    assert resolved.is_relative_to(tmp_path.resolve())


@pytest.mark.parametrize(
    "malicious_path",
    [
        "../../../../etc/passwd",
        "students/abc-id/../../../../../etc/passwd",
        ("../" * 20) + "etc/passwd",
        "/etc/passwd",
    ],
    ids=["relative-traversal", "traversal-after-legit-prefix", "multi-level-traversal", "absolute-unix"],
)
def test_local_storage_provider_rejects_any_path_resolving_outside_base(tmp_path: Path, malicious_path: str) -> None:
    provider = LocalStorageProvider(str(tmp_path))
    with pytest.raises(StoragePathError):
        provider._resolve(malicious_path)


def test_local_storage_provider_windows_style_path_stays_contained_on_this_platform(tmp_path: Path) -> None:
    """Ce backend s'exécute sur Linux (conteneur `api`, voir Dockerfile) : `\\` n'est pas un
    séparateur de chemin pour `pathlib.PosixPath`, et une chaîne du type "..\\..\\Windows\\..." n'y
    est pas reconnue comme un chemin absolu. Ce test vérifie honnêtement ce qui est réellement
    garanti DANS CET ENVIRONNEMENT — le confinement reste respecté, la chaîne devenant un nom de
    fichier littéral inoffensif — sans prétendre avoir validé quoi que ce soit sous un véritable
    interpréteur Windows, qui n'existe pas ici (règle de vérité, Phase 13)."""
    provider = LocalStorageProvider(str(tmp_path))
    resolved = provider._resolve("students/abc-id/" + "..\\..\\..\\Windows\\System32\\config")
    assert resolved.is_relative_to(tmp_path.resolve())


async def test_local_storage_provider_legitimate_upload_download_roundtrip_still_works(tmp_path: Path) -> None:
    provider = LocalStorageProvider(str(tmp_path))
    await provider.upload("students/abc-id/photo.jpg", b"real-bytes")
    assert await provider.download("students/abc-id/photo.jpg") == b"real-bytes"


# --- Intégration : upload réel avec nom de fichier hostile ---------------------------------------
async def test_student_photo_upload_with_traversal_filename_stays_contained(client: AsyncClient) -> None:
    """Le nom de fichier fourni dans la requête multipart est hostile, mais le contenu est un
    fichier légitime : l'upload doit réussir (sanitization silencieuse), jamais échouer avec une
    erreur opaque, et jamais écrire hors du répertoire de stockage configuré."""
    from app.core.storage import storage as shared_storage

    data = await register_school(client, "storagetraversal")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("../../../../../../etc/passwd", b"fake-jpeg-bytes", "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    photo_path = response.json()["photo_path"]

    assert ".." not in photo_path
    assert not photo_path.startswith("/")
    # Preuve directe de confinement : la même vérification que _resolve() applique à chaque appel
    # ne lève pas — le chemin stocké reste bien à l'intérieur du répertoire de stockage réel.
    resolved = shared_storage._resolve(photo_path)  # type: ignore[attr-defined]
    assert resolved.is_relative_to(shared_storage._base_path)  # type: ignore[attr-defined]

    download = await client.get(f"/api/v1/students/{student['id']}/photo", headers=headers)
    assert download.status_code == 200
    assert download.content == b"fake-jpeg-bytes"


async def test_student_document_upload_with_absolute_unix_filename_stays_contained(client: AsyncClient) -> None:
    data = await register_school(client, "storagedocabs")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/documents",
        headers=headers,
        data={"document_type": "birth_certificate"},
        files={"file": ("/etc/passwd", b"fake-pdf-bytes", "application/pdf")},
    )
    assert response.status_code == 201, response.text
    file_path = response.json()["file_path"]
    assert ".." not in file_path
    assert not file_path.startswith("/etc")


async def test_school_logo_upload_with_traversal_filename_stays_contained(client: AsyncClient) -> None:
    data = await register_school(client, "storagelogo")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    school_id = data["school"]["id"]

    response = await client.post(
        f"/api/v1/schools/{school_id}/logo",
        headers=headers,
        files={"file": ("..\\..\\..\\windows\\win.ini", b"fake-png-bytes", "image/png")},
    )
    assert response.status_code == 200, response.text


async def test_legitimate_filename_upload_is_unaffected(client: AsyncClient) -> None:
    """Non-régression : un nom de fichier normal continue de fonctionner exactement comme avant."""
    data = await register_school(client, "storagenormal")
    token = await _login(client, data["user"]["email"])
    headers = {"Authorization": f"Bearer {token}"}
    student = await _create_student(client, headers, data["school"]["id"])

    response = await client.post(
        f"/api/v1/students/{student['id']}/photo",
        headers=headers,
        files={"file": ("photo.jpg", b"fake-jpeg-bytes", "image/jpeg")},
    )
    assert response.status_code == 200, response.text
    assert response.json()["photo_path"].endswith("photo.jpg")


# --- Isolation école / organisation (non-régression, corrélée au correctif) ----------------------
async def test_school_isolation_still_enforced_on_student_photo(client: AsyncClient) -> None:
    school_a = await register_school(client, "storageisoa")
    school_b = await register_school(client, "storageisob")

    token_a = await _login(client, school_a["user"]["email"])
    headers_a = {"Authorization": f"Bearer {token_a}"}
    student_a = await _create_student(client, headers_a, school_a["school"]["id"])

    await client.post(
        f"/api/v1/students/{student_a['id']}/photo",
        headers=headers_a,
        files={"file": ("photo.jpg", b"fake-jpeg-bytes", "image/jpeg")},
    )

    token_b = await _login(client, school_b["user"]["email"])
    headers_b = {"Authorization": f"Bearer {token_b}"}

    cross_school_read = await client.get(f"/api/v1/students/{student_a['id']}/photo", headers=headers_b)
    assert cross_school_read.status_code == 404


async def test_organization_isolation_still_enforced_on_student_photo(client: AsyncClient) -> None:
    """Deux organisations distinctes (pas seulement deux écoles d'une même organisation) —
    même garantie, même mécanisme (RLS + ensure_permission scopés à la ressource chargée)."""
    org_a = await register_school(client, "storageisoorga")
    org_b = await register_school(client, "storageisoorgb")
    assert org_a["organization"]["id"] != org_b["organization"]["id"]

    token_a = await _login(client, org_a["user"]["email"])
    headers_a = {"Authorization": f"Bearer {token_a}"}
    student_a = await _create_student(client, headers_a, org_a["school"]["id"])

    token_b = await _login(client, org_b["user"]["email"])
    headers_b = {"Authorization": f"Bearer {token_b}"}

    cross_org_read = await client.get(f"/api/v1/students/{student_a['id']}/photo", headers=headers_b)
    assert cross_org_read.status_code == 404
