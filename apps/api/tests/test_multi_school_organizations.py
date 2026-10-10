"""PR #19 — plusieurs établissements par organisation.

Parcours couverts :
- PLATFORM_OWNER : nouvelle organisation + première école (POST /platform/organizations,
  inchangé), puis ajout d'établissements à une organisation EXISTANTE
  (POST /platform/organizations/{id}/schools) ;
- PARTNER_ADMIN : même chose dans SON périmètre uniquement
  (GET /partner/organizations, POST /partner/organizations/{id}/schools).

Invariants vérifiés : jamais de nouvelle organisation sur le parcours « existante », un
SCHOOL_ADMIN par école ajoutée (scopé à CETTE école), doublons refusés (nom/slug/email, y compris
en concurrence), source d'acquisition et éligibilité commission décidées côté serveur, aucun
identifiant client (organization_id étranger, partner_id, school_id) ne permet d'élargir le
périmètre, et toujours aucune donnée individuelle d'élève ni `students.read`.
"""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.core.permissions import get_all_permission_codes
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.organizations.models import Organization
from app.modules.partners.models import PartnerSchoolEnrollment
from app.modules.rbac.models import Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User
from tests.conftest import register_school, unique_email, unique_slug
from tests.pr17_helpers import (
    PASSWORD,
    auth,
    create_partner,
    create_platform_owner,
    enroll_school_as_partner,
    enrollment_payload,
    login,
)


def _school_payload(name: str, slug: str | None = None, admin_email: str | None = None) -> dict:
    return {
        "school": {"name": name, "slug": slug or unique_slug("etab")},
        "admin": {"full_name": f"Admin {name}", "email": admin_email or unique_email("admin.etab"), "password": PASSWORD},
    }


async def _owner_org_with_primary(client: AsyncClient, owner: dict, prefix: str) -> dict:
    payload = enrollment_payload(prefix)
    payload["school"]["name"] = "Primaire La Référence"
    response = await client.post("/api/v1/platform/organizations", json=payload, headers=owner["headers"])
    assert response.status_code == 201, response.text
    return response.json()


async def _org_rows(organization_id: str) -> tuple[int, list[School]]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        org_count = (
            await db.execute(select(func.count()).select_from(Organization).where(Organization.id == uuid.UUID(organization_id)))
        ).scalar_one()
        schools = list(
            (
                await db.execute(
                    select(School).where(School.organization_id == uuid.UUID(organization_id)).order_by(School.created_at)
                )
            ).scalars()
        )
    return int(org_count), schools


async def _admin_roles(user_id: str) -> list[tuple[str, str | None, str | None]]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = (
            await db.execute(
                select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == uuid.UUID(user_id))
            )
        ).all()
    return [
        (code, str(ur.organization_id) if ur.organization_id else None, str(ur.school_id) if ur.school_id else None)
        for ur, code in rows
    ]


async def _enrollment(school_id: str) -> PartnerSchoolEnrollment:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return (
            await db.execute(select(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.school_id == uuid.UUID(school_id)))
        ).scalar_one()


