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


async def _clear_register_rate_limit() -> None:
    """Le rate limiting de /auth/register (Phase 20) est volontairement basé sur l'IP (voir
    app/core/rate_limit.py) — une seule IP peut légitimement créer très peu d'organisations dans
    la vraie vie, contrairement au login. Sous httpx `ASGITransport`, toutes les requêtes de toute
    la suite de tests partagent la même IP factice : sans ce nettoyage, `register_school()` (appelé
    des dizaines de fois par fichier de test, dans toute la suite) finirait par se heurter à cette
    limite bien avant qu'aucun des tests dédiés au rate limiting ne s'exécute. Motif équivalent au
    `_clear_key(email)` déjà utilisé dans test_auth_rate_limit.py, appliqué ici une fois pour
    toutes dans le helper partagé plutôt que dans chaque test individuel. Tolérant à un Redis
    injoignable (certains tests le rendent délibérément injoignable via monkeypatch) — un échec
    ici ne doit jamais faire échouer `register_school()` elle-même."""
    from redis.exceptions import RedisError

    from app.core.rate_limit import _get_client as _get_rate_limit_client

    try:
        redis_client = _get_rate_limit_client()
        async for key in redis_client.scan_iter(match="register_attempts:*"):
            await redis_client.delete(key)
    except RedisError:
        pass


async def register_school(client: AsyncClient, org_prefix: str = "org") -> dict:
    """Crée une organisation + école + SCHOOL_ADMIN via l'API et retourne la réponse complète."""
    await _clear_register_rate_limit()
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
