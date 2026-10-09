"""PR #17 — promotion EXPLICITE d'un compte existant en PLATFORM_OWNER (procédure opérateur).

Pourquoi : avant la PR #17, le seul compte « plateforme » possible était SUPER_ADMIN
(`is_platform_admin=True`, UserRole globale), créé hors bande. SUPER_ADMIN détient TOUTES les
permissions du catalogue, y compris students.*/grades.*/attendance.*/report_cards.*/fees.*/
payments.* — et il est platform-wide côté RLS : un propriétaire de plateforme resté SUPER_ADMIN
garde donc un accès complet aux données scolaires, quoi qu'apporte PLATFORM_OWNER.

Une migration Alembic ne peut pas faire cette conversion : elle devrait désigner « le » compte
propriétaire, donc coder en dur un email (interdit). Cette fonction est appelée par
`app/jobs/promote_platform_owner.py`, l'email étant fourni à l'exécution par l'opérateur.

Effet (`apply=True`), dans UNE transaction :
- ajoute une UserRole PLATFORM_OWNER globale (organization_id ET school_id NULL), si absente ;
- supprime les UserRole globales SUPER_ADMIN et PLATFORM_SUPPORT de CE compte (sources des
  permissions scolaires héritées) — le rôle SUPER_ADMIN lui-même reste dans le catalogue pour ses
  autres usages (comptes techniques, suite de tests) ;
- garantit `is_platform_admin=True` (accès aux 2 endpoints historiques /platform).

Refus (aucune modification) : compte inconnu ou inactif, compte PARTNER_ADMIN, ou compte ayant
une quelconque UserRole scopée organisation/école — le propriétaire ne doit jamais être rattaché
à une école ; ces rattachements doivent être retirés explicitement avant, jamais silencieusement.

`apply=False` (défaut côté job) : simulation, rien n'est écrit (rollback).
Les permissions étant recalculées à chaque requête depuis la base, l'effet est immédiat.
"""

import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.modules.rbac.models import Role, UserRole
from app.modules.users.models import User

# Rôles globaux hérités retirés au compte promu : ce sont eux qui portent les permissions scolaires.
LEGACY_GLOBAL_ROLE_CODES = ("SUPER_ADMIN", "PLATFORM_SUPPORT")


class PromotionRefused(Exception):
    """Promotion impossible — aucune modification effectuée."""


@dataclass
class PromotionReport:
    user_id: uuid.UUID
    roles_before: list[str]
    roles_after: list[str]
    removed_role_codes: list[str] = field(default_factory=list)
    added_platform_owner: bool = False
    set_platform_admin_flag: bool = False
    applied: bool = False


async def _role_rows(db: AsyncSession, user_id: uuid.UUID) -> list[tuple[UserRole, str]]:
    result = await db.execute(
        select(UserRole, Role.code).join(Role, Role.id == UserRole.role_id).where(UserRole.user_id == user_id)
    )
    return [(user_role, code) for user_role, code in result.all()]


async def promote_to_platform_owner(db: AsyncSession, email: str, *, apply: bool) -> PromotionReport:
    await set_platform_wide_context(db)
    try:
        user = (await db.execute(select(User).where(User.email == email.strip().lower()))).scalar_one_or_none()
        if user is None:
            raise PromotionRefused("Aucun compte avec cet email.")
        if not user.is_active:
            raise PromotionRefused("Compte inactif : réactivation explicite requise avant promotion.")

        rows = await _role_rows(db, user.id)
        codes_before = sorted(code for _, code in rows)
        if "PARTNER_ADMIN" in codes_before:
            raise PromotionRefused("Compte partenaire : un partenaire ne peut pas devenir propriétaire.")
        scoped = sorted(
            f"{code} (organization_id={ur.organization_id}, school_id={ur.school_id})"
            for ur, code in rows
            if ur.organization_id is not None or ur.school_id is not None
        )
        if scoped:
            raise PromotionRefused(
                "Compte rattaché à une organisation/école — retirer explicitement ces rôles d'abord : "
                + "; ".join(scoped)
            )

        report = PromotionReport(user_id=user.id, roles_before=codes_before, roles_after=[])
        report.removed_role_codes = sorted(code for _, code in rows if code in LEGACY_GLOBAL_ROLE_CODES)
        if report.removed_role_codes:
            await db.execute(
                delete(UserRole).where(
                    UserRole.id.in_([ur.id for ur, code in rows if code in LEGACY_GLOBAL_ROLE_CODES])
                )
            )

        if "PLATFORM_OWNER" not in codes_before:
            owner_role = (await db.execute(select(Role).where(Role.code == "PLATFORM_OWNER"))).scalar_one_or_none()
            if owner_role is None:
                raise PromotionRefused("Rôle PLATFORM_OWNER absent — migration 0023 non appliquée.")
            db.add(
                UserRole(id=uuid.uuid4(), user_id=user.id, role_id=owner_role.id, organization_id=None, school_id=None)
            )
            report.added_platform_owner = True

        if not user.is_platform_admin:
            user.is_platform_admin = True
            report.set_platform_admin_flag = True

        await db.flush()
        report.roles_after = sorted(code for _, code in await _role_rows(db, user.id))
        if apply:
            await db.commit()
            report.applied = True
        else:
            await db.rollback()
        return report
    except Exception:
        await db.rollback()
        raise