# === 1-7, 16-17 : PLATFORM_OWNER =============================================================
async def test_owner_creates_org_then_adds_second_and_third_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "msowner")
    created = await _owner_org_with_primary(client, owner, "msowner")  # 1
    org_id = created["organization"]["id"]

    added = []
    for name in ("Collège La Référence", "Lycée La Référence"):  # 2, 3
        response = await client.post(
            f"/api/v1/platform/organizations/{org_id}/schools", json=_school_payload(name), headers=owner["headers"]
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["organization"]["id"] == org_id
        assert body["acquisition_source"] == "PLATFORM_OWNER" and body["commission_eligible"] is False
        added.append(body)

    org_count, schools = await _org_rows(org_id)
    assert org_count == 1  # 4 — une seule organisation
    assert [s.name for s in schools] == ["Primaire La Référence", "Collège La Référence", "Lycée La Référence"]
    assert {str(s.organization_id) for s in schools} == {org_id}  # 5

    # 6 — chaque école a son SCHOOL_ADMIN ; ceux des écoles ajoutées sont scopés à LEUR école.
    assert await _admin_roles(created["admin"]["id"]) == [("SCHOOL_ADMIN", org_id, None)]
    for body in added:
        assert await _admin_roles(body["admin"]["id"]) == [("SCHOOL_ADMIN", org_id, body["school"]["id"])]

    # 16, 17 — source d'acquisition / éligibilité commission.
    for body in [created, *added]:
        enrollment = await _enrollment(body["school"]["id"])
        assert enrollment.partner_id is None
        assert enrollment.acquisition_source == "PLATFORM_OWNER"
        assert enrollment.commission_eligible is False
        assert str(enrollment.enrolled_by_user_id) == owner["user_id"]

    # Vue plateforme de l'organisation : 3 établissements, métadonnées + agrégats uniquement.
    listing = await client.get(f"/api/v1/platform/organizations/{org_id}/schools", headers=owner["headers"])
    assert listing.status_code == 200
    assert listing.json()["organization"]["id"] == org_id
    assert [s["name"] for s in listing.json()["schools"]] == [s.name for s in schools]


async def test_added_school_admin_administers_only_its_own_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "msscope")
    created = await _owner_org_with_primary(client, owner, "msscope")
    org_id = created["organization"]["id"]
    payload = _school_payload("Collège Scope")
    response = await client.post(f"/api/v1/platform/organizations/{org_id}/schools", json=payload, headers=owner["headers"])
    college_admin = await login(client, payload["admin"]["email"])
    college_id = response.json()["school"]["id"]
    assert (await client.get(f"/api/v1/students?school_id={college_id}", headers=college_admin)).status_code == 200
    primary = await client.get(f"/api/v1/students?school_id={created['school']['id']}", headers=college_admin)
    assert primary.status_code == 403


async def test_owner_cannot_create_the_same_school_twice(client: AsyncClient) -> None:  # 7
    owner = await create_platform_owner(client, "msdup")
    created = await _owner_org_with_primary(client, owner, "msdup")
    org_id = created["organization"]["id"]
    url = f"/api/v1/platform/organizations/{org_id}/schools"
    first = await client.post(url, json=_school_payload("Collège Doublon", slug="college"), headers=owner["headers"])
    assert first.status_code == 201
    same_name = await client.post(url, json=_school_payload("  collège   DOUBLON "), headers=owner["headers"])
    assert same_name.status_code == 409
    assert same_name.json()["detail"] == "A school with this name already exists in this organization"
    same_slug = await client.post(url, json=_school_payload("Autre Collège", slug="college"), headers=owner["headers"])
    assert same_slug.status_code == 409
    primary_name = await client.post(url, json=_school_payload("Primaire La Référence"), headers=owner["headers"])
    assert primary_name.status_code == 409
    existing_admin = await client.post(
        url, json=_school_payload("Lycée Mail", admin_email=created["admin"]["email"]), headers=owner["headers"]
    )
    assert existing_admin.status_code == 409
    org_count, schools = await _org_rows(org_id)
    assert org_count == 1 and len(schools) == 2  # aucune ligne partielle


async def test_owner_add_school_to_unknown_org_is_404_and_never_creates_org(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "ms404")
    unknown = str(uuid.uuid4())
    response = await client.post(
        f"/api/v1/platform/organizations/{unknown}/schools", json=_school_payload("Fantôme"), headers=owner["headers"]
    )
    assert response.status_code == 404
    assert (await _org_rows(unknown))[0] == 0
    assert (await client.get(f"/api/v1/platform/organizations/{unknown}/schools", headers=owner["headers"])).status_code == 404


