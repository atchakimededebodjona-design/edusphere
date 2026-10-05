"""POST /api/v1/platform/organizations — seul point d'entrée de création d'une organisation.

Couvre : autorisation côté backend (401 / 403 / 201), création atomique (organisation, école,
SCHOOL_ADMIN), absence de fuite de mot de passe, conflits (409), rollback complet, isolation tenant
et disparition de l'ancienne inscription publique.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.security import hash_password
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.organizations.models import Organization
from app.modules.users.models import User
from tests.conftest import assign_role, create_platform_admin, register_school, unique_email, unique_slug

ENDPOINT = "/api/v1/platform/organizations"
PASSWORD = "SuperSecret123"


def _payload(prefix: str, admin_email: str | None = None) -> dict:
    return {
        "organization": {
            "name": f"{prefix} Group",
            "slug": unique_slug(prefix),
            "country_code": "tg",
            "timezone": "Africa/Lome",
            "currency": "XOF",
        },
        "school": {
            "name": f"{prefix} School",
            "slug": "principale",
            "address": "12 rue de la Paix, Lomé",
            "phone": "+22812345678",
            "email": f"contact.{uuid.uuid4().hex[:8]}@edusphere-pytest.tg",
            "timezone": "Africa/Lome",
            "currency": "XOF",
        },
        "admin": {
            "full_name": f"Admin {prefix}",
            "email": admin_email or unique_email(f"admin.{prefix}"),
            "phone": "+22898765432",
            "password": PASSWORD,
        },
    }


async def _platform_headers(client: AsyncClient) -> dict[str, str]:
    admin = await create_platform_admin(client, "orgplatform")
    return {"Authorization": f"Bearer {admin['tokens']['access_token']}"}


async def _create_as_platform(client: AsyncClient, payload: dict) -> dict:
    response = await client.post(ENDPOINT, json=payload, headers=await _platform_headers(client))
    assert response.status_code == 201, response.text
    return response.json()


async def _user_with_role(client: AsyncClient, role_code: str, organization_id: str, school_id: str) -> dict[str, str]:
    """Compte non plateforme rattaché à une école, créé directement en base (même motif que
    create_platform_admin dans conftest)."""
    user_id = uuid.uuid4()
    email = unique_email(f"{role_code.lower()}.orgtest")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            User(
                id=user_id,
                email=email,
                full_name=f"{role_code} test",
                hashed_password=hash_password(PASSWORD),
                is_active=True,
                is_platform_admin=False,
            )
        )
        await db.commit()
    await assign_role(str(user_id), role_code, organization_id, school_id)
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def _organization_count_by_slug(slug: str) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(select(func.count()).select_from(Organization).where(Organization.slug == slug))
        return result.scalar_one()


# --- 1 à 5 : création réussie, liens entre les entités, rôle -----------------------------------
async def test_platform_admin_creates_organization_with_school_and_admin(client: AsyncClient) -> None:
    payload = _payload("createok")
    body = (await _create_as_platform(client, payload))

    assert body["organization"]["slug"] == payload["organization"]["slug"]
    assert body["organization"]["country_code"] == "TG"
    assert body["organization"]["timezone"] == "Africa/Lome"
    assert body["admin_role_code"] == "SCHOOL_ADMIN"


async def test_created_school_is_linked_to_created_organization(client: AsyncClient) -> None:
    body = await _create_as_platform(client, _payload("schoollink"))

    assert body["school"]["organization_id"] == body["organization"]["id"]
    assert body["school"]["slug"] == "principale"
    assert body["school"]["timezone"] == "Africa/Lome"


async def test_created_admin_user_is_not_platform_admin(client: AsyncClient) -> None:
    payload = _payload("adminuser")
    body = await _create_as_platform(client, payload)

    assert body["admin"]["email"] == payload["admin"]["email"].lower()
    assert body["admin"]["full_name"] == payload["admin"]["full_name"]
    assert body["admin"]["is_platform_admin"] is False


async def test_created_admin_has_school_admin_role_scoped_to_organization(client: AsyncClient) -> None:
    payload = _payload("adminrole")
    body = await _create_as_platform(client, payload)

    login = await client.post("/api/v1/auth/login", json={"email": payload["admin"]["email"], "password": PASSWORD})
    assert login.status_code == 200, login.text
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {login.json()['access_token']}"}
    )
    assert me.status_code == 200
    roles = me.json()["roles"]
    assert roles == [
        {"role_code": "SCHOOL_ADMIN", "organization_id": body["organization"]["id"], "school_id": None}
    ]


# --- 6 à 7 : mot de passe ----------------------------------------------------------------------
async def test_admin_password_is_stored_hashed_only(client: AsyncClient) -> None:
    payload = _payload("hashcheck")
    await _create_as_platform(client, payload)

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        hashed = (
            await db.execute(select(User.hashed_password).where(User.email == payload["admin"]["email"].lower()))
        ).scalar_one()
    assert hashed != PASSWORD
    assert hashed.startswith("$2")  # bcrypt, mécanisme de app/core/security.py


async def test_password_and_hash_never_returned(client: AsyncClient) -> None:
    response = await client.post(ENDPOINT, json=_payload("nosecret"), headers=await _platform_headers(client))
    assert response.status_code == 201
    assert PASSWORD not in response.text
    assert "hashed_password" not in response.text
    assert "$2b$" not in response.text and "$2a$" not in response.text


async def test_creation_does_not_log_the_session_in_as_school_admin(client: AsyncClient) -> None:
    """La réponse ne porte aucun token : le platform admin reste seul connecté."""
    response = await client.post(ENDPOINT, json=_payload("noautologin"), headers=await _platform_headers(client))
    assert response.status_code == 201
    assert "tokens" not in response.json()
    assert "access_token" not in response.text


# --- 8 à 9 : autorisation côté backend ---------------------------------------------------------
async def test_unauthenticated_creation_returns_401(client: AsyncClient) -> None:
    response = await client.post(ENDPOINT, json=_payload("anon"))
    assert response.status_code == 401


async def test_school_admin_cannot_create_organization(client: AsyncClient) -> None:
    data = await register_school(client, "schooladminforbidden")
    headers = {"Authorization": f"Bearer {data['tokens']['access_token']}"}
    response = await client.post(ENDPOINT, json=_payload("byschooladmin"), headers=headers)
    assert response.status_code == 403


async def test_teacher_cannot_create_organization(client: AsyncClient) -> None:
    data = await register_school(client, "teacherforbidden")
    headers = await _user_with_role(
        client, "TEACHER", data["organization"]["id"], data["school"]["id"]
    )
    response = await client.post(ENDPOINT, json=_payload("byteacher"), headers=headers)
    assert response.status_code == 403


async def test_parent_cannot_create_organization(client: AsyncClient) -> None:
    data = await register_school(client, "parentforbidden")
    headers = await _user_with_role(client, "PARENT", data["organization"]["id"], data["school"]["id"])
    response = await client.post(ENDPOINT, json=_payload("byparent"), headers=headers)
    assert response.status_code == 403


# --- 10 à 11 : conflits ------------------------------------------------------------------------
async def test_duplicate_organization_slug_returns_409(client: AsyncClient) -> None:
    headers = await _platform_headers(client)
    first = _payload("dupslug")
    response = await client.post(ENDPOINT, json=first, headers=headers)
    assert response.status_code == 201, response.text

    second = _payload("dupslug2")
    second["organization"]["slug"] = first["organization"]["slug"]
    conflict = await client.post(ENDPOINT, json=second, headers=headers)
    assert conflict.status_code == 409


async def test_duplicate_admin_email_returns_409(client: AsyncClient) -> None:
    headers = await _platform_headers(client)
    first = _payload("dupemail")
    response = await client.post(ENDPOINT, json=first, headers=headers)
    assert response.status_code == 201, response.text

    second = _payload("dupemail2", admin_email=first["admin"]["email"])
    conflict = await client.post(ENDPOINT, json=second, headers=headers)
    assert conflict.status_code == 409


# --- 12 : atomicité ----------------------------------------------------------------------------
async def test_failure_mid_transaction_rolls_back_everything(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une erreur après l'insertion de l'organisation et de l'école (hash du mot de passe ici)
    doit annuler toute la transaction : aucune organisation orpheline ne reste en base."""
    headers = await _platform_headers(client)
    payload = _payload("rollback")

    def _boom(_: str) -> str:
        raise RuntimeError("simulated failure")

    monkeypatch.setattr("app.modules.platform.service.hash_password", _boom)
    with pytest.raises(RuntimeError, match="simulated failure"):
        await client.post(ENDPOINT, json=payload, headers=headers)

    assert await _organization_count_by_slug(payload["organization"]["slug"]) == 0


