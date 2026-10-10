"""Correctif d'autorité urgent (P0-1 / P0-2, audit PR #21).

P0-1 : un admin d'une organisation B ne peut plus rattacher un compte d'une organisation A via
POST /users, ni (défense en profondeur, si un tel rattachement existait déjà) le désactiver ou
changer son rôle via PATCH /users/{id}.
P0-2 : un admin d'UNE école ne peut plus désactiver ni rétrograder un compte qui détient des
droits hors de son périmètre (admin org-wide, compte d'une autre école).
Règle : l'acteur doit couvrir l'INTÉGRALITÉ des rôles du compte cible ; refus générique 409.
Les cas normaux (compte entièrement dans le périmètre de l'acteur) restent autorisés.
"""

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from tests.conftest import assign_role, create_platform_admin, register_school, unique_email, unique_slug
from tests.pr17_helpers import PASSWORD, auth, create_partner, create_platform_owner, login

ATTACH_REFUSED = "This account cannot be attached to a school"
MODIFY_REFUSED = "This account cannot be modified from this school"


async def _org_with_schools(client: AsyncClient, prefix: str) -> dict:
    """Organisation A : Alice SCHOOL_ADMIN org-wide (école principale), Bob admin scopé du Collège,
    Claire admin scopée du Lycée (écoles ajoutées par le Platform Owner, PR #19/#20)."""
    owner = await create_platform_owner(client, f"{prefix}owner")
    org = await register_school(client, prefix)
    org_id = org["organization"]["id"]
    env = {
        "owner": owner,
        "org_id": org_id,
        "main_school": org["school"]["id"],
        "alice": {"id": org["user"]["id"], "email": org["user"]["email"], "headers": auth(org["tokens"]["access_token"])},
    }
    for key, name in (("bob", "College"), ("claire", "Lycee")):
        email = unique_email(f"{prefix}{key}")
        response = await client.post(
            f"/api/v1/platform/organizations/{org_id}/schools",
            json={"school": {"name": f"{name} {prefix}", "slug": unique_slug("s")}, "admin": {"full_name": key, "email": email, "password": PASSWORD}},
            headers=owner["headers"],
        )
        assert response.status_code == 201, response.text
        env[key] = {
            "id": response.json()["admin"]["id"],
            "email": email,
            "school": response.json()["school"]["id"],
            "headers": await login(client, email),
        }
    return env


async def _create_user(client: AsyncClient, headers: dict, school_id: str, role_code: str, email: str | None = None):
    return await client.post(
        "/api/v1/users",
        json={"email": email or unique_email(role_code.lower()), "full_name": f"Compte {role_code}", "school_id": school_id, "role_code": role_code},
        headers=headers,
    )


async def _roles(user_id: str) -> list[tuple[str, str | None, str | None]]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = (
            await db.execute(
                select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == uuid.UUID(user_id))
            )
        ).all()
    return sorted((c, str(u.organization_id) if u.organization_id else None, str(u.school_id) if u.school_id else None) for u, c in rows)


async def _active(user_id: str) -> bool:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uuid.UUID(user_id))
        assert user is not None
        return user.is_active


# === P0-1 — inter-organisation ======================================================================
async def test_p0_1_cross_org_attach_is_refused(client: AsyncClient) -> None:
    org_a = await register_school(client, "p01a")
    org_b = await register_school(client, "p01b")
    before = await _roles(org_a["user"]["id"])
    response = await _create_user(
        client, auth(org_b["tokens"]["access_token"]), org_b["school"]["id"], "TEACHER", org_a["user"]["email"]
    )
    assert response.status_code == 409
    assert response.json()["detail"] == ATTACH_REFUSED
    assert await _roles(org_a["user"]["id"]) == before


