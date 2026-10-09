"""PR #17 — `core/tenancy.py::apply_tenant_context` : `app.is_platform_wide` dépend du CODE de
rôle (PLATFORM_ROLE_CODES), jamais de la simple nullité de `user_roles.organization_id`."""

import uuid

from httpx import AsyncClient
from sqlalchemy import text

from app.core.tenancy import apply_tenant_context
from app.db.session import AsyncSessionLocal
from tests.conftest import assign_role, create_platform_admin, register_school
from tests.pr17_helpers import create_partner, create_platform_owner


async def _session_settings(user_id: str) -> tuple[str, str]:
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(user_id))
        row = (
            await db.execute(
                text(
                    "SELECT current_setting('app.is_platform_wide', true), "
                    "current_setting('app.tenant_org_ids', true)"
                )
            )
        ).one()
        await db.rollback()
    return row[0], row[1]


async def _strip_roles(user_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.is_platform_wide', 'true', true)"))
        await db.execute(text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": uuid.UUID(user_id)})
        await db.commit()


async def test_partner_admin_global_role_is_not_platform_wide_and_has_no_tenant(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "tenancyowner")
    partner = await create_partner(client, owner["headers"], "tenancypartner")
    assert await _session_settings(partner["user_id"]) == ("false", "")


async def test_partner_admin_stays_non_platform_wide_after_enrolling_schools(client: AsyncClient) -> None:
    """Inscrire des écoles ne donne jamais au partenaire de UserRole sur ces tenants."""
    owner = await create_platform_owner(client, "tenancyenrollowner")
    partner = await create_partner(client, owner["headers"], "tenancyenroll")
    response = await client.post(
        "/api/v1/partner/schools",
        json={
            "organization": {"name": "Tenancy Group", "slug": f"tenancy-{uuid.uuid4().hex[:8]}", "country_code": "TG"},
            "school": {"name": "Tenancy School", "slug": "principale"},
            "admin": {"full_name": "Admin Tenancy", "email": f"admin.{uuid.uuid4().hex[:8]}@edusphere-pytest.tg", "password": "SuperSecret123"},
        },
        headers=partner["headers"],
    )
    assert response.status_code == 201, response.text
    assert await _session_settings(partner["user_id"]) == ("false", "")


async def test_platform_owner_is_platform_wide(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "tenancyowner2")
    assert (await _session_settings(owner["user_id"]))[0] == "true"


async def test_super_admin_is_platform_wide(client: AsyncClient) -> None:
    admin = await create_platform_admin(client, "tenancysuper")
    assert (await _session_settings(admin["user_id"]))[0] == "true"


async def test_platform_support_is_platform_wide(client: AsyncClient) -> None:
    data = await register_school(client, "tenancysupport")
    await _strip_roles(data["user"]["id"])
    await assign_role(data["user"]["id"], "PLATFORM_SUPPORT", organization_id=None, school_id=None)
    assert (await _session_settings(data["user"]["id"]))[0] == "true"


async def test_global_role_with_non_platform_code_is_never_platform_wide(client: AsyncClient) -> None:
    """Preuve directe du correctif : une UserRole globale (organization_id NULL) portant un code
    hors PLATFORM_ROLE_CODES ne rend plus la session platform-wide (avant PR #17 : 'true')."""
    data = await register_school(client, "tenancynullity")
    await _strip_roles(data["user"]["id"])
    await assign_role(data["user"]["id"], "TEACHER", organization_id=None, school_id=None)
    assert await _session_settings(data["user"]["id"]) == ("false", "")


async def test_school_admin_context_is_unchanged(client: AsyncClient) -> None:
    data = await register_school(client, "tenancyschool")
    assert await _session_settings(data["user"]["id"]) == ("false", data["organization"]["id"])