# --- 13 : isolation tenant ---------------------------------------------------------------------
async def test_new_organization_is_invisible_to_other_tenants(client: AsyncClient) -> None:
    other = await register_school(client, "isolationother")
    created = await _create_as_platform(client, _payload("isolationnew"))

    other_headers = {"Authorization": f"Bearer {other['tokens']['access_token']}"}
    response = await client.get(f"/api/v1/organizations/{created['organization']['id']}", headers=other_headers)
    assert response.status_code in (403, 404)


# --- 14 : ancienne inscription publique -------------------------------------------------------
async def test_legacy_public_register_cannot_create_tenant(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Legacy Org",
            "organization_slug": unique_slug("legacy"),
            "country_code": "TG",
            "school_name": "Legacy School",
            "school_slug": "principale",
            "admin_full_name": "Legacy Admin",
            "admin_email": unique_email("legacy.admin"),
            "admin_password": PASSWORD,
        },
    )
    assert response.status_code == 404


# --- validation des entrées --------------------------------------------------------------------
async def test_invalid_timezone_returns_422(client: AsyncClient) -> None:
    payload = _payload("badtz")
    payload["organization"]["timezone"] = "Mars/Olympus"
    response = await client.post(ENDPOINT, json=payload, headers=await _platform_headers(client))
    assert response.status_code == 422


async def test_invalid_organization_slug_returns_422(client: AsyncClient) -> None:
    payload = _payload("badslug")
    payload["organization"]["slug"] = "Mauvais Slug"
    response = await client.post(ENDPOINT, json=payload, headers=await _platform_headers(client))
    assert response.status_code == 422


async def test_missing_admin_section_returns_422(client: AsyncClient) -> None:
    payload = _payload("noadmin")
    del payload["admin"]
    response = await client.post(ENDPOINT, json=payload, headers=await _platform_headers(client))
    assert response.status_code == 422