@pytest.mark.parametrize(
    "forged",
    [
        {"organization": {"name": "Nouvelle", "slug": "nouvelle", "country_code": "TG"}},
        {"organization_id": "00000000-0000-0000-0000-000000000000"},
        {"partner_id": "00000000-0000-0000-0000-000000000000"},
        {"acquisition_source": "PARTNER"},
        {"commission_eligible": True},
    ],
)
async def test_add_school_payload_rejects_any_extra_field(client: AsyncClient, forged: dict) -> None:
    owner = await create_platform_owner(client, "msforge")
    created = await _owner_org_with_primary(client, owner, "msforge")
    payload = {**_school_payload("Collège Forgé"), **forged}
    response = await client.post(
        f"/api/v1/platform/organizations/{created['organization']['id']}/schools", json=payload, headers=owner["headers"]
    )
    assert response.status_code == 422
    assert len((await _org_rows(created["organization"]["id"]))[1]) == 1


async def test_platform_organization_search_finds_existing_org(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "mssearch")
    marker = uuid.uuid4().hex[:10]
    payload = enrollment_payload("mssearch")
    payload["organization"]["name"] = f"Groupe Scolaire {marker}"
    created = await client.post("/api/v1/platform/organizations", json=payload, headers=owner["headers"])
    found = await client.get(f"/api/v1/platform/organizations?q={marker.upper()}", headers=owner["headers"])
    assert found.status_code == 200
    assert [o["id"] for o in found.json()["items"]] == [created.json()["organization"]["id"]]
    assert found.json()["total"] == 1
    wildcard = await client.get("/api/v1/platform/organizations?q=%25&page_size=1", headers=owner["headers"])
    assert wildcard.status_code == 200 and wildcard.json()["total"] == 0  # « % » littéral, jamais un joker


async def test_school_roles_and_partner_cannot_use_owner_add_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "msrbac")
    partner = await create_partner(client, owner["headers"], "msrbac")
    school = await register_school(client, "msrbacschool")
    org_id = school["organization"]["id"]
    for headers in (auth(school["tokens"]["access_token"]), partner["headers"]):
        response = await client.post(
            f"/api/v1/platform/organizations/{org_id}/schools", json=_school_payload("Intrus"), headers=headers
        )
        assert response.status_code == 403
        assert (await client.get(f"/api/v1/platform/organizations/{org_id}/schools", headers=headers)).status_code == 403
    assert len((await _org_rows(org_id))[1]) == 1


# === 8-14, 16-17 : PARTNER_ADMIN ===============================================================
async def test_partner_creates_org_then_adds_second_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "mspartner")
    partner = await create_partner(client, owner["headers"], "mspartner")
    first = await enroll_school_as_partner(client, partner["headers"], "mspartnerorg")  # 8
    org_id = first["organization"]["id"]

    orgs = await client.get("/api/v1/partner/organizations", headers=partner["headers"])
    assert orgs.status_code == 200
    assert [(o["organization_id"], [s["school_id"] for s in o["schools"]]) for o in orgs.json()] == [
        (org_id, [first["school"]["id"]])
    ]

    response = await client.post(  # 9
        f"/api/v1/partner/organizations/{org_id}/schools", json=_school_payload("Collège Partenaire"), headers=partner["headers"]
    )
    assert response.status_code == 201, response.text
    second = response.json()
    assert second["organization"]["id"] == org_id
    assert second["acquisition_source"] == "PARTNER" and second["commission_eligible"] is True

    org_count, schools = await _org_rows(org_id)
    assert org_count == 1 and len(schools) == 2  # 10
    for school_id in (first["school"]["id"], second["school"]["id"]):  # 16, 17
        enrollment = await _enrollment(school_id)
        assert str(enrollment.partner_id) == partner["partner"]["id"]
        assert enrollment.acquisition_source == "PARTNER" and enrollment.commission_eligible is True
    assert await _admin_roles(second["admin"]["id"]) == [("SCHOOL_ADMIN", org_id, second["school"]["id"])]

    listed = await client.get("/api/v1/partner/schools", headers=partner["headers"])
    assert {s["school_id"] for s in listed.json()} == {first["school"]["id"], second["school"]["id"]}
    dashboard = await client.get("/api/v1/partner/dashboard", headers=partner["headers"])
    assert dashboard.json() == {"school_count": 2, "organization_count": 1}


