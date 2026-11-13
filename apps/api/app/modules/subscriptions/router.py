"""Abonnements des écoles (Phase 29, lot A) — endpoints.

Côté école (`/school-subscription*`) : même convention que cashier/router.py — l'école est chargée
sous le contexte RLS de l'appelant (404 pour une autre organisation), puis la permission est
vérifiée pour CETTE école (`ensure_permission`, règle de portée unique : 403 pour une autre école
de la même organisation). Le client n'envoie jamais de montant : uniquement la durée.

Côté plateforme (`/platform/subscription*`) : permissions `platform.subscriptions.read|manage`,
détenues uniquement par SUPER_ADMIN et PLATFORM_OWNER (rbac/seed.py) — 403 pour tout autre compte,
indépendamment de ce que le frontend affiche.

Pas de paiement en ligne dans ce lot (PayGate = lot B) : le paiement est enregistré manuellement
par la plateforme.
"""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.core.permissions import CurrentUser, DbSession, ensure_permission, require_permission
from app.modules.subscriptions import service
from app.modules.subscriptions.schemas import (
    CancelInput,
    GridInput,
    GridOut,
    InvoiceCreate,
    InvoiceOut,
    InvoicesPage,
    InvoiceSummaryOut,
    ManualPaymentInput,
    PlatformInvoiceOut,
    PlatformSchoolSubscriptionsPage,
    QuoteInput,
    SchoolSubscriptionOut,
    SubscriptionStateCode,
)
from app.modules.users.models import User

router = APIRouter()

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
InvoiceStatusFilter = Literal["QUOTE_REQUIRED", "ISSUED", "PAID", "EXPIRED", "CANCELLED"]
PlatformReader = Annotated[User, Depends(require_permission("platform.subscriptions.read"))]
PlatformManager = Annotated[User, Depends(require_permission("platform.subscriptions.manage"))]


