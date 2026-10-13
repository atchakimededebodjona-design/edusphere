from typing import NamedTuple
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.modules.rbac.models import (
    NON_SCHOOL_ROLE_CODES,
    REUSABLE_ADMIN_ROLE_CODES,
    Role,
    UserRole,
)


class AccountRoleAssignment(NamedTuple):
    """Rôle réellement détenu par un compte, avec sa portée tenant."""

    role_code: str
    organization_id: UUID | None
    school_id: UUID | None


def normalize_email(email: str) -> str:
    """Normalise un email pour les recherches et verrous transactionnels."""
    return email.strip().lower()


async def lock_account_email(
    db: AsyncSession,
    email: str,
    *,
    namespace: str = "school-admin-email",
) -> str:
    """Sérialise les opérations concurrentes visant le même compte par email.

    Le verrou est transactionnel et doit donc être appelé dans la transaction
    qui porte l'opération métier.
    """
    normalized_email = normalize_email(email)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"{namespace}:{normalized_email}"},
    )
    return normalized_email


async def load_account_footprint(
    db: AsyncSession,
    user_id: UUID,
    current_user_id: UUID | None = None,
) -> list[AccountRoleAssignment]:
    """Charge TOUS les rôles d'un compte, toutes organisations confondues.

    La lecture est effectuée temporairement en contexte platform-wide puis le
    contexte du demandeur est restauré immédiatement.

    Cette fonction ne modifie jamais les rôles et ne dépend d'aucun module
    métier users/platform.
    """
    await set_platform_wide_context(db)
    try:
        result = await db.execute(
            select(
                Role.code,
                UserRole.organization_id,
                UserRole.school_id,
            )
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        return [
            AccountRoleAssignment(code, organization_id, school_id)
            for code, organization_id, school_id in result.all()
        ]
    finally:
        if current_user_id is not None:
            await apply_tenant_context(db, current_user_id)


def is_reusable_school_admin(
    *,
    user_is_active: bool,
    user_is_platform_admin: bool,
    footprint: list[AccountRoleAssignment],
    organization_id: UUID,
) -> bool:
    """Détermine si un compte existant peut être réutilisé comme SCHOOL_ADMIN.

    Règle centralisée :
    - compte actif ;
    - pas de compte plateforme ;
    - aucun rôle non-scolaire/partenaire ;
    - détient déjà SCHOOL_ADMIN ou DIRECTOR dans l'organisation cible.
    """
    if not user_is_active or user_is_platform_admin:
        return False

    if any(entry.role_code in NON_SCHOOL_ROLE_CODES for entry in footprint):
        return False

    return any(
        entry.organization_id == organization_id
        and entry.role_code in REUSABLE_ADMIN_ROLE_CODES
        for entry in footprint
    )


def has_organization_wide_school_admin(
    *,
    footprint: list[AccountRoleAssignment],
    organization_id: UUID,
) -> bool:
    """Indique si le compte possède déjà SCHOOL_ADMIN org-wide dans l'organisation."""
    return any(
        entry.role_code == "SCHOOL_ADMIN"
        and entry.organization_id == organization_id
        and entry.school_id is None
        for entry in footprint
    )