async def test_p0_1_cross_org_patch_refused_even_if_attach_preexisted(client: AsyncClient) -> None:
    """Défense en profondeur : un rattachement inter-organisation antérieur au correctif (créé ici
    directement en base) ne permet ni de désactiver ni de rétrograder le compte."""
    org_a = await register_school(client, "p01pa")
    org_b = await register_school(client, "p01pb")
    alice = org_a["user"]
    await assign_role(alice["id"], "TEACHER", org_b["organization"]["id"], org_b["school"]["id"])
    before = await _roles(alice["id"])
    b_headers = auth(org_b["tokens"]["access_token"])
    for body in ({"is_active": False}, {"role_code": "STUDENT"}):
        response = await client.patch(f"/api/v1/users/{alice['id']}", json={"school_id": org_b["school"]["id"], **body}, headers=b_headers)
        assert response.status_code == 409, (body, response.text)
        assert response.json()["detail"] == MODIFY_REFUSED
    assert await _active(alice["id"]) is True
    assert await _roles(alice["id"]) == before
    assert (await client.post("/api/v1/auth/login", json={"email": alice["email"], "password": PASSWORD})).status_code == 200


# === P0-2 — admin d'une école vs compte plus large ======================================================
async def test_p0_2_school_admin_cannot_deactivate_or_demote_org_wide_admin(client: AsyncClient) -> None:
    env = await _org_with_schools(client, "p02")
    alice, bob = env["alice"], env["bob"]
    # Rattacher Alice (même organisation) comme TEACHER au Collège reste permis : simple ajout.
    attach = await _create_user(client, bob["headers"], bob["school"], "TEACHER", alice["email"])
    assert attach.status_code == 201, attach.text
    before = await _roles(alice["id"])
    for body in ({"is_active": False}, {"role_code": "STUDENT"}, {"role_code": "SCHOOL_ADMIN"}):
        response = await client.patch(f"/api/v1/users/{alice['id']}", json={"school_id": bob["school"], **body}, headers=bob["headers"])
        assert response.status_code == 409, (body, response.text)
        assert response.json()["detail"] == MODIFY_REFUSED
    assert await _active(alice["id"]) is True
    assert await _roles(alice["id"]) == before


async def test_p0_2_school_admin_cannot_touch_account_with_roles_in_another_school(client: AsyncClient) -> None:
    env = await _org_with_schools(client, "p02x")
    bob, claire = env["bob"], env["claire"]
    created = await _create_user(client, claire["headers"], claire["school"], "TEACHER")
    teacher = created.json()["user"]
    # Bob rattache cet enseignant (même organisation) au Collège : permis.
    attach = await _create_user(client, bob["headers"], bob["school"], "TEACHER", teacher["email"])
    assert attach.status_code == 201
    for body in ({"is_active": False}, {"role_code": "STAFF"}):
        response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": bob["school"], **body}, headers=bob["headers"])
        assert response.status_code == 409, body
    # Claire non plus : le compte a aussi un rôle au Collège, hors de SON périmètre.
    response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": claire["school"], "is_active": False}, headers=claire["headers"])
    assert response.status_code == 409
    assert await _active(teacher["id"]) is True


# === Régressions : cas normaux toujours permis ===========================================================
async def test_school_admin_still_manages_accounts_entirely_in_own_school(client: AsyncClient) -> None:
    env = await _org_with_schools(client, "p0reg")
    bob = env["bob"]
    teacher = (await _create_user(client, bob["headers"], bob["school"], "TEACHER")).json()["user"]
    response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": bob["school"], "role_code": "STAFF"}, headers=bob["headers"])
    assert response.status_code == 200, response.text
    assert await _roles(teacher["id"]) == [("STAFF", env["org_id"], bob["school"])]
    response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": bob["school"], "is_active": False}, headers=bob["headers"])
    assert response.status_code == 200
    assert await _active(teacher["id"]) is False
    response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": bob["school"], "is_active": True}, headers=bob["headers"])
    assert response.status_code == 200 and await _active(teacher["id"]) is True