async def test_partner_sees_only_its_own_scope(client: AsyncClient) -> None:  # 11
    owner = await create_platform_owner(client, "msscopep")
    partner_a = await create_partner(client, owner["headers"], "msscopea")
    partner_b = await create_partner(client, owner["headers"], "msscopeb")
    a = await enroll_school_as_partner(client, partner_a["headers"], "msscopeorga")
    b = await enroll_school_as_partner(client, partner_b["headers"], "msscopeorgb")
    platform_school = await register_school(client, "msscopeplatform")
    # Le propriétaire ajoute une école dans l'organisation de A : visible côté plateforme, jamais
    # comme une école « de A » (inscrite par un autre acteur).
    owner_added = await client.post(
        f"/api/v1/platform/organizations/{a['organization']['id']}/schools",
        json=_school_payload("Lycée Direct"),
        headers=owner["headers"],
    )
    assert owner_added.status_code == 201

    orgs_a = (await client.get("/api/v1/partner/organizations", headers=partner_a["headers"])).json()
    assert [o["organization_id"] for o in orgs_a] == [a["organization"]["id"]]
    assert [s["school_id"] for s in orgs_a[0]["schools"]] == [a["school"]["id"]]
    schools_a = {s["school_id"] for s in (await client.get("/api/v1/partner/schools", headers=partner_a["headers"])).json()}
    assert schools_a == {a["school"]["id"]}
    for foreign in (b["school"]["id"], platform_school["school"]["id"], owner_added.json()["school"]["id"]):
        assert foreign not in schools_a
    orgs_b = (await client.get("/api/v1/partner/organizations", headers=partner_b["headers"])).json()
    assert [o["organization_id"] for o in orgs_b] == [b["organization"]["id"]]


async def test_partner_cannot_add_school_to_foreign_organization(client: AsyncClient) -> None:  # 12, 14
    owner = await create_platform_owner(client, "msforeign")
    partner_a = await create_partner(client, owner["headers"], "msforeigna")
    partner_b = await create_partner(client, owner["headers"], "msforeignb")
    await enroll_school_as_partner(client, partner_a["headers"], "msforeignorga")
    b = await enroll_school_as_partner(client, partner_b["headers"], "msforeignorgb")
    platform_school = await register_school(client, "msforeignplatform")

    for org_id in (b["organization"]["id"], platform_school["organization"]["id"], str(uuid.uuid4())):
        response = await client.post(
            f"/api/v1/partner/organizations/{org_id}/schools", json=_school_payload("Intrus"), headers=partner_a["headers"]
        )
        # 404 identique pour une organisation étrangère et inexistante : aucun oracle d'existence.
        assert response.status_code == 404, (org_id, response.text)
        assert response.json()["detail"] == "Organization not found"
    for org_id in (b["organization"]["id"], platform_school["organization"]["id"]):
        assert len((await _org_rows(org_id))[1]) == 1


@pytest.mark.parametrize("field", ["partner_id", "organization_id", "school_id", "organization"])
async def test_partner_add_school_rejects_forged_identifiers(client: AsyncClient, field: str) -> None:  # 13
    owner = await create_platform_owner(client, f"msforged{field[:4]}")
    partner_a = await create_partner(client, owner["headers"], "msforgeda")
    partner_b = await create_partner(client, owner["headers"], "msforgedb")
    a = await enroll_school_as_partner(client, partner_a["headers"], "msforgedorga")
    b = await enroll_school_as_partner(client, partner_b["headers"], "msforgedorgb")
    values = {
        "partner_id": partner_b["partner"]["id"],
        "organization_id": b["organization"]["id"],
        "school_id": b["school"]["id"],
        "organization": {"name": "Pirate", "slug": "pirate", "country_code": "TG"},
    }
    payload = {**_school_payload("Collège Forgé"), field: values[field]}
    response = await client.post(
        f"/api/v1/partner/organizations/{a['organization']['id']}/schools", json=payload, headers=partner_a["headers"]
    )
    assert response.status_code == 422
    assert len((await _org_rows(a["organization"]["id"]))[1]) == 1
    assert len((await _org_rows(b["organization"]["id"]))[1]) == 1
    # Paramètres de requête forgés : ignorés.
    listed = await client.get(
        f"/api/v1/partner/organizations?partner_id={partner_b['partner']['id']}&organization_id={b['organization']['id']}",
        headers=partner_a["headers"],
    )
    assert [o["organization_id"] for o in listed.json()] == [a["organization"]["id"]]


