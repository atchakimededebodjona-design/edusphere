"""P1-2 — POST /api/v1/schools n'est plus un point d'entrée de création d'école.

Toute création passe par le workflow d'enrôlement central (PR #19/#20) :
- POST /api/v1/platform/organizations/{id}/schools (PLATFORM_OWNER / SUPER_ADMIN)
- POST /api/v1/partner/organizations/{id}/schools  (PARTNER_ADMIN, son seul périmètre)
Ces parcours créent l'école, résolvent son administrateur par le résolveur central et tracent la
source d'acquisition (PLATFORM_OWNER ou PARTNER, jamais inventée), atomiquement.
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.partners.models import PartnerSchoolEnrollment
from app.modules.rbac.models import Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User
from tests.conftest import create_platform_admin, register_school, unique_email, unique_slug
from tests.pr17_helpers import PASSWORD, auth, create_partner, create_platform_owner, enroll_school_as_partner

MOVED = (
    "School creation goes through the enrollment workflow: "
    "POST /api/v1/platform/organizations/{organization_id}/schools or "
    "POST /api/v1/partner/organizations/{organization_id}/schools"
)


async def _school_count(organization_id: str) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return int(
            (
                await db.execute(
                    select(func.count()).select_from(School).where(School.organization_id == uuid.UUID(organization_id))
                )
            ).scalar_one()
        )


async def _enrollment(school_id: str) -> PartnerSchoolEnrollment | None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return (
            await db.execute(select(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.school_id == uuid.UUID(school_id)))
        ).scalar_one_or_none()


async def _roles(user_id: str) -> list[tuple[str, str | None, str | None]]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = (
            await db.execute(
                select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == uuid.UUID(user_id))
            )
        ).all()
    return sorted((c, str(u.organization_id) if u.organization_id else None, str(u.school_id) if u.school_id else None) for u, c in rows)


def _add_payload(name: str, admin_email: str, slug: str | None = None, password: str | None = None) -> dict:
    admin: dict = {"email": admin_email}
    if password is not None:
        admin.update({"full_name": f"Admin {name}", "password": password})
    return {"school": {"name": name, "slug": slug or unique_slug("ecole")}, "admin": admin}


# === 1 — le bypass historique n'existe plus ===========================================================
async def test_1_post_schools_no_longer_creates_anything_for_any_caller(client: AsyncClient) -> None:
    org = await register_school(client, "p12bypass")
    org_id = org["organization"]["id"]
    super_admin = await create_platform_admin(client, "p12bypasssuper")
    owner = await create_platform_owner(client, "p12bypassowner")
    callers = {
        "org-wide SCHOOL_ADMIN": auth(org["tokens"]["access_token"]),
        "SUPER_ADMIN": auth(super_admin["tokens"]["access_token"]),
        "PLATFORM_OWNER": owner["headers"],
    }
    for label, headers in callers.items():
        response = await client.post(
            "/api/v1/schools",
            json={"organization_id": org_id, "name": f"Bypass {label}", "slug": unique_slug("bypass")},
            headers=headers,
        )
        assert response.status_code == 410, (label, response.text)
        assert response.json()["detail"] == MOVED
    assert await _school_count(org_id) == 1
    assert (await client.post("/api/v1/schools", json={})).status_code == 401


async def test_1_school_read_update_logo_routes_unchanged(client: AsyncClient) -> None:
    org = await register_school(client, "p12keep")
    headers = auth(org["tokens"]["access_token"])
    school_id = org["school"]["id"]
    assert (await client.get(f"/api/v1/schools/{school_id}", headers=headers)).status_code == 200
    assert (await client.get(f"/api/v1/schools?organization_id={org['organization']['id']}", headers=headers)).status_code == 200
    patched = await client.patch(f"/api/v1/schools/{school_id}", json={"name": "Nom modifié"}, headers=headers)
    assert patched.status_code == 200 and patched.json()["name"] == "Nom modifié"


# === 2 / 7 — acteurs non autorisés et inter-organisation refusés ==========================================
async def test_2_unauthorized_actors_cannot_create_a_school(client: AsyncClient) -> None:
    org = await register_school(client, "p12unauth")
    org_id = org["organization"]["id"]
    admin_headers = auth(org["tokens"]["access_token"])
    teacher_email = unique_email("p12teacher")
    created = await client.post(
        "/api/v1/users",
        json={"email": teacher_email, "full_name": "Ens", "school_id": org["school"]["id"], "role_code": "TEACHER"},
        headers=admin_headers,
    )
    assert created.status_code == 201
    await client.post("/api/v1/auth/reset-password", json={"token": created.json()["dev_reset_token"], "new_password": PASSWORD})
    teacher_headers = auth(
        (await client.post("/api/v1/auth/login", json={"email": teacher_email, "password": PASSWORD})).json()["access_token"]
    )
    for headers in (admin_headers, teacher_headers):
        response = await client.post(
            f"/api/v1/platform/organizations/{org_id}/schools", json=_add_payload("Intrus", org["user"]["email"]), headers=headers
        )
        assert response.status_code == 403
    assert await _school_count(org_id) == 1


async def test_7_cross_organization_creation_refused(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "p12cross")
    partner = await create_partner(client, owner["headers"], "p12cross")
    own = await enroll_school_as_partner(client, partner["headers"], "p12crossown")
    foreign = await register_school(client, "p12crossforeign")
    org_a = await register_school(client, "p12crossa")
    # Admin de A vers l'organisation étrangère : aucune voie de création.
    response = await client.post(
        "/api/v1/schools",
        json={"organization_id": foreign["organization"]["id"], "name": "Intrus", "slug": "intrus"},
        headers=auth(org_a["tokens"]["access_token"]),
    )
    assert response.status_code == 410
    # Partenaire vers une organisation hors de son périmètre : 404 (aucun oracle d'existence).
    response = await client.post(
        f"/api/v1/partner/organizations/{foreign['organization']['id']}/schools",
        json=_add_payload("Intrus", own["admin"]["email"]),
        headers=partner["headers"],
    )
    assert response.status_code == 404
    assert await _school_count(foreign["organization"]["id"]) == 1


# === 3 / 4 / 5 / 6 — création autorisée via le workflow central ==============================================
@pytest.mark.parametrize("actor", ["PLATFORM_OWNER", "SUPER_ADMIN"])
async def test_3_4_5_platform_creation_goes_through_central_workflow(client: AsyncClient, actor: str) -> None:
    org = await register_school(client, f"p12plat{actor[:5].lower()}")
    org_id = org["organization"]["id"]
    if actor == "PLATFORM_OWNER":
        caller = await create_platform_owner(client, "p12platowner")
        headers, caller_id = caller["headers"], caller["user_id"]
    else:
        caller = await create_platform_admin(client, "p12platsuper")
        headers, caller_id = auth(caller["tokens"]["access_token"]), caller["user_id"]
    response = await client.post(
        f"/api/v1/platform/organizations/{org_id}/schools", json=_add_payload("Collège P12", org["user"]["email"]), headers=headers
    )
    assert response.status_code == 201, response.text
    school_id = response.json()["school"]["id"]
    enrollment = await _enrollment(school_id)
    assert enrollment is not None
    assert enrollment.acquisition_source == "PLATFORM_OWNER" and enrollment.partner_id is None
    assert enrollment.commission_eligible is False
    assert str(enrollment.enrolled_by_user_id) == caller_id  # 5 — toujours l'appelant authentifié
    # 6 — admin org-wide réutilisé : aucun compte ni rôle supplémentaire.
    assert await _roles(org["user"]["id"]) == [("SCHOOL_ADMIN", org_id, None)]


async def test_3_4_5_partner_creation_goes_through_central_workflow(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "p12part")
    partner = await create_partner(client, owner["headers"], "p12part")
    own = await enroll_school_as_partner(client, partner["headers"], "p12partorg")
    org_id = own["organization"]["id"]
    new_admin = unique_email("p12partadmin")
    response = await client.post(
        f"/api/v1/partner/organizations/{org_id}/schools",
        json=_add_payload("Lycée P12", new_admin, password=PASSWORD),
        headers=partner["headers"],
    )
    assert response.status_code == 201, response.text
    school_id = response.json()["school"]["id"]
    enrollment = await _enrollment(school_id)
    assert enrollment is not None
    assert enrollment.acquisition_source == "PARTNER" and str(enrollment.partner_id) == partner["partner"]["id"]
    assert enrollment.commission_eligible is True
    assert str(enrollment.enrolled_by_user_id) == partner["user_id"]
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == new_admin))).scalar_one()
    assert await _roles(str(user.id)) == [("SCHOOL_ADMIN", org_id, school_id)]  # scopé à CETTE école


async def test_6_no_illegitimate_school_admin_elevation(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "p12elev")
    org = await register_school(client, "p12elev")
    org_id = org["organization"]["id"]
    teacher_email = unique_email("p12elevteacher")
    created = await client.post(
        "/api/v1/users",
        json={"email": teacher_email, "full_name": "Ens", "school_id": org["school"]["id"], "role_code": "TEACHER"},
        headers=auth(org["tokens"]["access_token"]),
    )
    teacher_id = created.json()["user"]["id"]
    before = await _roles(teacher_id)
    response = await client.post(
        f"/api/v1/platform/organizations/{org_id}/schools", json=_add_payload("Collège Elev", teacher_email), headers=owner["headers"]
    )
    assert response.status_code == 409  # résolveur central : un TEACHER n'est jamais promu admin implicitement
    assert await _roles(teacher_id) == before
    assert await _school_count(org_id) == 1


# === 8 / 9 — doublon slug en 409, aucun état partiel ===========================================================
async def test_8_9_duplicate_slug_is_409_without_partial_state(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "p12dup")
    org = await register_school(client, "p12dup")
    org_id = org["organization"]["id"]
    url = f"/api/v1/platform/organizations/{org_id}/schools"
    first = await client.post(url, json=_add_payload("Collège Dup", org["user"]["email"], slug="college-dup"), headers=owner["headers"])
    assert first.status_code == 201
    new_admin = unique_email("p12dupadmin")
    second = await client.post(
        url, json=_add_payload("Autre Collège", new_admin, slug="college-dup", password=PASSWORD), headers=owner["headers"]
    )
    assert second.status_code == 409
    assert await _school_count(org_id) == 2
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        assert (await db.execute(select(User).where(User.email == new_admin))).scalar_one_or_none() is None
        enrollments = (
            await db.execute(
                select(func.count()).select_from(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.organization_id == uuid.UUID(org_id))
            )
        ).scalar_one()
    assert enrollments == 2  # école principale + Collège Dup : aucune inscription partielle


async def test_9_failure_mid_workflow_rolls_back_everything(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = await create_platform_owner(client, "p12rollback")
    org = await register_school(client, "p12rollback")
    org_id = org["organization"]["id"]
    new_admin = unique_email("p12rbadmin")

    def _boom(_password: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.modules.platform.service.hash_password", _boom)
    with pytest.raises(RuntimeError):
        await client.post(
            f"/api/v1/platform/organizations/{org_id}/schools",
            json=_add_payload("Collège Rollback", new_admin, password=PASSWORD),
            headers=owner["headers"],
        )
    monkeypatch.undo()
    assert await _school_count(org_id) == 1
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(User).where(User.email == new_admin))).scalar_one_or_none() is None
