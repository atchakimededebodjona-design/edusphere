"""Contexte tenant appliqué à chaque requête authentifiée pour les policies RLS Postgres.

Trois variables de session (via set_config(..., is_local=true), valables pour la transaction
en cours uniquement — SET LOCAL ne supporte pas les paramètres liés, contrairement à la
fonction set_config()) :
- app.current_user_id   : id de l'utilisateur courant
- app.is_platform_wide  : 'true' si l'utilisateur a un rôle plateforme (organization_id IS NULL
                           dans user_roles) — voit toutes les organisations/écoles
- app.tenant_org_ids    : liste d'UUID d'organisations séparées par des virgules, dérivée des
                           rôles de l'utilisateur — délimite ce qu'il peut voir sinon

Le filtrage applicatif (dependencies de permissions) reste la protection primaire ; RLS est une
seconde ligne de défense qui s'applique même si une requête oublie un filtre `organization_id`.
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rbac.models import UserRole

_SET_CONFIG = text("SELECT set_config(:name, :value, true)")


async def apply_tenant_context(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(_SET_CONFIG, {"name": "app.current_user_id", "value": str(user_id)})

    result = await db.execute(select(UserRole.organization_id).where(UserRole.user_id == user_id))
    organization_ids = [row[0] for row in result.all()]

    is_platform_wide = any(org_id is None for org_id in organization_ids)
    tenant_org_ids = {str(org_id) for org_id in organization_ids if org_id is not None}

    await db.execute(
        _SET_CONFIG, {"name": "app.is_platform_wide", "value": "true" if is_platform_wide else "false"}
    )
    await db.execute(_SET_CONFIG, {"name": "app.tenant_org_ids", "value": ",".join(tenant_org_ids)})


async def set_platform_wide_context(db: AsyncSession) -> None:
    """À utiliser uniquement pour des opérations système sans utilisateur authentifié
    (ex. création d'un nouveau tenant lors de l'inscription — il n'existe pas encore de
    contexte tenant à ce moment, et créer un tenant n'expose aucune donnée d'un tenant existant).
    """
    await db.execute(_SET_CONFIG, {"name": "app.is_platform_wide", "value": "true"})