async def test_partner_cannot_reattach_existing_school(client: AsyncClient) -> None:  # 14 (rattachement)
    owner = await create_platform_owner(client, "msreattach")
    partner = await create_partner(client, owner["headers"], "msreattach")
    a = await enroll_school_as_partner(client, partner["headers"], "msreattachorg")
    org_id = a["organization"]["id"]
    # Le nom d'une école déjà présente dans l'organisation est refusé (même casse/espaces différents).
    duplicate = await client.post(
        f"/api/v1/partner/organizations/{org_id}/schools",
        json=_school_payload(a["school"]["name"].upper()),
        headers=partner["headers"],
    )
    assert duplicate.status_code == 409
    # Le slug d'une école existante aussi (contrainte uq_school_org_slug).
    same_slug = await client.post(
        f"/api/v1/partner/organizations/{org_id}/schools",
        json=_school_payload("Nom Différent", slug=a["school"]["slug"]),
        headers=partner["headers"],
    )
    assert same_slug.status_code == 409
    assert len((await _org_rows(org_id))[1]) == 1


async def test_partner_endpoints_rbac(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "msprbac")
    school = await register_school(client, "msprbacschool")
    for headers in (owner["headers"], auth(school["tokens"]["access_token"])):
        assert (await client.get("/api/v1/partner/organizations", headers=headers)).status_code == 403
        response = await client.post(
            f"/api/v1/partner/organizations/{school['organization']['id']}/schools",
            json=_school_payload("Intrus"),
            headers=headers,
        )
        assert response.status_code == 403
    assert (await client.get("/api/v1/partner/organizations")).status_code == 401


# === 15 : concurrence ============================================================================
@pytest.mark.parametrize("variant", ["same_name", "same_slug"])
async def test_concurrent_double_add_only_one_succeeds(client: AsyncClient, variant: str) -> None:
    owner = await create_platform_owner(client, f"msconc{variant[5:]}")
    partner = await create_partner(client, owner["headers"], "msconc")
    a = await enroll_school_as_partner(client, partner["headers"], "msconcorg")
    org_id = a["organization"]["id"]
    owner_headers = owner["headers"]
    partner_headers = partner["headers"]

    if variant == "same_name":
        payloads = [_school_payload("Collège Concurrent"), _school_payload("Collège Concurrent")]
    else:
        payloads = [_school_payload("Collège X", slug="college-conc"), _school_payload("Collège Y", slug="college-conc")]

    results = await asyncio.gather(
        client.post(f"/api/v1/platform/organizations/{org_id}/schools", json=payloads[0], headers=owner_headers),
        client.post(f"/api/v1/partner/organizations/{org_id}/schools", json=payloads[1], headers=partner_headers),
    )
    assert sorted(r.status_code for r in results) == [201, 409], [r.text for r in results]
    assert len((await _org_rows(org_id))[1]) == 2
    loser = next(r for r in results if r.status_code == 409)
    loser_email = payloads[[r.status_code for r in results].index(409)]["admin"]["email"]
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(User).where(User.email == loser_email))).scalar_one_or_none() is None
    assert loser.json()["detail"] in {
        "A school with this name already exists in this organization",
        "School slug or admin email already in use",
    }


