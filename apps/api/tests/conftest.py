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


async def _clear_shared_ip_rate_limits() -> None:
    """Sous httpx `ASGITransport`, toutes les requêtes de toute la suite de tests partagent la
    même IP factice (127.0.0.1). Les endpoints rate-limités PAR IP (reset-password,
    report-card-verify — voir app/core/rate_limit.py) accumulent donc un compteur unique et
    partagé entre des dizaines de tests indépendants qui les appellent incidemment (ex.
    `reset-password` est appelé par la quasi-totalité des helpers de fixtures qui créent un
    compte). Nettoyé avant CHAQUE test plutôt qu'une seule fois par fichier, pour qu'aucun ordre
    d'exécution ne fasse dépendre un test du nettoyage effectué par un autre. Tolérant à un Redis
    injoignable (certains tests le rendent délibérément injoignable via monkeypatch)."""
    from redis.exceptions import RedisError

    from app.core.rate_limit import _get_client as _get_rate_limit_client

    try:
        redis_client = _get_rate_limit_client()
        for pattern in ("reset_password_attempts:*", "report_card_verify_attempts:*"):
            async for key in redis_client.scan_iter(match=pattern):
                await redis_client.delete(key)
    except RedisError:
        pass


@pytest_asyncio.fixture
async def client():
    await _clear_shared_ip_rate_limits()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def valid_image_bytes(image_format: str = "JPEG") -> bytes:
    """Contenu d'image RÉEL (pas juste des octets factices) : la validation stricte des uploads
    photo/document (students/service.py::validate_photo_upload) ouvre réellement le contenu avec
    Pillow — un ancien placeholder comme b"fake-jpeg-bytes" est maintenant rejeté à juste titre."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color=(255, 0, 0)).save(buffer, format=image_format)
    return buffer.getvalue()


def valid_pdf_bytes() -> bytes:
    """La détection de PDF (students/service.py::_sniff_mime) ne vérifie que la signature
    d'en-tête "%PDF-" — pas besoin d'un PDF structurellement complet pour ces tests."""
    return b"%PDF-1.4\n%fake-but-correctly-signed-pdf-content\n%%EOF"


def unique_slug(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def unique_email(prefix: str) -> str:
    # email-validator rejette les domaines réservés IANA (example.com/.test/.invalid/...)
    # même en syntaxe pure (sans vérification DNS/délivrabilité, désactivée par défaut).
    return f"{prefix}.{uuid.uuid4().hex[:10]}@edusphere-pytest.tg"


_PLATFORM_ADMIN_EMAIL: str | None = None
_TEST_PASSWORD = "SuperSecret123"


async def _platform_admin_headers(client: AsyncClient) -> dict[str, str]:
    """Headers d'un compte plateforme partagé pour toute la suite (créé une seule fois, puis
    reconnecté à chaque appel pour un token frais — le token d'accès expire après 15 minutes)."""
    global _PLATFORM_ADMIN_EMAIL
    if _PLATFORM_ADMIN_EMAIL is None:
        admin = await create_platform_admin(client, "tenantfactory")
        _PLATFORM_ADMIN_EMAIL = admin["email"]
    login = await client.post(
        "/api/v1/auth/login", json={"email": _PLATFORM_ADMIN_EMAIL, "password": _TEST_PASSWORD}
    )
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


async def register_school(client: AsyncClient, org_prefix: str = "org") -> dict:
    """Crée une organisation + école + SCHOOL_ADMIN via POST /api/v1/platform/organizations (seul
    point d'entrée de création, réservé aux platform admins), puis connecte le SCHOOL_ADMIN créé
    pour obtenir ses tokens. Retourne {organization, school, user, tokens}."""
    headers = await _platform_admin_headers(client)
    admin_email = unique_email(f"admin.{org_prefix}")
    payload = {
        "organization": {
            "name": f"{org_prefix} Group",
            "slug": unique_slug(org_prefix),
            "country_code": "TG",
        },
        "school": {"name": f"{org_prefix} School", "slug": "principale"},
        "admin": {
            "full_name": f"Admin {org_prefix}",
            "email": admin_email,
            "password": _TEST_PASSWORD,
        },
    }
    response = await client.post("/api/v1/platform/organizations", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    created = response.json()

    login = await client.post("/api/v1/auth/login", json={"email": admin_email, "password": _TEST_PASSWORD})
    assert login.status_code == 200, login.text
    return {
        "organization": created["organization"],
        "school": created["school"],
        "user": created["admin"],
        "tokens": login.json(),
    }


async def create_platform_admin(client: AsyncClient, prefix: str = "platformadmin") -> dict:
    """Crée un compte plateforme pur (is_platform_admin=True, SUPER_ADMIN, aucune organisation/
    école) et retourne ses tokens. Il n'existe pas de flux d'inscription public pour ce type de
    compte (la création d'organisation ne produit qu'un SCHOOL_ADMIN rattaché à un nouveau tenant — voir
    test_register_never_grants_platform_admin) : c'est un compte insensible-tenant seed en
    production, reproduit ici directement en base, même motif que assign_role() ci-dessous."""
    import uuid as uuid_module

    from app.core.security import hash_password
    from app.core.tenancy import set_platform_wide_context
    from app.modules.users.models import User

    password = "SuperSecret123"
    email = unique_email(prefix)
    user_id = uuid_module.uuid4()

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            User(
                id=user_id,
                email=email,
                full_name=f"Platform Admin {prefix}",
                hashed_password=hash_password(password),
                is_active=True,
                is_platform_admin=True,
            )
        )
        await db.commit()

    await assign_role(str(user_id), "SUPER_ADMIN", organization_id=None, school_id=None)

    await _clear_shared_ip_rate_limits()
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"user_id": str(user_id), "email": email, "tokens": login.json()}


async def assign_role(user_id: str, role_code: str, organization_id: str | None, school_id: str | None) -> None:
    """Attribue un rôle directement en base — il n'existe pas encore d'endpoint d'invitation
    d'utilisateur en Phase 1 (différé, cf. PHASE_1_AUTH_MULTITENANCY_PLAN.md §5)."""
    from sqlalchemy import select

    from app.core.tenancy import set_platform_wide_context
    from app.modules.rbac.models import Role, UserRole

    async with AsyncSessionLocal() as db:
        # user_roles a RLS activé (voir migration 0002) : un insert direct hors requête HTTP
        # authentifiée n'a pas de contexte tenant — on l'accorde explicitement ici, comme le
        # fait le service de création d'organisation pour la même raison.
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
