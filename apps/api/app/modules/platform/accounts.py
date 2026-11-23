"""Retrait des comptes par la plateforme (demande du 2026-11-18, migration 0035).

Le propriétaire de la plateforme (permission `platform.accounts.manage`) peut :
- **désactiver** un compte : plus aucune connexion ni requête (chaque requête et chaque
  renouvellement de session vérifient `is_active`) ; ses sessions sont fermées et ses appareils
  retirés des notifications téléphone. **Réversible** (« réactiver ») ;
- **supprimer** un compte, définitivement : nom, email, téléphone, photo et mot de passe effacés ; rôles,
  affectations d'enseignant, liens de tuteur, notifications, sessions et appareils retirés. La ligne
  `users` reste, avec `deleted_at`/`deleted_by` : l'historique (paiements, caisses, appels, notes,
  audit) garde sa référence, affichée « Compte supprimé ». L'email redevient libre.

Jamais sur son propre compte ni sur un compte plateforme (`is_platform_admin` ou rôle de
`PLATFORM_ROLE_CODES`). Un compte partenaire se désactive mais ne se supprime pas ici : sa fiche
partenaire et ses commissions lui restent rattachées.

Pas de journal d'audit possible (`audit_logs` exige une école) : la suppression est tracée sur le
compte lui-même, et chaque action dans les journaux de l'API (identifiants seulement).
"""

import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.core.tenancy import set_platform_wide_context
from app.modules.academics.models import TeacherAssignment
from app.modules.auth.models import PasswordResetToken, UserSession
from app.modules.notifications.models import Notification, PushDevice
from app.modules.rbac.models import PLATFORM_ROLE_CODES, Role, UserRole
from app.modules.students.models import Guardian
from app.modules.users.models import User
from app.modules.users.photo import delete_photo_file_best_effort

logger = logging.getLogger(__name__)

DELETED_ACCOUNT_NAME = "Compte supprimé"
# Domaine réservé (RFC 2606) : aucune adresse en « .invalid » ne peut recevoir de courrier.
DELETED_EMAIL_DOMAIN = "comptes-supprimes.invalid"

SELF_DETAIL = "Vous ne pouvez pas retirer votre propre compte."
PLATFORM_DETAIL = "Les comptes de la plateforme ne se retirent pas depuis cette page."
DELETED_DETAIL = "Ce compte a déjà été supprimé."
PARTNER_DETAIL = (
    "Compte partenaire : désactivez-le. Sa fiche partenaire et ses commissions lui restent rattachées, "
    "il ne se supprime pas."
)
CONFIRM_DETAIL = "Pour confirmer, saisissez exactement l'adresse email du compte."


def deleted_email(user_id: uuid.UUID) -> str:
    return f"supprime-{user_id.hex}@{DELETED_EMAIL_DOMAIN}"


async def search_accounts(
    db: AsyncSession, page: int, page_size: int, query: str | None
) -> tuple[list[User], int]:
    """Comptes, les plus récents d'abord ; `query` cherche dans le nom et l'email (sans casse)."""
    await set_platform_wide_context(db)
    condition = None
    if query and query.strip():
        pattern = f"%{query.strip().lower()}%"
        condition = or_(func.lower(User.full_name).like(pattern), func.lower(User.email).like(pattern))
    listing = select(User).order_by(User.created_at.desc(), User.id)
    counting = select(func.count()).select_from(User)
    if condition is not None:
        listing = listing.where(condition)
        counting = counting.where(condition)
    users = list((await db.execute(listing.offset((page - 1) * page_size).limit(page_size))).scalars().all())
    total = int((await db.execute(counting)).scalar_one())
    return users, total


async def _global_role_codes(db: AsyncSession, user_id: uuid.UUID) -> set[str]:
    result = await db.execute(
        select(Role.code)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id, UserRole.organization_id.is_(None), UserRole.school_id.is_(None))
    )
    return {row[0] for row in result.all()}


async def _target(db: AsyncSession, actor_id: uuid.UUID, user_id: uuid.UUID) -> tuple[User, set[str]]:
    """Compte visé, verrouillé pour la durée de la transaction, après les refus communs."""
    await set_platform_wide_context(db)
    if user_id == actor_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=SELF_DETAIL)
    user = (await db.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Compte introuvable.")
    global_codes = await _global_role_codes(db, user.id)
    if user.is_platform_admin or global_codes & PLATFORM_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PLATFORM_DETAIL)
    if user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DELETED_DETAIL)
    return user, global_codes


async def _close_sessions_and_devices(db: AsyncSession, user_id: uuid.UUID, now: datetime) -> None:
    await db.execute(
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await db.execute(delete(PushDevice).where(PushDevice.user_id == user_id))


async def set_account_active(db: AsyncSession, actor_id: uuid.UUID, user_id: uuid.UUID, active: bool) -> User:
    user, _codes = await _target(db, actor_id, user_id)
    if user.is_active != active:
        user.is_active = active
        if not active:
            await _close_sessions_and_devices(db, user.id, datetime.now(timezone.utc))
    await db.commit()
    await db.refresh(user)
    logger.info(
        "Compte %s par la plateforme : %s (par %s).", "réactivé" if active else "désactivé", user.id, actor_id
    )
    return user


async def delete_account(db: AsyncSession, actor_id: uuid.UUID, user_id: uuid.UUID, confirm_email: str) -> User:
    user, codes = await _target(db, actor_id, user_id)
    if "PARTNER_ADMIN" in codes:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=PARTNER_DETAIL)
    if confirm_email.strip().lower() != user.email.strip().lower():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=CONFIRM_DETAIL)

    now = datetime.now(timezone.utc)
    await _close_sessions_and_devices(db, user.id, now)
    await db.execute(delete(UserSession).where(UserSession.user_id == user.id))
    await db.execute(delete(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    await db.execute(delete(Notification).where(Notification.recipient_user_id == user.id))
    await db.execute(delete(TeacherAssignment).where(TeacherAssignment.user_id == user.id))
    # Le tuteur reste dans le dossier de l'élève (fiche de l'école), sans compte.
    await db.execute(update(Guardian).where(Guardian.user_id == user.id).values(user_id=None))
    await db.execute(delete(UserRole).where(UserRole.user_id == user.id))

    photo_path = user.photo_path  # migration 0036 : la photo d'identité est une donnée personnelle
    user.photo_path = None
    user.email = deleted_email(user.id)
    user.full_name = DELETED_ACCOUNT_NAME
    user.phone = None
    user.hashed_password = hash_password(secrets.token_urlsafe(48))
    user.is_active = False
    user.deleted_at = now
    user.deleted_by = actor_id
    await db.commit()
    await db.refresh(user)
    if photo_path:
        await delete_photo_file_best_effort(photo_path)
    logger.info("Compte supprimé par la plateforme : %s (par %s).", user.id, actor_id)
    return user