# === 18-21 : élèves — aucune régression ==========================================================
async def test_students_read_still_absent_for_owner_and_partner(client: AsyncClient) -> None:  # 18, 19
    owner = await create_platform_owner(client, "msperm")
    partner = await create_partner(client, owner["headers"], "msperm")
    for user_id in (owner["user_id"], partner["user_id"]):
        async with AsyncSessionLocal() as db:
            await apply_tenant_context(db, uuid.UUID(user_id))
            user = await db.get(User, uuid.UUID(user_id))
            assert user is not None
            codes = await get_all_permission_codes(db, user)
            await db.rollback()
        assert "students.read" not in codes and "students.manage" not in codes
        assert all(code.startswith(("platform.", "partner.")) for code in codes)
    async with AsyncSessionLocal() as db:
        holders = {
            row[0]
            for row in (
                await db.execute(
                    text(
                        "SELECT r.code FROM role_permissions rp JOIN roles r ON r.id = rp.role_id "
                        "JOIN permissions p ON p.id = rp.permission_id WHERE p.code LIKE 'students.%'"
                    )
                )
            ).all()
        }
    assert not holders & {"PLATFORM_OWNER", "PARTNER_ADMIN"}


async def test_no_individual_student_data_and_counts_stay_correct(client: AsyncClient) -> None:  # 20, 21
    owner = await create_platform_owner(client, "mscounts")
    partner = await create_partner(client, owner["headers"], "mscounts")
    first = await enroll_school_as_partner(client, partner["headers"], "mscountsorg")
    org_id = first["organization"]["id"]
    payload = _school_payload("Collège Comptes")
    added = await client.post(f"/api/v1/partner/organizations/{org_id}/schools", json=payload, headers=partner["headers"])
    college_id = added.json()["school"]["id"]
    college_admin = await login(client, payload["admin"]["email"])

    marker = f"Ident{uuid.uuid4().hex[:8]}"
    student_ids = []
    for i, (headers, school_id) in enumerate(
        [(first["admin_headers"], first["school"]["id"]), (college_admin, college_id), (college_admin, college_id)]
    ):
        response = await client.post(
            "/api/v1/students",
            json={
                "school_id": school_id,
                "matricule": f"{marker}M{i}",
                "first_name": f"{marker}P{i}",
                "last_name": f"{marker}N{i}",
                "date_of_birth": "2014-01-01",
                "sex": "F",
            },
            headers=headers,
        )
        assert response.status_code == 201, response.text
        student_ids.append(response.json()["id"])
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(text("UPDATE students SET status = 'WITHDRAWN' WHERE id = :id"), {"id": uuid.UUID(student_ids[2])})
        await db.commit()

    expected = {first["school"]["id"]: (1, 1), college_id: (2, 1)}
    partner_orgs = await client.get("/api/v1/partner/organizations", headers=partner["headers"])
    owner_org = await client.get(f"/api/v1/platform/organizations/{org_id}/schools", headers=owner["headers"])
    partner_schools = await client.get("/api/v1/partner/schools", headers=partner["headers"])
    got_partner = {s["school_id"]: (s["student_count"], s["active_student_count"]) for s in partner_orgs.json()[0]["schools"]}
    got_owner = {s["id"]: (s["student_count"], s["active_student_count"]) for s in owner_org.json()["schools"]}
    assert got_partner == expected and got_owner == expected
    for response in (partner_orgs, owner_org, partner_schools):
        assert marker not in response.text
        for student_id in student_ids:
            assert student_id not in response.text

    for headers in (owner["headers"], partner["headers"]):
        for path in (
            f"/api/v1/students?school_id={college_id}",
            f"/api/v1/students/{student_ids[1]}",
            f"/api/v1/students/{student_ids[1]}/photo",
            f"/api/v1/students/{student_ids[1]}/guardians",
        ):
            response = await client.get(path, headers=headers)
            assert response.status_code in (403, 404), (path, response.status_code)
            assert marker not in response.text
