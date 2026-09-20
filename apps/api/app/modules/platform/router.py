from fastapi import APIRouter, Depends

from app.core.permissions import DbSession, require_platform_admin
from app.modules.platform import service
from app.modules.platform.schemas import PlatformDashboardOut

router = APIRouter()


@router.get(
    "/platform/dashboard",
    response_model=PlatformDashboardOut,
    dependencies=[Depends(require_platform_admin)],
)
async def get_platform_dashboard(db: DbSession) -> PlatformDashboardOut:
    summary = await service.get_platform_dashboard_summary(db)
    return PlatformDashboardOut(**summary)
