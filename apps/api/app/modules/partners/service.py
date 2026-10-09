"""Lectures/écritures côté partenaire commercial (PR #17).

Modèle de sécurité (voir core/tenancy.py) : un PARTNER_ADMIN n'est JAMAIS platform-wide et son
`tenant_org_ids` est toujours vide — RLS ne lui montre donc aucune ligne d'aucune table tenant par
défaut. Chaque lecture de ce module suit strictement le même schéma :

1. résoudre le `Partner` de l'utilisateur authentifié (`Partner.user_id == current_user.id`,
   jamais un `partner_id` fourni par le client) ;
2. dériver la liste blanche des `school_id`/`organization_id` depuis
   `partner_school_enrollments.partner_id == <ce partenaire>` ;
3. élever explicitement le contexte (`set_platform_wide_context`) pour rendre la lecture
   possible, en filtrant TOUJOURS explicitement par cette liste blanche — l'élévation ne fait que
   rendre la lecture possible, l'autorisation réelle est la clause WHERE.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.modules.organizations.models import Organization
from app.modules.partners.models import (
    ACQUISITION_SOURCE_PARTNER,
    PARTNER_STATUS_ACTIVE,
    Partner,
    PartnerSchoolEnrollment,
)
from app.modules.platform import service as platform_service
from app.modules.platform.schemas import PlatformOrganizationCreate
from app.modules.rbac.models import NON_SCHOOL_ROLE_CODES, Role, UserRole
from app.modules.schools.models import School
from app.modules.users.models import User


async def get_own_partner(db: AsyncSession, current_user_id: uuid.UUID) -> Partner:
    """Partenaire du compte authentifié. 404 si ce compte n'a pas de fiche partenaire (ex. un
    SUPER_ADMIN, qui détient les permissions `partner.*` par convention du catalogue mais n'est
    rattaché à aucun partenaire) ; 403 si la fiche est suspendue."""
    await set_platform_wide_context(db)
    result = await db.execute(select(Partner).where(Partner.user_id == current_user_id))
    partner = result.scalar_one_or_none()
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No partner profile for this account")
    if partner.status != PARTNER_STATUS_ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Partner account is suspended")
    return partner


async def get_partner_dashboard(db: AsyncSession, partner: Partner) -> dict[str, int]:
    await set_platform_wide_context(db)
    result = await db.execute(
        select(
            func.count(PartnerSchoolEnrollment.school_id),
            func.count(func.distinct(PartnerSchoolEnrollment.organization_id)),
        ).where(PartnerSchoolEnrollment.partner_id == partner.id)
    )
    school_count, organization_count = result.one()
    return {"school_count": int(school_count), "organization_count": int(organization_count)}


async def list_partner_schools(
    db: AsyncSession, partner: Partner
) -> list[tuple[PartnerSchoolEnrollment, School, Organization]]:
    await set_platform_wide_context(db)
    result = await db.execute(
        select(PartnerSchoolEnrollment, School, Organization)
        .join(School, School.id == PartnerSchoolEnrollment.school_id)
        .join(Organization, Organization.id == PartnerSchoolEnrollment.organization_id)
        .where(PartnerSchoolEnrollment.partner_id == partner.id)
        .order_by(PartnerSchoolEnrollment.enrolled_at.desc())
    )
    return [(enrollment, school, organization) for enrollment, school, organization in result.all()]


async def enroll_school(
    db: AsyncSession, partner: Partner, payload: PlatformOrganizationCreate, current_user_id: uuid.UUID
) -> tuple[Organization, School, User]:
    """Inscription via ce partenaire : réutilise EXACTEMENT la logique plateforme
    (platform/service.py::create_organization_school_admin), avec `partner_id` dérivé côté
    serveur et la source "PARTNER" (donc `commission_eligible=True`)."""
    return await platform_service.create_organization_school_admin(
        db,
        payload,
        enrolled_by_user_id=current_user_id,
        partner_id=partner.id,
        acquisition_source=ACQUISITION_SOURCE_PARTNER,
    )


async def list_partner_accounts(db: AsyncSession, partner: Partner) -> list[tuple[User, list[str]]]:
    """Comptes ayant une UserRole scopée à l'une des écoles inscrites par CE partenaire — ou
    org-wide (`school_id` NULL) sur l'organisation de l'une de ces écoles (cas du SCHOOL_ADMIN
    créé à l'inscription, dont le rôle est scopé organisation). Jamais un compte détenant un rôle
    non scolaire (PLATFORM_OWNER/PARTNER_ADMIN/SUPER_ADMIN/PLATFORM_SUPPORT, exclus
    explicitement), jamais un compte des écoles d'un autre partenaire ou inscrites directement
    par la plateforme.

    Les rôles affichés sont restreints à ces mêmes écoles/organisations : un compte rattaché
    aussi à une école hors périmètre ne révèle jamais ce rattachement ici."""
    await set_platform_wide_context(db)
    whitelist = await db.execute(
        select(PartnerSchoolEnrollment.school_id, PartnerSchoolEnrollment.organization_id).where(
            PartnerSchoolEnrollment.partner_id == partner.id
        )
    )
    pairs = whitelist.all()
    if not pairs:
        return []
    school_ids = {school_id for school_id, _ in pairs}
    organization_ids = {organization_id for _, organization_id in pairs}

    # Une organisation inscrite par ce partenaire lui appartient entièrement (création atomique
    # organisation + école), d'où la prise en compte des rôles org-wide de ces organisations.
    in_scope = (UserRole.school_id.in_(list(school_ids))) | (
        UserRole.organization_id.in_(list(organization_ids)) & UserRole.school_id.is_(None)
    )
    roles_result = await db.execute(
        select(UserRole.user_id, Role.code)
        .join(Role, Role.id == UserRole.role_id)
        .where(in_scope, Role.code.not_in(sorted(NON_SCHOOL_ROLE_CODES)))
    )
    codes: dict[uuid.UUID, set[str]] = {}
    for user_id, code in roles_result.all():
        codes.setdefault(user_id, set()).add(code)
    if not codes:
        return []

    # Exclusion défensive supplémentaire : un compte détenant par ailleurs un rôle non scolaire
    # (plateforme ou partenaire), quelle que soit sa portée, n'apparaît jamais dans cette liste.
    non_school_result = await db.execute(
        select(UserRole.user_id)
        .join(Role, Role.id == UserRole.role_id)
        .where(UserRole.user_id.in_(list(codes)), Role.code.in_(sorted(NON_SCHOOL_ROLE_CODES)))
    )
    excluded = {row[0] for row in non_school_result.all()}

    users_result = await db.execute(select(User).where(User.id.in_(list(set(codes) - excluded))).order_by(User.full_name))
    return [(user, sorted(codes[user.id])) for user in users_result.scalars().all()]
