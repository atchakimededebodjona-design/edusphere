from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.core.permissions import DbSession, require_permission, require_platform_admin
from app.modules.auth.schemas import UserOut
from app.modules.organizations.schemas import OrganizationOut
from app.modules.partners.models import Partner
from app.modules.platform import service
from app.modules.platform.schemas import (
    PlatformAccountOut,
    PlatformAccountsPage,
    PlatformDashboardOut,
    PlatformOrganizationCreate,
    PlatformOrganizationCreated,
    PlatformOrganizationListItem,
    PlatformOrganizationsPage,
    PlatformPartnerCreate,
    PlatformPartnerCreated,
    PlatformPartnerOut,
    PlatformPartnersPage,
    PlatformSchoolListItem,
    PlatformSchoolsPage,
)
from app.modules.schools.schemas import SchoolOut
from app.modules.users.models import User

router = APIRouter()

PlatformAdmin = Annotated[User, Depends(require_platform_admin)]
Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]


def _page_meta(page: int, page_size: int, total: int) -> dict[str, int]:
    return {"page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


@router.get(
    "/platform/dashboard",
    response_model=PlatformDashboardOut,
    dependencies=[Depends(require_platform_admin)],
)
async def get_platform_dashboard(db: DbSession) -> PlatformDashboardOut:
    summary = await service.get_platform_dashboard_summary(db)
    return PlatformDashboardOut(**summary)


# Seul point d'entrée de création d'une organisation (remplace l'ancien POST /auth/register public).
# Contrôle d'autorisation côté backend via require_platform_admin : 401 sans token, 403 pour tout
# compte non plateforme (School Admin, Teacher, Parent...), 201 pour un platform admin.
# PR #17 — trace aussi la source d'acquisition (partner_school_enrollments, source "PLATFORM_OWNER").
@router.post(
    "/platform/organizations",
    response_model=PlatformOrganizationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_platform_organization(
    payload: PlatformOrganizationCreate, db: DbSession, current_user: PlatformAdmin
) -> PlatformOrganizationCreated:
    organization, school, admin = await service.create_organization_with_admin(db, payload, current_user.id)
    return PlatformOrganizationCreated(
        organization=OrganizationOut.model_validate(organization),
        school=SchoolOut.model_validate(school),
        admin=UserOut.model_validate(admin),
    )


# --- PR #17 — endpoints plateforme granulaires (RBAC d'abord, jamais require_platform_admin) ------
# Métadonnées uniquement. Chaque route exige un code `platform.*` précis, détenu seulement par
# SUPER_ADMIN/PLATFORM_OWNER (rbac/seed.py::PR17_PLATFORM_ROLE_PERMISSIONS) : 403 pour tout
# SCHOOL_ADMIN/DIRECTOR/TEACHER/PARTNER_ADMIN, indépendamment de ce que le frontend affiche.


@router.get(
    "/platform/organizations",
    response_model=PlatformOrganizationsPage,
    dependencies=[Depends(require_permission("platform.organizations.read"))],
)
async def list_platform_organizations(db: DbSession, page: Page = 1, page_size: PageSize = 20) -> PlatformOrganizationsPage:
    organizations, total = await service.list_organizations(db, page, page_size)
    return PlatformOrganizationsPage(
        items=[PlatformOrganizationListItem.model_validate(org) for org in organizations],
        **_page_meta(page, page_size, total),
    )


@router.get(
    "/platform/schools",
    response_model=PlatformSchoolsPage,
    dependencies=[Depends(require_permission("platform.schools.read"))],
)
async def list_platform_schools(db: DbSession, page: Page = 1, page_size: PageSize = 20) -> PlatformSchoolsPage:
    rows, total = await service.list_schools(db, page, page_size)
    return PlatformSchoolsPage(
        items=[
            PlatformSchoolListItem(
                id=school.id,
                name=school.name,
                organization_id=school.organization_id,
                slug=school.slug,
                created_at=school.created_at,
                acquisition_source=source,
                student_count=student_count,
                active_student_count=active_student_count,
            )
            for school, source, student_count, active_student_count in rows
        ],
        **_page_meta(page, page_size, total),
    )


@router.get(
    "/platform/accounts",
    response_model=PlatformAccountsPage,
    dependencies=[Depends(require_permission("platform.accounts.read"))],
)
async def list_platform_accounts(db: DbSession, page: Page = 1, page_size: PageSize = 20) -> PlatformAccountsPage:
    rows, total = await service.list_accounts(db, page, page_size)
    return PlatformAccountsPage(
        items=[
            PlatformAccountOut(
                id=user.id,
                email=user.email,
                full_name=user.full_name,
                is_active=user.is_active,
                created_at=user.created_at,
                role_codes=role_codes,
            )
            for user, role_codes in rows
        ],
        **_page_meta(page, page_size, total),
    )


def _partner_out(partner: Partner, enrollment_count: int) -> PlatformPartnerOut:
    return PlatformPartnerOut(
        id=partner.id,
        user_id=partner.user_id,
        display_name=partner.display_name,
        phone=partner.phone,
        email=partner.email,
        status=partner.status,
        created_at=partner.created_at,
        enrollment_count=enrollment_count,
    )


@router.get(
    "/platform/partners",
    response_model=PlatformPartnersPage,
    dependencies=[Depends(require_permission("platform.partners.read"))],
)
async def list_platform_partners(db: DbSession, page: Page = 1, page_size: PageSize = 20) -> PlatformPartnersPage:
    rows, total = await service.list_partners(db, page, page_size)
    return PlatformPartnersPage(
        items=[_partner_out(partner, count) for partner, count in rows], **_page_meta(page, page_size, total)
    )


@router.post(
    "/platform/partners",
    response_model=PlatformPartnerCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("platform.partners.manage"))],
)
async def create_platform_partner(payload: PlatformPartnerCreate, db: DbSession) -> PlatformPartnerCreated:
    partner, _user, dev_reset_token = await service.create_partner(db, payload)
    return PlatformPartnerCreated(partner=_partner_out(partner, 0), dev_reset_token=dev_reset_token)
