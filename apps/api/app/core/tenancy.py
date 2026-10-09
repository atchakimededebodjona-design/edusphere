"""Contexte tenant appliqué à chaque requête authentifiée pour les policies RLS Postgres.

Trois variables de session (via set_config(..., is_local=true), valables pour la transaction
en cours uniquement — SET LOCAL ne supporte pas les paramètres liés, contrairement à la
fonction set_config()) :
- app.current_user_id   : id de l'utilisateur courant
- app.is_platform_wide  : 'true' si l'utilisateur détient au moins une UserRole dont le CODE de
                           rôle appartient à `PLATFORM_ROLE_CODES` (SUPER_ADMIN, PLATFORM_SUPPORT,
                           PLATFORM_OWNER — voir modules/rbac/models.py) — voit alors toutes les
                           organisations/écoles
- app.tenant_org_ids    : liste d'UUID d'organisations séparées par des virgules, dérivée des
                           rôles de l'utilisateur — délimite ce qu'il peut voir sinon

PR #17 — `is_platform_wide` est calculé à partir du code de rôle, JAMAIS de la simple nullité de
`user_roles.organization_id`. Avant ce correctif, toute UserRole globale (organization_id NULL)
rendait la session platform-wide, quel que soit le rôle : attribuer à un partenaire commercial
(PARTNER_ADMIN, externe à l'entreprise) une UserRole globale lui aurait silencieusement accordé un
bypass RLS complet sur les données de toutes les écoles. Désormais, la UserRole globale d'un
PARTNER_ADMIN produit `is_platform_wide = 'false'` ET un `tenant_org_ids` vide : par défaut, il ne
voit donc AUCUNE ligne via la policy générique `{table}_tenant_isolation` de chaque table tenant.
C'est intentionnel (défense en profondeur) : ses seules lectures légitimes passent par les
endpoints `/partner/*`, qui élèvent explicitement le contexte (`set_platform_wide_context`) pour
une lecture précise ET filtrent explicitement par la liste blanche d'ids dérivée de son propre
`partners.id` (voir modules/partners/service.py).

Le filtrage applicatif (dependencies de permissions) reste la protection primaire ; RLS est une
seconde ligne de défense qui s'applique même si une requête oublie un filtre `organization_id`.
"""

import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.rbac.models import PLATFORM_ROLE_CODES, Role, UserRole

_SET_CONFIG = text("SELECT set_config(:name, :value, true)")


async def apply_tenant_context(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(_SET_CONFIG, {"name": "app.current_user_id", "value": str(user_id)})

    # Jointure sur `roles` : la décision platform-wide repose sur le code du rôle (voir docstring
    # du module). `roles` n'a pas de RLS ; `user_roles` laisse toujours lire ses propres lignes
    # (policy `user_roles_tenant_isolation`, clause `user_id = app.current_user_id` posée ci-dessus).
    result = await db.execute(
        select(UserRole.organization_id, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user_id)
    )
    rows = result.all()

    is_platform_wide = any(code in PLATFORM_ROLE_CODES for _, code in rows)
    tenant_org_ids = {str(org_id) for org_id, _ in rows if org_id is not None}

    await db.execute(
        _SET_CONFIG, {"name": "app.is_platform_wide", "value": "true" if is_platform_wide else "false"}
    )
    await db.execute(_SET_CONFIG, {"name": "app.tenant_org_ids", "value": ",".join(tenant_org_ids)})


async def set_platform_wide_context(db: AsyncSession) -> None:
    """À utiliser uniquement pour des opérations système sans utilisateur authentifié
    (ex. création d'un nouveau tenant lors de l'inscription — il n'existe pas encore de
    contexte tenant à ce moment, et créer un tenant n'expose aucune donnée d'un tenant existant).

    PR #17 — également utilisé par les lectures `/partner/*` : l'élévation rend seulement la
    lecture POSSIBLE, l'autorisation réelle reste toujours la clause WHERE explicite (liste
    blanche d'ids dérivée côté serveur du compte appelant, jamais d'un id fourni par le client).
    """
    await db.execute(_SET_CONFIG, {"name": "app.is_platform_wide", "value": "true"})
