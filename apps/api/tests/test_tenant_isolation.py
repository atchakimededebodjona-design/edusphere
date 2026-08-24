"""Test 1 — Isolation tenant (critique, cahier des charges §45).

« Utilisateur École A -> impossible d'accéder aux données École B. »
Vérifie les deux lignes de défense : filtrage applicatif (permissions scopées) ET
PostgreSQL Row Level Security (schools, user_roles) — même en forgeant un organization_id.
"""

from httpx import AsyncClient

from tests.conftest import register_school


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_admin_a_cannot_read_school_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isoread-a")
    school_b = await register_school(client, "isoread-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.get(
        f"/api/v1/schools/{school_b['school']['id']}", headers={"Authorization": f"Bearer {token_a}"}
    )
    assert response.status_code in (403, 404)


async def test_admin_a_cannot_update_school_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isowrite-a")
    school_b = await register_school(client, "isowrite-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.patch(
        f"/api/v1/schools/{school_b['school']['id']}",
        json={"name": "Piraté"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code in (403, 404)

    # La donnée de B n'a réellement pas changé.
    token_b = await _login(client, school_b["user"]["email"])
    check = await client.get(
        f"/api/v1/schools/{school_b['school']['id']}", headers={"Authorization": f"Bearer {token_b}"}
    )
    assert check.json()["name"] == school_b["school"]["name"]
    assert check.json()["name"] != "Piraté"


async def test_admin_a_cannot_list_schools_of_organization_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isolist-a")
    school_b = await register_school(client, "isolist-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.get(
        f"/api/v1/schools?organization_id={school_b['organization']['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


async def test_admin_a_cannot_read_organization_b(client: AsyncClient) -> None:
    school_a = await register_school(client, "isoorg-a")
    school_b = await register_school(client, "isoorg-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.get(
        f"/api/v1/organizations/{school_b['organization']['id']}",
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


async def test_admin_a_cannot_create_school_under_organization_b(client: AsyncClient) -> None:
    """Même en forgeant explicitement l'organization_id de B dans le corps de la requête."""
    school_a = await register_school(client, "isocreate-a")
    school_b = await register_school(client, "isocreate-b")
    token_a = await _login(client, school_a["user"]["email"])

    response = await client.post(
        "/api/v1/schools",
        json={
            "organization_id": school_b["organization"]["id"],
            "name": "École intruse",
            "slug": "intruse",
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response.status_code == 403


async def test_row_level_security_hides_school_row_even_bypassing_app_check(client: AsyncClient) -> None:
    """Vérifie directement au niveau base (rôle applicatif non-superutilisateur) que la ligne
    de l'école B est invisible sous le contexte tenant de A — la garantie RLS elle-même, pas
    seulement le contrôle applicatif au-dessus."""
    import uuid

    from sqlalchemy import select

    from app.core.tenancy import apply_tenant_context
    from app.db.session import AsyncSessionLocal
    from app.modules.schools.models import School

    school_a = await register_school(client, "isorls-a")
    school_b = await register_school(client, "isorls-b")

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(school_a["user"]["id"]))
        result = await db.execute(select(School).where(School.id == uuid.UUID(school_b["school"]["id"])))
        assert result.scalar_one_or_none() is None

        # Contrôle positif : la même session voit bien sa propre école.
        own = await db.execute(select(School).where(School.id == uuid.UUID(school_a["school"]["id"])))
        assert own.scalar_one_or_none() is not None
        await db.rollback()
