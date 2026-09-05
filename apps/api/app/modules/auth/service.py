import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email_best_effort
from app.core.rate_limit import ensure_refresh_not_rate_limited, register_refresh_attempt
from app.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_opaque_token,
    hash_password,
    refresh_token_expiry,
    verify_password,
)
from app.core.tenancy import set_platform_wide_context
from app.modules.auth.models import PasswordResetToken, UserSession
from app.modules.auth.schemas import RegisterRequest, TokenPair
from app.modules.organizations.models import Organization
from app.modules.rbac.models import Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User

PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30

# Phase 13 (HIGH #2 — canal de fuite temporelle) : hash bcrypt précalculé une seule fois, au
# chargement du module. `authenticate()` l'utilise pour payer un coût bcrypt identique que le
# compte existe ou non, afin que la latence de réponse ne révèle plus l'existence d'un email. Le
# mot de passe d'origine n'a aucune importance — ce hash n'est jamais comparé à une vraie entrée
# utilisateur avec l'intention de réussir.
_DUMMY_PASSWORD_HASH = hash_password("edusphere-timing-mitigation-placeholder")


async def register(db: AsyncSession, payload: RegisterRequest) -> tuple[Organization, School, User, TokenPair]:
    """Crée une nouvelle organisation, sa première école et son premier SCHOOL_ADMIN.

    Il n'existe aucun contexte tenant authentifié à ce stade (l'utilisateur n'existe pas
    encore) : on crée explicitement un nouveau tenant, ce qui n'expose aucune donnée d'un
    tenant existant. C'est le seul endroit de l'application où ce bypass RLS est légitime.
    """
    result = await db.execute(select(Role).where(Role.code == "SCHOOL_ADMIN"))
    school_admin_role = result.scalar_one_or_none()
    if school_admin_role is None:
        raise RuntimeError("SCHOOL_ADMIN role is missing — RBAC seed data was not applied")

    await set_platform_wide_context(db)

    try:
        # Flush (pas commit) après CHAQUE ajout : sans relationship() ORM entre ces modules,
        # l'unit-of-work de SQLAlchemy ne connaît pas la dépendance user -> user_role et peut
        # tenter de les insérer dans le mauvais ordre. Un flush par objet force l'ordre.
        #
        # `refresh()` doit aussi se faire AVANT le commit final : la ligne `schools` n'est
        # visible que le temps de la transaction courante (SET LOCAL app.is_platform_wide=
        # 'true' expire au commit) ; un refresh après coup, sans contexte tenant, ne
        # verrait plus la ligne (RLS).
        organization = Organization(
            id=uuid.uuid4(),
            name=payload.organization_name,
            slug=payload.organization_slug,
            country_code=payload.country_code.upper(),
        )
        db.add(organization)
        await db.flush()

        school = School(
            id=uuid.uuid4(),
            organization_id=organization.id,
            name=payload.school_name,
            slug=payload.school_slug,
        )
        db.add(school)
        await db.flush()

        user = User(
            id=uuid.uuid4(),
            email=payload.admin_email.lower(),
            full_name=payload.admin_full_name,
            hashed_password=hash_password(payload.admin_password),
        )
        db.add(user)
        await db.flush()

        user_role = UserRole(
            id=uuid.uuid4(),
            user_id=user.id,
            role_id=school_admin_role.id,
            organization_id=organization.id,
            school_id=None,
        )
        db.add(user_role)
        await db.flush()

        await db.refresh(organization)
        await db.refresh(school)
        await db.refresh(user)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Organization slug or admin email already in use",
        ) from exc

    tokens = await _issue_tokens(db, user, device_id=None, ip=None, user_agent=None)
    return organization, school, user, tokens