def _page_meta(page: int, page_size: int, total: int) -> dict[str, int]:
    return {"page": page, "page_size": page_size, "total": total, "total_pages": (total + page_size - 1) // page_size}


# --- École -------------------------------------------------------------------------------------
@router.get("/school-subscription", response_model=SchoolSubscriptionOut)
async def get_school_subscription(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> SchoolSubscriptionOut:
    school = await service.get_school_or_404(db, school_id)
    await ensure_permission(
        db, current_user, "subscriptions.read", organization_id=school.organization_id, school_id=school.id
    )
    return await service.build_school_subscription(db, school)


@router.get("/school-subscription/invoices", response_model=list[InvoiceSummaryOut])
async def list_school_subscription_invoices(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> list[InvoiceSummaryOut]:
    school = await service.get_school_or_404(db, school_id)
    await ensure_permission(
        db, current_user, "subscriptions.read", organization_id=school.organization_id, school_id=school.id
    )
    now = service.utc_now()
    return [service.invoice_summary(invoice, now) for invoice in await service.list_school_invoices(db, school.id)]


@router.get("/school-subscription/invoices/{invoice_id}", response_model=InvoiceOut)
async def get_school_subscription_invoice(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> InvoiceOut:
    invoice = await service.get_invoice_or_404(db, invoice_id)
    school = await service.get_school_or_404(db, invoice.school_id)
    await ensure_permission(
        db, current_user, "subscriptions.read", organization_id=school.organization_id, school_id=school.id
    )
    return await service.invoice_out(db, invoice, service.utc_now())


@router.post("/school-subscription/invoices", response_model=InvoiceOut, status_code=status.HTTP_201_CREATED)
async def create_school_subscription_invoice(
    payload: InvoiceCreate, db: DbSession, current_user: CurrentUser
) -> InvoiceOut:
    school = await service.get_school_or_404(db, payload.school_id)
    await ensure_permission(
        db, current_user, "subscriptions.pay", organization_id=school.organization_id, school_id=school.id
    )
    invoice = await service.create_invoice(db, school, current_user, payload)
    return await service.invoice_out(db, invoice, service.utc_now())


def _pdf_response(filename: str, pdf: bytes) -> Response:
    return Response(
        content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# Lot C — reçu PDF d'une facture payée (409 si la facture n'est pas payée).
@router.get("/school-subscription/invoices/{invoice_id}/receipt.pdf")
async def download_school_subscription_receipt(invoice_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Response:
    invoice = await service.get_invoice_or_404(db, invoice_id)
    school = await service.get_school_or_404(db, invoice.school_id)
    await ensure_permission(
        db, current_user, "subscriptions.read", organization_id=school.organization_id, school_id=school.id
    )
    return _pdf_response(*await service.invoice_receipt_pdf(db, invoice))


# --- Plateforme : grilles de prix --------------------------------------------------------------
@router.get("/platform/subscription-grids", response_model=list[GridOut])
async def list_subscription_grids(db: DbSession, _: PlatformReader) -> list[GridOut]:
    return await service.list_grids(db)


@router.post("/platform/subscription-grids", response_model=GridOut, status_code=status.HTTP_201_CREATED)
async def create_subscription_grid(payload: GridInput, db: DbSession, current_user: PlatformManager) -> GridOut:
    return await service.create_grid(db, current_user, payload)


@router.put("/platform/subscription-grids/{grid_id}", response_model=GridOut)
async def update_subscription_grid(
    grid_id: uuid.UUID, payload: GridInput, db: DbSession, current_user: PlatformManager
) -> GridOut:
    return await service.update_grid(db, grid_id, current_user, payload)


@router.post("/platform/subscription-grids/{grid_id}/activate", response_model=GridOut)
async def activate_subscription_grid(grid_id: uuid.UUID, db: DbSession, current_user: PlatformManager) -> GridOut:
    return await service.activate_grid(db, grid_id, current_user)


# --- Plateforme : abonnements par école --------------------------------------------------------
@router.get("/platform/subscriptions", response_model=PlatformSchoolSubscriptionsPage)
async def list_platform_school_subscriptions(
    db: DbSession,
    _: PlatformReader,
    page: Page = 1,
    page_size: PageSize = 20,
    state: SubscriptionStateCode | None = None,
) -> PlatformSchoolSubscriptionsPage:
    items = await service.list_school_subscriptions(db, state)
    start = (page - 1) * page_size
    return PlatformSchoolSubscriptionsPage(items=items[start : start + page_size], **_page_meta(page, page_size, len(items)))


# --- Plateforme : factures ---------------------------------------------------------------------
@router.get("/platform/subscription-invoices", response_model=InvoicesPage)
async def list_platform_subscription_invoices(
    db: DbSession,
    _: PlatformReader,
    page: Page = 1,
    page_size: PageSize = 20,
    status_filter: Annotated[InvoiceStatusFilter | None, Query(alias="status")] = None,
    school_id: uuid.UUID | None = None,
) -> InvoicesPage:
    items, total = await service.list_platform_invoices(db, page, page_size, status_filter, school_id)
    return InvoicesPage(items=items, **_page_meta(page, page_size, total))


@router.get("/platform/subscription-invoices/{invoice_id}", response_model=PlatformInvoiceOut)
async def get_platform_subscription_invoice(invoice_id: uuid.UUID, db: DbSession, _: PlatformReader) -> PlatformInvoiceOut:
    invoice = await service.get_invoice_or_404(db, invoice_id)
    return await service.platform_invoice_out(db, invoice, service.utc_now())


@router.post("/platform/subscription-invoices/{invoice_id}/quote", response_model=PlatformInvoiceOut)
async def set_subscription_invoice_quote(
    invoice_id: uuid.UUID, payload: QuoteInput, db: DbSession, current_user: PlatformManager
) -> PlatformInvoiceOut:
    invoice = await service.set_quote(db, invoice_id, current_user, payload)
    return await service.platform_invoice_out(db, invoice, service.utc_now())


@router.post("/platform/subscription-invoices/{invoice_id}/cancel", response_model=PlatformInvoiceOut)
async def cancel_subscription_invoice(
    invoice_id: uuid.UUID, payload: CancelInput, db: DbSession, current_user: PlatformManager
) -> PlatformInvoiceOut:
    invoice = await service.cancel_invoice(db, invoice_id, current_user, payload.reason)
    return await service.platform_invoice_out(db, invoice, service.utc_now())


@router.post(
    "/platform/subscription-invoices/{invoice_id}/manual-payments",
    response_model=PlatformInvoiceOut,
    status_code=status.HTTP_201_CREATED,
)
async def record_subscription_manual_payment(
    invoice_id: uuid.UUID, payload: ManualPaymentInput, db: DbSession, current_user: PlatformManager
) -> PlatformInvoiceOut:
    invoice = await service.record_manual_payment(db, invoice_id, current_user, payload)
    return await service.platform_invoice_out(db, invoice, service.utc_now())


@router.get("/platform/subscription-invoices/{invoice_id}/receipt.pdf")
async def download_platform_subscription_receipt(invoice_id: uuid.UUID, db: DbSession, _: PlatformReader) -> Response:
    invoice = await service.get_invoice_or_404(db, invoice_id)
    return _pdf_response(*await service.invoice_receipt_pdf(db, invoice))
