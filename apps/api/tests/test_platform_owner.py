"""PR #17 — rôle PLATFORM_OWNER : accès plateforme (métadonnées) sans aucun accès aux données
scolaires, traçabilité des inscriptions directes, et contexte RLS platform-wide basé sur le code
de rôle (core/tenancy.py::apply_tenant_context)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.permissions import require_platform_admin
from app.core.tenancy import apply_tenant_context
from app.db.session import AsyncSessionLocal
from app.main import app
from tests.conftest import assign_role, register_school, unique_email
from tests.pr17_helpers import (
    PARTNER_GET_ENDPOINTS,
    PLATFORM_GET_ENDPOINTS,
    auth,
    create_partner,
    create_platform_owner,
    enrollment_for_school,
    enrollment_payload,
    login,
    school_data_endpoints,
    school_with_student,
)


# === A.1 — accès plateforme ======================================================================
async def test_platform_owner_can_read_every_platform_endpoint(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a1owner")
    for path in PLATFORM_GET_ENDPOINTS:
        response = await client.get(path, headers=owner["headers"])
        assert response.status_code == 200, (path, response.text)


async def test_platform_owner_can_enroll_organization_via_existing_endpoint(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a1enroll")
    response = await client.post(
        "/api/v1/platform/organizations", json=enrollment_payload("a1enroll"), headers=owner["headers"]
    )
    assert response.status_code == 201, response.text


async def test_platform_owner_can_create_partner(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a1partner")
    partner = await create_partner(client, owner["headers"], "a1partner")
    assert partner["partner"]["status"] == "ACTIVE"
    assert partner["partner"]["enrollment_count"] == 0


async def test_platform_lists_expose_metadata_of_all_tenants(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a1lists")
    data = await register_school(client, "a1listsschool")
    partner = await create_partner(client, owner["headers"], "a1listspartner")
    params = "?page=1&page_size=100"  # tri created_at DESC : les lignes créées ici sont en tête.

    orgs = (await client.get(f"/api/v1/platform/organizations{params}", headers=owner["headers"])).json()
    assert set(orgs.keys()) == {"items", "page", "page_size", "total", "total_pages"}
    assert orgs["page_size"] == 100 and orgs["total"] >= 1
    assert data["organization"]["id"] in {o["id"] for o in orgs["items"]}
    assert set(orgs["items"][0].keys()) == {"id", "name", "slug", "country_code", "created_at"}

    schools = (await client.get(f"/api/v1/platform/schools{params}", headers=owner["headers"])).json()
    school = next(s for s in schools["items"] if s["id"] == data["school"]["id"])
    assert school["acquisition_source"] == "PLATFORM_OWNER"

    accounts = (await client.get(f"/api/v1/platform/accounts{params}", headers=owner["headers"])).json()
    by_id = {a["id"]: a for a in accounts["items"]}
    assert by_id[data["user"]["id"]]["role_codes"] == ["SCHOOL_ADMIN"]
    assert by_id[partner["user_id"]]["role_codes"] == ["PARTNER_ADMIN"]
    assert set(by_id[data["user"]["id"]].keys()) == {"id", "email", "full_name", "is_active", "created_at", "role_codes"}

    partners = (await client.get(f"/api/v1/platform/partners{params}", headers=owner["headers"])).json()
    assert partner["partner"]["id"] in {p["id"] for p in partners["items"]}


async def test_platform_lists_validate_pagination(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a1page")
    for path in PLATFORM_GET_ENDPOINTS[1:]:
        assert (await client.get(f"{path}?page=0", headers=owner["headers"])).status_code == 422
        assert (await client.get(f"{path}?page_size=101", headers=owner["headers"])).status_code == 422
        body = (await client.get(f"{path}?page_size=1", headers=owner["headers"])).json()
        assert len(body["items"]) <= 1


async def test_platform_dashboard_exposes_partner_and_enrollment_counts(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a1dash")
    before = (await client.get("/api/v1/platform/dashboard", headers=owner["headers"])).json()
    await create_partner(client, owner["headers"], "a1dashpartner")
    await register_school(client, "a1dashschool")
    after = (await client.get("/api/v1/platform/dashboard", headers=owner["headers"])).json()
    assert after["partner_count"] == before["partner_count"] + 1
    assert after["enrollment_count"] == before["enrollment_count"] + 1


async def test_platform_partner_creation_rejects_existing_email(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a1dup")
    data = await register_school(client, "a1dupschool")
    response = await client.post(
        "/api/v1/platform/partners",
        json={"display_name": "Doublon", "full_name": "Doublon", "email": data["user"]["email"]},
        headers=owner["headers"],
    )
    assert response.status_code == 409


# === A.2 — aucune donnée scolaire =================================================================
async def test_platform_owner_gets_403_on_every_school_data_domain(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a2owner")
    data = await school_with_student(client, "a2school")
    for path in school_data_endpoints(data["school"]["id"], data["student"]["id"]):
        response = await client.get(path, headers=owner["headers"])
        # PLATFORM_OWNER est platform-wide côté RLS (il VOIT l'école/l'élève, d'où 403 et non 404) :
        # c'est le contrôle RBAC applicatif qui refuse, faute de toute permission scolaire.
        assert response.status_code == 403, (path, response.status_code, response.text)


async def test_platform_owner_cannot_write_school_data(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a2write")
    data = await school_with_student(client, "a2writeschool")
    response = await client.patch(
        f"/api/v1/students/{data['student']['id']}", json={"first_name": "Pirate"}, headers=owner["headers"]
    )
    assert response.status_code == 403
    response = await client.post(
        "/api/v1/users",
        json={
            "email": unique_email("a2write"),
            "full_name": "Intrus",
            "school_id": data["school"]["id"],
            "role_code": "TEACHER",
        },
        headers=owner["headers"],
    )
    assert response.status_code == 403


async def test_platform_owner_cannot_use_partner_endpoints(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a2partnerep")
    for path in PARTNER_GET_ENDPOINTS:
        response = await client.get(path, headers=owner["headers"])
        assert response.status_code == 403, (path, response.text)
    response = await client.post(
        "/api/v1/partner/schools", json=enrollment_payload("a2partnerep"), headers=owner["headers"]
    )
    assert response.status_code == 403


def test_no_school_data_route_relies_on_require_platform_admin() -> None:
    """Décision #3 : `is_platform_admin=True` seul ne donne jamais accès aux données scolaires.
    Seules les deux routes historiques de /platform utilisent `require_platform_admin`."""

    def _uses(dependant) -> bool:  # type: ignore[no-untyped-def]
        return any(dep.call is require_platform_admin or _uses(dep) for dep in dependant.dependencies)

    users = {
        (sorted(route.methods)[0], route.path)
        for route in app.routes
        if hasattr(route, "dependant") and _uses(route.dependant)
    }
    assert users == {("GET", "/api/v1/platform/dashboard"), ("POST", "/api/v1/platform/organizations")}


# === A.3 — traçabilité de l'inscription directe ===================================================
async def test_platform_enrollment_records_platform_owner_source(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a3owner")
    response = await client.post(
        "/api/v1/platform/organizations", json=enrollment_payload("a3owner"), headers=owner["headers"]
    )
    assert response.status_code == 201, response.text
    enrollment = await enrollment_for_school(response.json()["school"]["id"])
    assert enrollment is not None
    assert enrollment.partner_id is None
    assert enrollment.acquisition_source == "PLATFORM_OWNER"
    assert enrollment.commission_eligible is False
    assert str(enrollment.enrolled_by_user_id) == owner["user_id"]
    assert str(enrollment.organization_id) == response.json()["organization"]["id"]


async def test_platform_enrollment_rollback_leaves_no_enrollment(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await create_platform_owner(client, "a3rollback")
    payload = enrollment_payload("a3rollback")

    def _boom(_password: str) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr("app.modules.platform.service.hash_password", _boom)
    with pytest.raises(RuntimeError):
        await client.post("/api/v1/platform/organizations", json=payload, headers=owner["headers"])

    async with AsyncSessionLocal() as db:
        await db.execute(text("SELECT set_config('app.is_platform_wide', 'true', true)"))
        count = (
            await db.execute(
                text(
                    "SELECT count(*) FROM partner_school_enrollments e JOIN organizations o "
                    "ON o.id = e.organization_id WHERE o.slug = :slug"
                ),
                {"slug": payload["organization"]["slug"]},
            )
        ).scalar_one()
    assert count == 0


# === A.4 — comptes scolaires refusés sur /platform/* ================================================
@pytest.mark.parametrize("role_code", ["SCHOOL_ADMIN", "DIRECTOR", "TEACHER"])
async def test_school_roles_get_403_on_every_new_platform_endpoint(client: AsyncClient, role_code: str) -> None:
    data = await register_school(client, f"a4{role_code.lower().replace('_', '')}")
    if role_code == "SCHOOL_ADMIN":
        headers = auth(data["tokens"]["access_token"])
    else:
        other = await register_school(client, f"a4{role_code.lower().replace('_', '')}-user")
        # Retire son SCHOOL_ADMIN d'origine pour isoler le rôle testé (même motif que test_rbac.py).
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT set_config('app.is_platform_wide', 'true', true)"))
            await db.execute(
                text("DELETE FROM user_roles WHERE user_id = :uid"), {"uid": uuid.UUID(other["user"]["id"])}
            )
            await db.commit()
        await assign_role(other["user"]["id"], role_code, data["organization"]["id"], data["school"]["id"])
        headers = await login(client, other["user"]["email"])

    for path in PLATFORM_GET_ENDPOINTS:
        response = await client.get(path, headers=headers)
        assert response.status_code == 403, (role_code, path, response.text)
    response = await client.post(
        "/api/v1/platform/partners",
        json={"display_name": "X", "full_name": "Xx", "email": unique_email("a4")},
        headers=headers,
    )
    assert response.status_code == 403
    response = await client.post("/api/v1/platform/organizations", json=enrollment_payload("a4"), headers=headers)
    assert response.status_code == 403


async def test_new_platform_endpoints_require_authentication(client: AsyncClient) -> None:
    for path in PLATFORM_GET_ENDPOINTS:
        assert (await client.get(path)).status_code == 401
    assert (await client.post("/api/v1/platform/partners", json={})).status_code == 401


# === A.5 — contexte RLS =============================================================================
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


async def test_platform_owner_tenant_context_is_platform_wide(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a5owner")
    assert (await _session_settings(owner["user_id"]))[0] == "true"


async def test_platform_owner_session_reads_rows_of_every_organization(client: AsyncClient) -> None:
    owner = await create_platform_owner(client, "a5rows")
    school_a = await register_school(client, "a5rowsa")
    school_b = await register_school(client, "a5rowsb")
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(owner["user_id"]))
        ids = {
            row[0]
            for row in (
                await db.execute(
                    text("SELECT id::text FROM organizations WHERE id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": [school_a["organization"]["id"], school_b["organization"]["id"]]},
                )
            ).all()
        }
        await db.rollback()
    assert ids == {school_a["organization"]["id"], school_b["organization"]["id"]}