async def test_org_wide_admin_manages_accounts_across_schools_of_own_org(client: AsyncClient) -> None:
    env = await _org_with_schools(client, "p0org")
    alice, bob, claire = env["alice"], env["bob"], env["claire"]
    teacher = (await _create_user(client, bob["headers"], bob["school"], "TEACHER")).json()["user"]
    assert (await _create_user(client, claire["headers"], claire["school"], "TEACHER", teacher["email"])).status_code == 201
    response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": bob["school"], "is_active": False}, headers=alice["headers"])
    assert response.status_code == 200, response.text
    assert await _active(teacher["id"]) is False
    response = await client.patch(f"/api/v1/users/{teacher['id']}", json={"school_id": claire["school"], "role_code": "STAFF"}, headers=alice["headers"])
    assert response.status_code == 200
    # Alice peut aussi gérer Bob (admin scopé de SON organisation).
    response = await client.patch(f"/api/v1/users/{bob['id']}", json={"school_id": bob["school"], "is_active": False}, headers=alice["headers"])
    assert response.status_code == 200


async def test_super_admin_keeps_global_authority(client: AsyncClient) -> None:
    env = await _org_with_schools(client, "p0super")
    super_admin = await create_platform_admin(client, "p0super")
    headers = auth(super_admin["tokens"]["access_token"])
    response = await client.patch(
        f"/api/v1/users/{env['bob']['id']}", json={"school_id": env["bob"]["school"], "is_active": False}, headers=headers
    )
    assert response.status_code == 200


# === Politique de rattachement (même règle que PR #20) ==================================================
async def test_attach_policy_same_org_rules(client: AsyncClient) -> None:
    env = await _org_with_schools(client, "p0att")
    alice, bob, claire = env["alice"], env["bob"], env["claire"]
    teacher = (await _create_user(client, claire["headers"], claire["school"], "TEACHER")).json()["user"]
    director = (await _create_user(client, claire["headers"], claire["school"], "DIRECTOR")).json()["user"]

    # Rôle non-admin pour un compte de la même organisation : permis.
    assert (await _create_user(client, bob["headers"], bob["school"], "STAFF", teacher["email"])).status_code == 201
    # SCHOOL_ADMIN pour un simple TEACHER de l'organisation : refusé (jamais d'élévation silencieuse).
    refused = await _create_user(client, bob["headers"], bob["school"], "SCHOOL_ADMIN", teacher["email"])
    assert refused.status_code == 409 and refused.json()["detail"] == ATTACH_REFUSED
    # SCHOOL_ADMIN pour un DIRECTOR de l'organisation : permis (règle PR #20).
    assert (await _create_user(client, bob["headers"], bob["school"], "SCHOOL_ADMIN", director["email"])).status_code == 201
    # SCHOOL_ADMIN pour l'admin org-wide : déjà couvert, aucun rôle scopé ajouté.
    covered = await _create_user(client, bob["headers"], bob["school"], "SCHOOL_ADMIN", alice["email"])
    assert covered.status_code == 201
    assert await _roles(alice["id"]) == [("SCHOOL_ADMIN", env["org_id"], None)]


async def test_attach_refuses_inactive_and_platform_accounts(client: AsyncClient) -> None:
    env = await _org_with_schools(client, "p0inact")
    bob, claire = env["bob"], env["claire"]
    teacher = (await _create_user(client, claire["headers"], claire["school"], "TEACHER")).json()["user"]
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uuid.UUID(teacher["id"]))
        assert user is not None
        user.is_active = False
        await db.commit()
    response = await _create_user(client, bob["headers"], bob["school"], "TEACHER", teacher["email"])
    assert response.status_code == 409 and response.json()["detail"] == ATTACH_REFUSED

    super_admin = await create_platform_admin(client, "p0inactsuper")
    partner = await create_partner(client, env["owner"]["headers"], "p0inactpartner")
    for email in (super_admin["email"], partner["email"], env["owner"]["email"]):
        response = await _create_user(client, bob["headers"], bob["school"], "TEACHER", email)
        assert response.status_code == 409, email
        assert response.json()["detail"] == ATTACH_REFUSED
