"""Commissions des partenaires — endpoints (migration 0031).

Plateforme (`platform.commissions.read|manage`, SUPER_ADMIN et PLATFORM_OWNER) : liste et totaux,
versement manuel, annulation, taux de chaque partenaire. Partenaire (`partner.commissions.read`) :
ses propres commissions uniquement, le partenaire étant TOUJOURS dérivé du compte authentifié
(partners/service.py::get_own_partner). Les écoles n'y ont jamais accès.
"""

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.permissions import DbSession, require_permission
from app.modules.commissions import service
from app.modules.commissions.schemas import (
    CancelCommissionInput,
    CommissionRateInput,
    CommissionsPage,
    CommissionStatus,
    MarkPaidInput,
    PartnerCommissionsOut,
)
from app.modules.partners import service as partners_service
from app.modules.subscriptions.service import utc_now
from app.modules.users.models import User

router = APIRouter()

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
PlatformReader = Annotated[User, Depends(require_permission("platform.commissions.read"))]
PlatformManager = Annotated[User, Depends(require_permission("platform.commissions.manage"))]
PartnerReader = Annotated[User, Depends(require_permission("partner.commissions.read"))]


@router.get("/platform/partner-commissions", response_model=CommissionsPage)
async def list_partner_commissions(
    db: DbSession,
    _: PlatformReader,
    page: Page = 1,
    page_size: PageSize = 20,
    status_filter: Annotated[CommissionStatus | None, Query(alias="status")] = None,
    partner_id: uuid.UUID | None = None,
) -> CommissionsPage:
    items, total, totals = await service.list_commissions(db, page, page_size, status_filter, partner_id)
    return CommissionsPage(
        items=items,
        page=page,
        page_size=page_size,
        total=total,
        total_pages=(total + page_size - 1) // page_size,
        totals=totals,
    )


@router.post("/platform/partner-commissions/mark-paid", response_model=list[uuid.UUID])
async def mark_partner_commissions_paid(payload: MarkPaidInput, db: DbSession, current_user: PlatformManager) -> list[uuid.UUID]:
    return await service.mark_paid(db, current_user, payload, utc_now())


@router.post("/platform/partner-commissions/{commission_id}/cancel", response_model=uuid.UUID)
async def cancel_partner_commission(
    commission_id: uuid.UUID, payload: CancelCommissionInput, db: DbSession, current_user: PlatformManager
) -> uuid.UUID:
    return await service.cancel(db, current_user, commission_id, payload.reason, utc_now())


@router.put("/platform/partners/{partner_id}/commission-rate", response_model=Decimal)
async def set_partner_commission_rate(
    partner_id: uuid.UUID, payload: CommissionRateInput, db: DbSession, current_user: PlatformManager
) -> Decimal:
    partner = await service.set_partner_rate(db, current_user, partner_id, payload.rate, utc_now())
    return partner.commission_rate


@router.get("/partner/commissions", response_model=PartnerCommissionsOut)
async def get_own_partner_commissions(db: DbSession, current_user: PartnerReader) -> PartnerCommissionsOut:
    partner = await partners_service.get_own_partner(db, current_user.id)
    items, totals = await service.list_partner_commissions(db, partner)
    return PartnerCommissionsOut(commission_rate=partner.commission_rate, totals=totals, items=items)
