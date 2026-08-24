import asyncio
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.db.session import AsyncSessionLocal
from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Boucle d'événements unique pour toute la session de tests.

    Le moteur SQLAlchemy async (app/db/session.py) est un singleton créé à l'import, avec son
    propre pool de connexions asyncpg. Avec la boucle d'événements par défaut de pytest-asyncio
    (recréée à chaque test), les connexions du pool restent liées à une boucle fermée entre deux
    tests, ce qui plante sur Windows (asyncio.ProactorEventLoop). Une boucle de portée session
    évite ce problème.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def unique_email(prefix: str) -> str:
    # email-validator rejette les domaines réservés IANA (example.com/.test/.invalid/...)
    # même en syntaxe pure (sans vérification DNS/délivrabilité, désactivée par défaut).
    return f"{prefix}.{uuid.uuid4().hex[:10]}@edusphere-pytest.tg"


async def register_school(client: AsyncClient, org_prefix: str = "org") -> dict:
    """Crée une organisation + école + SCHOOL_ADMIN via l'API et retourne la réponse complète."""
    payload = {
        "organization_name": f"{org_prefix} Group",
        "organization_slug": unique_slug(org_prefix),
        "country_code": "TG",
        "school_name": f"{org_prefix} School",
        "school_slug": "principale",
        "admin_full_name": f"Admin {org_prefix}",
        "admin_email": unique_email(f"admin.{org_prefix}"),
        "admin_password": "SuperSecret123",
    }
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def assign_role(user_id: str, role_code: str, organization_id: str | None, school_id: str | None) -> None:
    """Attribue un rôle directement en base — il n'existe pas encore d'endpoint d'invitation
    d'utilisateur en Phase 1 (différé, cf. PHASE_1_AUTH_MULTITENANCY_PLAN.md §5)."""
    from sqlalchemy import select

    from app.core.tenancy import set_platform_wide_context
    from app.modules.rbac.models import Role, UserRole

    async with AsyncSessionLocal() as db:
        # user_roles a RLS activé (voir migration 0002) : un insert direct hors requête HTTP
        # authentifiée n'a pas de contexte tenant — on l'accorde explicitement ici, comme le
        # fait le service register() pour la même raison.
        await set_platform_wide_context(db)
        result = await db.execute(select(Role).where(Role.code == role_code))
        role = result.scalar_one()
        db.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=uuid.UUID(user_id),
                role_id=role.id,
                organization_id=uuid.UUID(organization_id) if organization_id else None,
                school_id=uuid.UUID(school_id) if school_id else None,
            )
        )
        await db.commit()
