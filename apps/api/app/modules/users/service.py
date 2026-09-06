import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from fastapi import HTTPException, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.email import send_email_best_effort
from app.core.security import generate_opaque_token, hash_opaque_token, hash_password
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.modules.auth.models import PasswordResetToken
from app.modules.rbac.models import PLATFORM_ROLE_CODES, Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User
from app.modules.users.schemas import UserCreateRequest, UserUpdateRequest

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
    db: AsyncSession, school: School, payload: UserCreateRequest, current_user_id: uuid.UUID
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
        # Le nouveau compte n'est pas l'appelant courant (l'admin) — bypass RLS explicite pour cet
        # INSERT, même motif que auth/service.py::request_password_reset (RETURNING implicite de
        # l'ORM). Contexte restauré juste après (avant les lectures user_roles qui suivent, qui
        # doivent rester filtrées par le tenant réel de l'admin — voir Phase 22 migration 0012).
        await set_platform_wide_context(db)
        db.add(
            PasswordResetToken(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hash_opaque_token(raw_token),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=PASSWORD_RESET_TOKEN_EXPIRE_MINUTES),
            )
        )
        await db.flush()
        await apply_tenant_context(db, current_user_id)
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


async def update_user_in_school(
    db: AsyncSession, school: School, target_user_id: uuid.UUID, payload: UserUpdateRequest, current_user_id: uuid.UUID
) -> tuple[User, list[RoleData]]:
    """Phase 22 — édite le rôle et/ou le statut actif d'un utilisateur, scopé à une école précise.

    Sécurité : (1) un utilisateur ne peut jamais se modifier lui-même via cet endpoint (empêche
    toute auto-élévation de privilège ou auto-désactivation accidentelle) ; (2) la cible doit
    déjà avoir une UserRole scopée EXACTEMENT à cette école (pas un rôle organisation plus large)
    — sinon 404, même sémantique que `_get_school_or_404`/`ensure_permission` : on ne révèle ni
    ne modifie une ressource hors du scope vérifié par l'appelant ; (3) impossible d'attribuer un
    rôle plateforme, même règle que `create_or_attach_user`. `role_code` remplace l'intégralité
    des UserRole de cet utilisateur scopées à cette école par une seule nouvelle ligne — même
    modèle mental qu'à la création (un seul rôle par utilisateur par école dans ce produit)."""
    if target_user_id == current_user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot modify your own account")
    if payload.role_code is None and payload.is_active is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to update")

    user = await db.get(User, target_user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role_rows_result = await db.execute(
        select(UserRole).where(UserRole.user_id == target_user_id, UserRole.school_id == school.id)
    )
    role_rows = list(role_rows_result.scalars().all())
    if not role_rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User has no role in this school")

    if payload.role_code is not None:
        if payload.role_code in PLATFORM_ROLE_CODES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot assign a platform-wide role here")
        role_result = await db.execute(select(Role).where(Role.code == payload.role_code))
        role = role_result.scalar_one_or_none()
        if role is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unknown role code")
        for row in role_rows:
            await db.delete(row)
        await db.flush()
        db.add(
            UserRole(
                id=uuid.uuid4(),
                user_id=target_user_id,
                role_id=role.id,
                organization_id=school.organization_id,
                school_id=school.id,
            )
        )

    if payload.is_active is not None:
        user.is_active = payload.is_active

    await db.flush()
    await db.refresh(user)

    roles_result = await db.execute(
        select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == target_user_id)
    )
    all_roles = [RoleData(role_code=code, organization_id=ur.organization_id, school_id=ur.school_id) for ur, code in roles_result.all()]

    await db.commit()
    return user, all_roles


async def list_users_for_school(db: AsyncSession, school: School) -> list[tuple[User, list[RoleData]]]:
    """Phase 24 — corrige une fuite confirmée en Discovery : la condition précédente
    (`school_id == school.id OR organization_id == school.organization_id`) incluait à tort tout
    utilisateur ayant un rôle scopé à une AUTRE école de la même organisation (`school_id` d'une
    école B, `organization_id` de l'organisation partagée) — un admin de l'école A voyait alors le
    personnel de l'école B dans sa propre liste. Aligné sur le motif déjà correct et testé de
    `notifications/service.py::resolve_school_member_user_ids` : un rôle organisation ne compte
    que s'il n'est PAS scopé à une école précise (`school_id IS NULL`, ex. le SCHOOL_ADMIN créé à
    l'inscription — `auth/service.py::register`)."""
    result = await db.execute(
        select(UserRole, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .where(
            or_(
                UserRole.school_id == school.id,
                and_(UserRole.organization_id == school.organization_id, UserRole.school_id.is_(None)),
            )
        )
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
