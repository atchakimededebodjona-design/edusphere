"""PR #20 — réutilisation d'un compte SCHOOL_ADMIN pour plusieurs écoles d'UNE MÊME organisation.

Règles validées :
- email inconnu => création du compte + rôle SCHOOL_ADMIN (comportement historique) ;
- compte existant, actif, détenant SCHOOL_ADMIN ou DIRECTOR dans la MÊME organisation => réutilisé :
  aucun nouveau User, mot de passe jamais lu ni modifié (ignoré s'il est envoyé), ajout d'UN rôle
  SCHOOL_ADMIN scopé à la nouvelle école — sauf s'il détient déjà SCHOOL_ADMIN org-wide dans cette
  organisation (rôle qui couvre déjà la nouvelle école : aucun rôle ajouté) ;
- tout autre compte existant (autre organisation, inactif, rôle non éligible, compte plateforme ou
  partenaire) => 409 avec le MÊME message générique qu'avant, aucune école ni rôle créés.
Cas A à M de la spécification couverts ci-dessous.
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.organizations.models import Organization
from app.modules.platform.service import (
    ADMIN_ACCESS_SCHOOL_ROLE_ADDED,
    _school_admin_role,
    resolve_or_create_school_admin,
)
from app.modules.platform.schemas import SchoolAdminInput
from app.modules.rbac.models import Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User
from tests.conftest import assign_role, create_platform_admin, register_school, unique_email, unique_slug
from tests.pr17_helpers import (
    PASSWORD,
    create_partner,
    create_platform_owner,
    enroll_school_as_partner,
    enrollment_payload,
    login,
)

CONFLICT = "School slug or admin email already in use"


def _payload(name: str, email: str, *, password: str | None = PASSWORD, full_name: str | None = "Wade") -> dict:
    admin: dict = {"email": email}
    if full_name is not None:
        admin["full_name"] = full_name
    if password is not None:
        admin["password"] = password
    return {"school": {"name": name, "slug": unique_slug("ecole")}, "admin": admin}


async def _owner_org(client: AsyncClient, owner: dict, prefix: str) -> dict:
    payload = enrollment_payload(prefix)
    payload["school"]["name"] = "Complexe scolaire EDULINKAGE"
    response = await client.post("/api/v1/platform/organizations", json=payload, headers=owner["headers"])
    assert response.status_code == 201, response.text
    org = response.json()
    org["admin_headers"] = await login(client, org["admin"]["email"])
    return org


async def _add(client: AsyncClient, headers: dict, org_id: str, payload: dict, *, partner: bool = False):
    prefix = "partner" if partner else "platform"
    return await client.post(f"/api/v1/{prefix}/organizations/{org_id}/schools", json=payload, headers=headers)


async def _user_state(email: str) -> tuple[int, User | None, list[tuple[str, str | None, str | None]]]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        count = (await db.execute(select(func.count()).select_from(User).where(User.email == email.strip().lower()))).scalar_one()
        user = (await db.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
        roles: list[tuple[str, str | None, str | None]] = []
        if user is not None:
            rows = (
                await db.execute(
                    select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == user.id)
                )
            ).all()
            roles = sorted(
                (code, str(ur.organization_id) if ur.organization_id else None, str(ur.school_id) if ur.school_id else None)
                for ur, code in rows
            )
    return int(count), user, roles


async def _school_count(org_id: str) -> int:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return int(
            (
                await db.execute(select(func.count()).select_from(School).where(School.organization_id == uuid.UUID(org_id)))
            ).scalar_one()
        )


async def _school_scoped_admin(client: AsyncClient, owner: dict, org_id: str, school_name: str) -> tuple[dict, str]:
    """Ajoute une école avec un NOUVEL admin (rôle scopé à cette école, PR #19)."""
    email = unique_email("wade")
    response = await _add(client, owner["headers"], org_id, _payload(school_name, email))
    assert response.status_code == 201, response.text
    assert response.json()["admin_access"] == "NEW_ACCOUNT"
    return response.json(), email


async def _school_user(client: AsyncClient, admin_headers: dict, school_id: str, role_code: str) -> str:
    email = unique_email(role_code.lower())
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": f"{role_code} existant", "school_id": school_id, "role_code": role_code},
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return email


async def _assert_refused(client: AsyncClient, headers: dict, org_id: str, email: str, *, partner: bool = False) -> None:
    count_before, user_before, roles_before = await _user_state(email)
    schools_before = await _school_count(org_id)
    response = await _add(client, headers, org_id, _payload(f"Refus {uuid.uuid4().hex[:6]}", email), partner=partner)
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == CONFLICT  # message générique, motif indistinguable
    count_after, user_after, roles_after = await _user_state(email)
    assert (count_after, roles_after) == (count_before, roles_before)
    if user_before is not None and user_after is not None:
        assert user_after.hashed_password == user_before.hashed_password
        assert user_after.is_active == user_before.is_active
    assert await _school_count(org_id) == schools_before  # aucune école partiellement créée


# === A — email inconnu ===========================================================================
async def test_a_unknown_email_creates_account_and_scoped_role(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20a")
    org = await _owner_org(client, owner, "r20a")
    org_id = org["organization"]["id"]
    added, email = await _school_scoped_admin(client, owner, org_id, "Collège EduLinkage")
    assert added["admin_account_reused"] is False
    count, user, roles = await _user_state(email)
    assert count == 1 and user is not None
    assert roles == [("SCHOOL_ADMIN", org_id, added["school"]["id"])]


async def test_a_new_account_requires_name_and_password(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20a2")
    org = await _owner_org(client, owner, "r20a2")
    org_id = org["organization"]["id"]
    for payload in (
        _payload("Sans mot de passe", unique_email("nopwd"), password=None),
        _payload("Mot de passe court", unique_email("shortpwd"), password="court"),
        _payload("Sans nom", unique_email("noname"), full_name=None),
    ):
        response = await _add(client, owner["headers"], org_id, payload)
        assert response.status_code == 422, response.text
        assert (await _user_state(payload["admin"]["email"]))[0] == 0
    assert await _school_count(org_id) == 1


# === B — compte existant, même organisation =========================================================
async def test_b_same_org_school_scoped_admin_is_reused_with_one_account(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20b")
    org = await _owner_org(client, owner, "r20b")
    org_id = org["organization"]["id"]
    college, email = await _school_scoped_admin(client, owner, org_id, "Collège EduLinkage")
    _, user_before, _ = await _user_state(email)
    assert user_before is not None

    response = await _add(client, owner["headers"], org_id, _payload("Lycée EduLinkage", email, password="UnAutreMotDePasse9"))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["admin_account_reused"] is True and body["admin_access"] == "SCHOOL_ROLE_ADDED"
    assert body["admin"]["id"] == college["admin"]["id"]

    count, user_after, roles = await _user_state(email)
    assert count == 1 and user_after is not None
    assert user_after.hashed_password == user_before.hashed_password  # mot de passe jamais modifié
    assert user_after.full_name == user_before.full_name
    assert roles == sorted(
        [("SCHOOL_ADMIN", org_id, college["school"]["id"]), ("SCHOOL_ADMIN", org_id, body["school"]["id"])]
    )
    # Le mot de passe envoyé a été ignoré : seul l'ancien permet de se connecter.
    await login(client, email)
    bad = await client.post("/api/v1/auth/login", json={"email": email, "password": "UnAutreMotDePasse9"})
    assert bad.status_code == 401


async def test_b_first_org_wide_admin_is_reused_without_new_role(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20bow")
    org = await _owner_org(client, owner, "r20bow")
    org_id = org["organization"]["id"]
    email = org["admin"]["email"]
    response = await _add(client, owner["headers"], org_id, _payload("Collège EduLinkage", email, password=None))
    assert response.status_code == 201, response.text
    assert response.json()["admin_account_reused"] is True
    assert response.json()["admin_access"] == "ORGANIZATION_WIDE_ROLE"
    count, _, roles = await _user_state(email)
    assert count == 1 and roles == [("SCHOOL_ADMIN", org_id, None)]
    # Son rôle org-wide couvre effectivement la nouvelle école.
    headers = await login(client, email)
    new_school = response.json()["school"]["id"]
    assert (await client.get(f"/api/v1/students?school_id={new_school}", headers=headers)).status_code == 200


# === D — compte existant dans plusieurs écoles de la même organisation ===============================
async def test_d_account_with_two_schools_gets_third_and_scope_stays_per_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20d")
    org = await _owner_org(client, owner, "r20d")
    org_id = org["organization"]["id"]
    college, email = await _school_scoped_admin(client, owner, org_id, "Collège EduLinkage")
    lycee = (await _add(client, owner["headers"], org_id, _payload("Lycée EduLinkage", email))).json()
    third = (await _add(client, owner["headers"], org_id, _payload("Annexe EduLinkage", email))).json()
    assert third["admin_access"] == "SCHOOL_ROLE_ADDED"
    other, _ = await _school_scoped_admin(client, owner, org_id, "Ecole Autre Admin")
    other_org = await _owner_org(client, owner, "r20dother")

    count, _, roles = await _user_state(email)
    assert count == 1
    assert {school for _, _, school in roles} == {college["school"]["id"], lycee["school"]["id"], third["school"]["id"]}
    assert all(org == org_id for _, org, _ in roles) and all(school is not None for _, _, school in roles)

    headers = await login(client, email)
    for school_id in (college["school"]["id"], lycee["school"]["id"], third["school"]["id"]):
        assert (await client.get(f"/api/v1/students?school_id={school_id}", headers=headers)).status_code == 200
    # Jamais d'accès implicite aux autres écoles de l'organisation ni à une autre organisation.
    for school_id in (org["school"]["id"], other["school"]["id"], other_org["school"]["id"]):
        response = await client.get(f"/api/v1/students?school_id={school_id}", headers=headers)
        assert response.status_code in (403, 404), school_id
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert sorted(r["school_id"] for r in me.json()["roles"]) == sorted(
        [college["school"]["id"], lycee["school"]["id"], third["school"]["id"]]
    )
    # Il apparaît dans la liste des utilisateurs de la nouvelle école.
    listed = await client.get(f"/api/v1/users?school_id={third['school']['id']}", headers=headers)
    assert college["admin"]["id"] in {e["user"]["id"] for e in listed.json()}


# === E — même compte + même école + même rôle : jamais de doublon ======================================
async def test_e_resolver_never_duplicates_an_identical_role(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20e")
    org = await _owner_org(client, owner, "r20e")
    org_id = org["organization"]["id"]
    college, email = await _school_scoped_admin(client, owner, org_id, "Collège EduLinkage")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        organization = await db.get(Organization, uuid.UUID(org_id))
        school = await db.get(School, uuid.UUID(college["school"]["id"]))
        assert organization is not None and school is not None
        resolution = await resolve_or_create_school_admin(
            db,
            organization=organization,
            school=school,
            admin_input=SchoolAdminInput(email=email),
            school_admin_role=await _school_admin_role(db),
            admin_school_scoped=True,
            conflict_detail=CONFLICT,
        )
        assert resolution.reused is True and resolution.access == ADMIN_ACCESS_SCHOOL_ROLE_ADDED
        count = (
            await db.execute(select(func.count()).select_from(UserRole).where(UserRole.user_id == resolution.user.id))
        ).scalar_one()
        assert count == 1
        await db.rollback()


# === F / G — normalisation de l'email ================================================================
@pytest.mark.parametrize("variant", ["spaces", "uppercase"])
async def test_fg_email_normalization_reuses_same_account(client: AsyncClient, variant: str) -> None:
    owner = await create_platform_owner(client, f"r20fg{variant[:3]}")
    org = await _owner_org(client, owner, f"r20fg{variant[:3]}")
    org_id = org["organization"]["id"]
    _, email = await _school_scoped_admin(client, owner, org_id, "Collège EduLinkage")
    submitted = f"  {email}  " if variant == "spaces" else email.upper()
    response = await _add(client, owner["headers"], org_id, _payload("Lycée EduLinkage", submitted))
    assert response.status_code == 201, response.text
    assert response.json()["admin_account_reused"] is True
    count, _, roles = await _user_state(email)
    assert count == 1 and len(roles) == 2


# === C / I / J / K / L / M — refus génériques ============================================================
async def test_c_admin_of_another_organization_is_refused(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20c")
    org_a = await _owner_org(client, owner, "r20ca")
    org_b = await _owner_org(client, owner, "r20cb")
    _, scoped_b = await _school_scoped_admin(client, owner, org_b["organization"]["id"], "Collège B")
    for email in (org_b["admin"]["email"], scoped_b):
        await _assert_refused(client, owner["headers"], org_a["organization"]["id"], email)


async def test_c_new_organization_flow_still_refuses_any_existing_email(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20cnew")
    org = await _owner_org(client, owner, "r20cnew")
    payload = enrollment_payload("r20cnewbis", admin_email=org["admin"]["email"])
    response = await client.post("/api/v1/platform/organizations", json=payload, headers=owner["headers"])
    assert response.status_code == 409
    assert response.json()["detail"] == "Organization slug or admin email already in use"
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        exists = (
            await db.execute(select(Organization).where(Organization.slug == payload["organization"]["slug"]))
        ).scalar_one_or_none()
    assert exists is None
    assert (await _user_state(org["admin"]["email"]))[2] == [("SCHOOL_ADMIN", org["organization"]["id"], None)]


async def test_i_inactive_account_is_refused(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20i")
    org = await _owner_org(client, owner, "r20i")
    org_id = org["organization"]["id"]
    _, email = await _school_scoped_admin(client, owner, org_id, "Collège EduLinkage")
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
        user.is_active = False
        await db.commit()
    await _assert_refused(client, owner["headers"], org_id, email)


@pytest.mark.parametrize("role_code", ["TEACHER", "PARENT", "ACCOUNTANT", "STAFF", "STUDENT"])
async def test_j_non_admin_role_in_same_org_is_refused(client: AsyncClient, role_code: str) -> None:
    owner = await create_platform_owner(client, f"r20j{role_code[:3].lower()}")
    org = await _owner_org(client, owner, f"r20j{role_code[:3].lower()}")
    email = await _school_user(client, org["admin_headers"], org["school"]["id"], role_code)
    await _assert_refused(client, owner["headers"], org["organization"]["id"], email)


async def test_j_director_in_same_org_is_reused_as_school_admin(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20jdir")
    org = await _owner_org(client, owner, "r20jdir")
    org_id = org["organization"]["id"]
    email = await _school_user(client, org["admin_headers"], org["school"]["id"], "DIRECTOR")
    response = await _add(client, owner["headers"], org_id, _payload("Collège EduLinkage", email))
    assert response.status_code == 201, response.text
    assert response.json()["admin_access"] == "SCHOOL_ROLE_ADDED"
    _, _, roles = await _user_state(email)
    assert roles == sorted(
        [("DIRECTOR", org_id, org["school"]["id"]), ("SCHOOL_ADMIN", org_id, response.json()["school"]["id"])]
    )


async def test_k_platform_accounts_are_refused(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20k")
    org = await _owner_org(client, owner, "r20k")
    org_id = org["organization"]["id"]
    super_admin = await create_platform_admin(client, "r20ksuper")
    # SUPER_ADMIN hérité ayant EN PLUS un rôle SCHOOL_ADMIN dans cette organisation : toujours refusé.
    legacy = await create_platform_admin(client, "r20klegacy")
    await assign_role(legacy["user_id"], "SCHOOL_ADMIN", org_id, None)
    support_email = await _school_user(client, org["admin_headers"], org["school"]["id"], "DIRECTOR")
    _, support_user, _ = await _user_state(support_email)
    assert support_user is not None
    await assign_role(str(support_user.id), "PLATFORM_SUPPORT", None, None)
    for email in (super_admin["email"], legacy["email"], support_email):
        await _assert_refused(client, owner["headers"], org_id, email)


async def test_l_partner_admin_account_is_refused(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20l")
    partner = await create_partner(client, owner["headers"], "r20l")
    org = await _owner_org(client, owner, "r20l")
    await _assert_refused(client, owner["headers"], org["organization"]["id"], partner["email"])


async def test_m_platform_owner_account_is_refused(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20m")
    other_owner = await create_platform_owner(client, "r20mother")
    org = await _owner_org(client, owner, "r20m")
    for email in (owner["email"], other_owner["email"]):
        await _assert_refused(client, owner["headers"], org["organization"]["id"], email)


# === L (parcours partenaire) =========================================================================
async def test_partner_flow_reuse_and_refusal(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20pf")
    partner = await create_partner(client, owner["headers"], "r20pf")
    first = await enroll_school_as_partner(client, partner["headers"], "r20pforg")
    org_id = first["organization"]["id"]

    # Premier admin (org-wide) réutilisé : aucun rôle ajouté.
    response = await _add(client, partner["headers"], org_id, _payload("Collège P", first["admin"]["email"]), partner=True)
    assert response.status_code == 201, response.text
    assert response.json()["admin_access"] == "ORGANIZATION_WIDE_ROLE"
    assert response.json()["acquisition_source"] == "PARTNER" and response.json()["commission_eligible"] is True

    # Admin scopé d'une école du partenaire réutilisé pour une autre école : rôle scopé ajouté.
    email = unique_email("r20pfscoped")
    lycee = await _add(client, partner["headers"], org_id, _payload("Lycée P", email), partner=True)
    assert lycee.json()["admin_access"] == "NEW_ACCOUNT"
    annexe = await _add(client, partner["headers"], org_id, _payload("Annexe P", email), partner=True)
    assert annexe.status_code == 201 and annexe.json()["admin_access"] == "SCHOOL_ROLE_ADDED"
    assert (await _user_state(email))[0] == 1

    # Admin d'une organisation étrangère : refusé (409 générique), rien créé.
    foreign = await register_school(client, "r20pfforeign")
    await _assert_refused(client, partner["headers"], org_id, foreign["user"]["email"], partner=True)
    # Et l'organisation étrangère reste inaccessible (404, PR #19).
    response = await _add(
        client, partner["headers"], foreign["organization"]["id"], _payload("Intrus", first["admin"]["email"]), partner=True
    )
    assert response.status_code == 404


# === H — concurrence ===================================================================================
async def test_h_concurrent_same_new_email_same_org_creates_one_account(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20h")
    partner = await create_partner(client, owner["headers"], "r20h")
    org = await enroll_school_as_partner(client, partner["headers"], "r20horg")
    org_id = org["organization"]["id"]
    email = unique_email("r20hconc")
    results = await asyncio.gather(
        _add(client, owner["headers"], org_id, _payload("Collège H", email)),
        _add(client, partner["headers"], org_id, _payload("Lycée H", email), partner=True),
    )
    assert sorted(r.status_code for r in results) == [201, 201], [r.text for r in results]
    assert sorted(r.json()["admin_access"] for r in results) == ["NEW_ACCOUNT", "SCHOOL_ROLE_ADDED"]
    count, _, roles = await _user_state(email)
    assert count == 1 and len(roles) == 2


async def test_h_concurrent_same_new_email_two_orgs_only_one_succeeds(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "r20h2")
    org = await _owner_org(client, owner, "r20h2")
    email = unique_email("r20h2conc")
    new_org_payload = enrollment_payload("r20h2new", admin_email=email)
    results = await asyncio.gather(
        client.post("/api/v1/platform/organizations", json=new_org_payload, headers=owner["headers"]),
        _add(client, owner["headers"], org["organization"]["id"], _payload("Collège H2", email)),
    )
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    count, _, roles = await _user_state(email)
    assert count == 1 and len(roles) == 1
