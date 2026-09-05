import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email_best_effort
from app.core.security import generate_opaque_token, hash_opaque_token, hash_password
from app.modules.auth.models import PasswordResetToken
from app.modules.rbac.models import PLATFORM_ROLE_CODES, Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User
from app.modules.users.schemas import UserCreateRequest

# Même durée que auth/service.py::request_password_reset — pas de dépendance croisée pour une
# seule constante (users ne dépend pas de auth, c'est l'inverse).
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES = 30


class RoleData(NamedTuple):
    """UserRole n'a pas de relationship() ORM vers Role (cf. auth/service.py::register()) —
    porte le code déjà résolu par jointure plutôt que l'objet UserRole brut."""

    role_code: str
    organization_id: uuid.UUID | None
    school_id: uuid.UUID | None


async def create_or_attach_user(
    db: AsyncSession, school: School, payload: UserCreateRequest
) -> tuple[User, list[RoleData], str | None]:
    """Crée un utilisateur (avec un token de reset mot de passe, cf. schemas.py) ou, si l'email
    existe déjà, attache seulement le nouveau rôle au compte existant (ex. enseignant déjà
    inscrit dans une autre école) — jamais de doublon de compte sur un email."""
    if payload.role_code in PLATFORM_ROLE_CODES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot assign a platform-wide role here")

    role_result = await db.execute(select(Role).where(Role.code == payload.role_code))
    role = role_result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role code")

    existing_result = await db.execute(select(User).where(User.email == payload.email.lower()))
    user = existing_result.scalar_one_or_none()
    dev_reset_token: str | None = None

    if user is None:
        user = User(
            id=uuid.uuid4(),
            email=payload.email.lower(),
            full_name=payload.full_name,
            phone=payload.phone,
            hashed_password=hash_password(generate_opaque_token()),
        )
        db.add(user)
        await db.flush()

        raw_token = generate_opaque_token()
        db.add(
            PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hash_opaque_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            )
        )
        await send_email_best_effort(
            user.email,
            "Bienvenue sur EduSphere — activez votre compte",
            f"Un compte a été créé pour vous sur EduSphere. Pour définir votre mot de passe, "
            f"ouvrez ce lien (valable {PASSWORD_RESET_TOKEN_EXPIRE_MINUTES} minutes) :\n"
            f"{settings.public_web_base_url}/reset-password?token={raw_token}",
        )
        # dev_reset_token même règle que auth/service.py::request_password_reset (dev_token) :
        # exposé hors production pour les tests/le développement, un email est envoyé dans tous
        # les cas (voir app/core/email.py — LocalEmailProvider en dev, SMTP en production).
        dev_reset_token = None if settings.environment == "production" else raw_token

    duplicate_result = await db.execute(
        select(UserRole).where(
            UserRole.user_id == user.id,
            UserRole.role_id == role.id,
            UserRole.organization_id == school.organization_id,
            UserRole.school_id == school.id,
        )
    )
    if duplicate_result.scalar_one_or_none() is None:
        db.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=user.id,
                role_id=role.id,
                organization_id=school.organization_id,
                school_id=school.id,
            )
        )

    await db.flush()
    await db.refresh(user)

    # UserRole n'a pas de relationship() ORM vers Role (cf. commentaire dans auth/service.py
    # register()) — jointure explicite pour récupérer le code, même pattern que
    # auth/router.py::me().
    roles_result = await db.execute(
        select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == user.id)
    )
    all_roles = [RoleData(role_code=code, organization_id=ur.organization_id, school_id=ur.school_id) for ur, code in roles_result.all()]

    await db.commit()
    return user, all_roles, dev_reset_token


async def list_users_for_school(db: AsyncSession, school: School) -> list[tuple[User, list[RoleData]]]:
    result = await db.execute(
        select(UserRole, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .where((UserRole.school_id == school.id) | (UserRole.organization_id == school.organization_id))
    )
    rows = result.all()
    user_ids = {ur.user_id for ur, _ in rows}
    if not user_ids:
        return []

    users_result = await db.execute(select(User).where(User.id.in_(user_ids)).order_by(User.full_name))
    users = list(users_result.scalars().all())

    roles_by_user: dict[uuid.UUID, list[RoleData]] = {}
    for ur, code in rows:
        roles_by_user.setdefault(ur.user_id, []).append(
            RoleData(role_code=code, organization_id=ur.organization_id, school_id=ur.school_id)
        )

    return [(user, roles_by_user.get(user.id, [])) for user in users]