async def authenticate(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()

    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user is None or not user.is_active:
        # Phase 13 (HIGH #2) : coût bcrypt payé même quand il n'y a rien à vérifier, pour que
        # cette branche prenne un temps comparable à un mot de passe invalide sur un compte actif
        # ci-dessous — sans ce travail, un compte inexistant (ou désactivé) répondait nettement
        # plus vite, ce qui constituait un oracle d'énumération de comptes malgré le message
        # générique déjà en place.
        verify_password(password, _DUMMY_PASSWORD_HASH)
        raise invalid

    if not verify_password(password, user.hashed_password):
        raise invalid

    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


async def _issue_tokens(
    db: AsyncSession, user: User, device_id: str | None, ip: str | None, user_agent: str | None
) -> TokenPair:
    refresh_token = generate_opaque_token()
    session = UserSession(
        id=uuid.uuid4(),
        user_id=user.id,
        refresh_token_hash=hash_opaque_token(refresh_token),
        device_id=device_id,
        ip=ip,
        user_agent=user_agent,
        expires_at=refresh_token_expiry(),
    )
    db.add(session)
    await db.commit()

    access_token = create_access_token(user.id)
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


async def login(
    db: AsyncSession, email: str, password: str, device_id: str | None, ip: str | None, user_agent: str | None
) -> TokenPair:
    user = await authenticate(db, email, password)
    return await _issue_tokens(db, user, device_id, ip, user_agent)


async def _get_active_session(db: AsyncSession, refresh_token: str) -> UserSession:
    token_hash = hash_opaque_token(refresh_token)
    result = await db.execute(select(UserSession).where(UserSession.refresh_token_hash == token_hash))
    session = result.scalar_one_or_none()

    invalid = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")
    if session is None:
        raise invalid
    now = datetime.now(timezone.utc)
    if session.revoked_at is not None or session.expires_at < now:
        raise invalid
    return session


async def refresh(db: AsyncSession, refresh_token: str, ip: str | None, user_agent: str | None) -> TokenPair:
    session = await _get_active_session(db, refresh_token)

    user = await db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    # Phase 20 — vérifié seulement après validation du token présenté (session active, utilisateur
    # trouvé) et AVANT toute mutation : un jeton invalide ne consomme jamais le compteur d'un vrai
    # utilisateur, et une requête rate-limitée ne brûle jamais le jeton encore valide du client
    # (voir app/core/rate_limit.py::ensure_refresh_not_rate_limited pour le choix de la clé user_id).
    await ensure_refresh_not_rate_limited(user.id)
    await register_refresh_attempt(user.id)

    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()

    return await _issue_tokens(db, user, session.device_id, ip, user_agent)


async def logout(db: AsyncSession, refresh_token: str) -> None:
    session = await _get_active_session(db, refresh_token)
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def list_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[UserSession]:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > now)
        .order_by(UserSession.created_at.desc())
    )
    return list(result.scalars().all())


async def revoke_session(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
    session = await db.get(UserSession, session_id)
    if session is None or session.user_id != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def request_password_reset(db: AsyncSession, email: str) -> str | None:
    """Retourne le token brut uniquement hors production (email non intégré en Phase 1).

    Phase 13 (HIGH #2) : un travail équivalent (génération + hachage d'un token) est effectué
    même pour un email inexistant, pour réduire l'écart de coût CPU par rapport à la branche
    "compte existant" ci-dessous. Mitigation PARTIELLE, documentée comme telle (voir
    PHASE_13_IMPLEMENTATION.md) : le principal facteur de latence restant — l'écriture en base
    puis l'envoi de l'email, potentiellement un appel réseau SMTP variable — n'est pas équilibré
    ici. Le faire proprement demanderait soit un délai artificiel disproportionné sur toutes les
    requêtes, soit une file d'attente différée : les deux sont explicitement hors périmètre de
    cette phase (pas de queue/worker sans besoin démontré). La limitation de débit déjà en place
    (Phase 10.1 — 3 tentatives/15 min par email) reste la protection principale contre une
    exploitation pratique de ce résidu."""
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        # Travail factice de coût comparable à la préparation du token réel ci-dessous, sans
        # écriture en base ni envoi d'email (jamais d'email supplémentaire pour un compte
        # inexistant — voir docstring).
        hash_opaque_token(generate_opaque_token())
        return None  # ne pas révéler si l'email existe

    raw_token = generate_opaque_token()
    reset_token = PasswordResetToken(
        id=uuid.uuid4(),
        user_id=user.id,
        token_hash=hash_opaque_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
    )
    db.add(reset_token)
    await db.commit()

    await send_email_best_effort(
        user.email,
        "Réinitialisation de votre mot de passe EduSphere",
        f"Pour définir un nouveau mot de passe, ouvrez ce lien (valable "
        f"{PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes) :\n"
        f"{settings.public_web_base_url}/reset-password?token={raw_token}",
    )

    return None if settings.environment == "production" else raw_token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    token_hash = hash_opaque_token(token)
    result = await db.execute(select(PasswordResetToken).where(PasswordResetToken.token_hash == token_hash))
    reset_token = result.scalar_one_or_none()

    invalid = HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token")
    now = datetime.now(timezone.utc)
    if reset_token is None or reset_token.used_at is not None or reset_token.expires_at < now:
        raise invalid

    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise invalid

    user.hashed_password = hash_password(new_password)
    reset_token.used_at = now
    await db.commit()
