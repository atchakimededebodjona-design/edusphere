"""PR #17 — partenaires commerciaux : création par la plateforme, endpoints /partner/*,
inscription d'écoles avec partner_id dérivé côté serveur, unicité d'inscription par école, et
refus d'attribuer PARTNER_ADMIN/PLATFORM_OWNER via les endpoints scopés école."""

import asyncio
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.partners.models import Partner, PartnerSchoolEnrollment
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User
from tests.conftest import register_school, unique_email
from tests.pr17_helpers import (
    auth,
    create_partner,
    create_platform_owner,
    enroll_school_as_partner,
    enrollment_for_school,
    enrollment_payload,
    partner_row_for_user,
)


# === B.1 — création d'un partenaire =================================================================
async def test_create_partner_creates_exactly_one_user_partner_and_global_role(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b1owner")
    email = unique_email("b1partner")
    response = await client.post(
        "/api/v1/platform/partners",
        json={"display_name": "Agence B1", "full_name": "Contact B1", "email": email, "phone": "+22890000000"},
        headers=owner["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["dev_reset_token"]
    assert "hashed_password" not in response.text

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        users = (await db.execute(select(User).where(User.email == email))).scalars().all()
        assert len(users) == 1
        user = users[0]
        assert user.is_platform_admin is False
        assert str(user.id) == body["partner"]["user_id"]

        partners = (await db.execute(select(Partner).where(Partner.user_id == user.id))).scalars().all()
        assert len(partners) == 1
        assert partners[0].display_name == "Agence B1"
        assert partners[0].status == "ACTIVE"

        roles = (
            await db.execute(
                select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == user.id)
            )
        ).all()
        assert len(roles) == 1
        user_role, code = roles[0]
        assert code == "PARTNER_ADMIN"
        assert user_role.organization_id is None
        assert user_role.school_id is None


async def test_partner_activation_link_sets_password(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b1activate")
    partner = await create_partner(client, owner["headers"], "b1activate")
    me = await client.get("/api/v1/auth/me", headers=partner["headers"])
    assert me.status_code == 200
    assert me.json()["user"]["is_platform_admin"] is False
    assert me.json()["roles"] == [{"role_code": "PARTNER_ADMIN", "organization_id": None, "school_id": None}]


async def test_create_partner_ignores_is_platform_admin_in_payload(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b1flag")
    email = unique_email("b1flag")
    response = await client.post(
        "/api/v1/platform/partners",
        json={"display_name": "Flag", "full_name": "Flag", "email": email, "is_platform_admin": True},
        headers=owner["headers"],
    )
    assert response.status_code == 201
    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one()
    assert user.is_platform_admin is False


# === B.2 — endpoints partenaire ======================================================================
async def test_partner_can_use_every_partner_endpoint(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b2owner")
    partner = await create_partner(client, owner["headers"], "b2partner")

    dashboard = await client.get("/api/v1/partner/dashboard", headers=partner["headers"])
    assert dashboard.status_code == 200
    assert dashboard.json() == {"school_count": 0, "organization_count": 0}

    enrolled = await client.post(
        "/api/v1/partner/schools", json=enrollment_payload("b2school"), headers=partner["headers"]
    )
    assert enrolled.status_code == 201, enrolled.text
    assert enrolled.json()["acquisition_source"] == "PARTNER"
    assert enrolled.json()["commission_eligible"] is True

    schools = await client.get("/api/v1/partner/schools", headers=partner["headers"])
    assert schools.status_code == 200
    assert [s["school_id"] for s in schools.json()] == [enrolled.json()["school"]["id"]]
    assert schools.json()[0]["organization_name"] == "b2school Group"
    assert schools.json()[0]["status"] == "ACTIVE"

    accounts = await client.get("/api/v1/partner/accounts", headers=partner["headers"])
    assert accounts.status_code == 200
    assert [a["id"] for a in accounts.json()] == [enrolled.json()["admin"]["id"]]
    assert accounts.json()[0]["role_codes"] == ["SCHOOL_ADMIN"]

    dashboard = await client.get("/api/v1/partner/dashboard", headers=partner["headers"])
    assert dashboard.json() == {"school_count": 1, "organization_count": 1}


async def test_partner_enrolled_school_admin_can_log_in_and_use_own_school(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b2admin")
    partner = await create_partner(client, owner["headers"], "b2admin")
    enrolled = await enroll_school_as_partner(client, partner["headers"], "b2adminschool")
    response = await client.get(
        f"/api/v1/students?school_id={enrolled['school']['id']}", headers=enrolled["admin_headers"]
    )
    assert response.status_code == 200


async def test_partner_endpoints_require_authentication(client: AsyncClient) -> None:
    for path in ("/api/v1/partner/dashboard", "/api/v1/partner/schools", "/api/v1/partner/accounts"):
        assert (await client.get(path)).status_code == 401
    assert (await client.post("/api/v1/partner/schools", json={})).status_code == 401


async def test_suspended_partner_is_refused(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b2suspend")
    partner = await create_partner(client, owner["headers"], "b2suspend")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        row = (await db.execute(select(Partner).where(Partner.id == uuid.UUID(partner["partner"]["id"])))).scalar_one()
        row.status = "SUSPENDED"
        await db.commit()
    assert (await client.get("/api/v1/partner/schools", headers=partner["headers"])).status_code == 403
    response = await client.post(
        "/api/v1/partner/schools", json=enrollment_payload("b2suspend"), headers=partner["headers"]
    )
    assert response.status_code == 403


# === B.3 — partner_id toujours dérivé côté serveur =====================================================
async def test_partner_enrollment_records_own_partner_id(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b3owner")
    partner = await create_partner(client, owner["headers"], "b3partner")
    enrolled = await enroll_school_as_partner(client, partner["headers"], "b3school")

    enrollment = await enrollment_for_school(enrolled["school"]["id"])
    assert enrollment is not None
    assert str(enrollment.partner_id) == partner["partner"]["id"]
    assert enrollment.acquisition_source == "PARTNER"
    assert enrollment.commission_eligible is True
    assert str(enrollment.enrolled_by_user_id) == partner["user_id"]
    assert str(enrollment.organization_id) == enrolled["organization"]["id"]


@pytest.mark.parametrize("forged_field", ["partner_id", "acquisition_source", "commission_eligible"])
async def test_partner_enrollment_rejects_client_supplied_attribution(client: AsyncClient, forged_field: str) -> None:
    owner = await create_platform_owner(client, f"b3forge{forged_field[:4]}")
    partner_a = await create_partner(client, owner["headers"], "b3forgea")
    partner_b = await create_partner(client, owner["headers"], "b3forgeb")
    forged_values = {
        "partner_id": partner_b["partner"]["id"],
        "acquisition_source": "PLATFORM_OWNER",
        "commission_eligible": False,
    }
    payload = enrollment_payload("b3forge")
    payload[forged_field] = forged_values[forged_field]

    response = await client.post("/api/v1/partner/schools", json=payload, headers=partner_a["headers"])
    assert response.status_code == 422

    # Rien n'a été créé, ni pour A ni pour B.
    for p in (partner_a, partner_b):
        schools = await client.get("/api/v1/partner/schools", headers=p["headers"])
        assert schools.json() == []


async def test_super_admin_without_partner_profile_gets_404_on_partner_endpoints(client: AsyncClient) -> None:
    """SUPER_ADMIN détient `partner.*` par convention du catalogue, mais n'est rattaché à aucun
    partenaire : jamais d'inscription « orpheline » ni de lecture d'un partenaire arbitraire."""
    from tests.conftest import create_platform_admin

    super_admin = await create_platform_admin(client, "b3super")
    headers = auth(super_admin["tokens"]["access_token"])
    assert (await client.get("/api/v1/partner/schools", headers=headers)).status_code == 404
    response = await client.post("/api/v1/partner/schools", json=enrollment_payload("b3super"), headers=headers)
    assert response.status_code == 404


# === B.4 — UNIQUE(school_id) en base, sous concurrence ===================================================
async def test_concurrent_enrollments_of_same_school_only_one_succeeds(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b4owner")
    partner_a = await create_partner(client, owner["headers"], "b4a")
    partner_b = await create_partner(client, owner["headers"], "b4b")

    # École existante SANS ligne d'inscription (cas d'une école antérieure à la PR #17) : on la
    # retire pour reproduire deux tentatives concurrentes d'inscrire la MÊME école.
    data = await register_school(client, "b4school")
    school_id = uuid.UUID(data["school"]["id"])
    organization_id = uuid.UUID(data["organization"]["id"])
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        existing = (
            await db.execute(select(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.school_id == school_id))
        ).scalar_one()
        await db.delete(existing)
        await db.commit()

    async def _enroll(partner_id: str) -> str:
        async with AsyncSessionLocal() as db:
            await set_platform_wide_context(db)
            db.add(
                PartnerSchoolEnrollment(
                    id=uuid.uuid4(),
                    partner_id=uuid.UUID(partner_id),
                    organization_id=organization_id,
                    school_id=school_id,
                    acquisition_source="PARTNER",
                    commission_eligible=True,
                )
            )
            try:
                await db.commit()
                return "ok"
            except IntegrityError:
                await db.rollback()
                return "conflict"

    results = await asyncio.gather(_enroll(partner_a["partner"]["id"]), _enroll(partner_b["partner"]["id"]))
    assert sorted(results) == ["conflict", "ok"]

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        count = (
            await db.execute(
                select(func.count()).select_from(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.school_id == school_id)
            )
        ).scalar_one()
    assert count == 1


async def test_partner_cannot_reenroll_school_already_enrolled_by_platform(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "b4dup")
    partner = await create_partner(client, owner["headers"], "b4dup")
    data = await register_school(client, "b4dupschool")
    partner_row = await partner_row_for_user(partner["user_id"])
    assert partner_row is not None

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            PartnerSchoolEnrollment(
                id=uuid.uuid4(),
                partner_id=partner_row.id,
                organization_id=uuid.UUID(data["organization"]["id"]),
                school_id=uuid.UUID(data["school"]["id"]),
                acquisition_source="PARTNER",
                commission_eligible=True,
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    enrollment = await enrollment_for_school(data["school"]["id"])
    assert enrollment is not None and enrollment.acquisition_source == "PLATFORM_OWNER"


# === B.5 — PARTNER_ADMIN / PLATFORM_OWNER jamais attribuables via les endpoints école =====================
@pytest.mark.parametrize("role_code", ["PARTNER_ADMIN", "PLATFORM_OWNER"])
async def test_school_user_creation_rejects_non_school_roles(client: AsyncClient, role_code: str) -> None:
    data = await register_school(client, f"b5create{role_code[:4].lower()}")
    headers = auth(data["tokens"]["access_token"])
    email = unique_email("b5create")
    response = await client.post(
        "/api/v1/users",
        json={"email": email, "full_name": "Intrus", "school_id": data["school"]["id"], "role_code": role_code},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot assign a platform-wide role here"
    async with AsyncSessionLocal() as db:
        assert (await db.execute(select(User).where(User.email == email))).scalar_one_or_none() is None


@pytest.mark.parametrize("role_code", ["PARTNER_ADMIN", "PLATFORM_OWNER"])
async def test_school_user_update_rejects_non_school_roles(client: AsyncClient, role_code: str) -> None:
    data = await register_school(client, f"b5update{role_code[:4].lower()}")
    headers = auth(data["tokens"]["access_token"])
    created = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email("b5update"),
            "full_name": "Enseignant",
            "school_id": data["school"]["id"],
            "role_code": "TEACHER",
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    response = await client.patch(
        f"/api/v1/users/{created.json()['user']['id']}",
        json={"school_id": data["school"]["id"], "role_code": role_code},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Cannot assign a platform-wide role here"
