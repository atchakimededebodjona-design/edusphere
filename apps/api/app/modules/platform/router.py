from fastapi import APIRouter, Depends, status

from app.core.permissions import DbSession, require_platform_admin
from app.modules.auth.schemas import UserOut
from app.modules.organizations.schemas import OrganizationOut
from app.modules.platform import service
from app.modules.platform.schemas import (
    PlatformDashboardOut,
    PlatformOrganizationCreate,
    PlatformOrganizationCreated,
)
from app.modules.schools.schemas import SchoolOut

router = APIRouter()


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
@router.post(
    "/platform/organizations",
    response_model=PlatformOrganizationCreated,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_platform_admin)],
)
async def create_platform_organization(
    payload: PlatformOrganizationCreate, db: DbSession
) -> PlatformOrganizationCreated:
    organization, school, admin = await service.create_organization_with_admin(db, payload)
    return PlatformOrganizationCreated(
        organization=OrganizationOut.model_validate(organization),
        school=SchoolOut.model_validate(school),
        admin=UserOut.model_validate(admin),
    )
