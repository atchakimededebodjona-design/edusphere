"""Abonnements des écoles (Phase 29, lot A) — endpoints.

Côté école (`/school-subscription*`) : même convention que cashier/router.py — l'école est chargée
sous le contexte RLS de l'appelant (404 pour une autre organisation), puis la permission est
vérifiée pour CETTE école (`ensure_permission`, règle de portée unique : 403 pour une autre école
de la même organisation). Le client n'envoie jamais de montant : uniquement la durée.

Côté plateforme (`/platform/subscription*`) : permissions `platform.subscriptions.read|manage`,
détenues uniquement par SUPER_ADMIN et PLATFORM_OWNER (rbac/seed.py) — 403 pour tout autre compte,
indépendamment de ce que le frontend affiche.

Lot B — paiement Mobile Money (PayGate Global, méthode directe) : lancement et suivi par l'école,
notification publique de PayGate (non authentifiée, non signée : elle ne fait jamais foi et ne
déclenche qu'une vérification d'état côté serveur). Voir subscriptions/online_payments.py.
"""

import json
import uuid
from typing import Annotated, Any, Literal
from urllib.parse import parse_qsl

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response, status

from app.core.config import settings
from app.core.permissions import CurrentUser, DbSession, ensure_permission, require_permission
from app.core.rate_limit import (
    ensure_paygate_callback_not_rate_limited,
    ensure_payments_not_rate_limited,
    ensure_public_pricing_not_rate_limited,
    register_paygate_callback_attempt,
    register_payments_attempt,
    register_public_pricing_attempt,
)
from app.modules.subscriptions import online_payments, service
from app.modules.subscriptions.schemas import (
    CancelInput,
    GridInput,
    GridOut,
    InvoiceCreate,
    InvoiceOut,
    InvoicesPage,
    InvoiceSummaryOut,
    ManualPaymentInput,
    OnlinePaymentInput,
    OnlinePaymentOut,
    PlatformInvoiceOut,
    PlatformSchoolSubscriptionsPage,
    LegalIdentityOut,
    PublicPricingOut,
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


# Lot B — paiement Mobile Money d'une facture émise. Le corps ne porte que le réseau, le numéro du
# payeur et une clé d'idempotence : le montant est celui de la facture, fixé par le serveur.
@router.post(
    "/school-subscription/invoices/{invoice_id}/payments",
    response_model=OnlinePaymentOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_school_subscription_online_payment(
    invoice_id: uuid.UUID, payload: OnlinePaymentInput, db: DbSession, current_user: CurrentUser
) -> OnlinePaymentOut:
    invoice = await service.get_invoice_or_404(db, invoice_id)
    school = await service.get_school_or_404(db, invoice.school_id)
    await ensure_permission(
        db, current_user, "subscriptions.pay", organization_id=school.organization_id, school_id=school.id
    )
    await ensure_payments_not_rate_limited(current_user.id)
    await register_payments_attempt(current_user.id)
    payment = await online_payments.initiate_online_payment(db, invoice_id, current_user, payload)
    return OnlinePaymentOut.model_validate(payment)


# Lot B — état d'une tentative, pour l'écran qui attend la confirmation sur le téléphone. Une
# tentative en cours est revérifiée auprès de PayGate, au plus une fois toutes les 10 secondes.
@router.get("/school-subscription/payments/{payment_id}", response_model=OnlinePaymentOut)
async def get_school_subscription_payment(payment_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> OnlinePaymentOut:
    payment = await online_payments.get_payment_or_404(db, payment_id)
    school = await service.get_school_or_404(db, payment.school_id)
    await ensure_permission(
        db, current_user, "subscriptions.read", organization_id=school.organization_id, school_id=school.id
    )
    checked = await online_payments.check_payment(db, payment_id, user_id=current_user.id, min_interval_seconds=10)
    return OnlinePaymentOut.model_validate(checked or payment)


# --- Notification de PayGate (publique) ----------------------------------------------------------
CALLBACK_MAX_BODY_BYTES = 8192


def _parse_callback_body(body: bytes, content_type: str) -> dict[str, Any] | None:
    """JSON d'après le guide ; formulaire accepté par prudence. Toute autre forme est invalide."""
    if not body or len(body) > CALLBACK_MAX_BODY_BYTES:
        return None
    try:
        if "application/x-www-form-urlencoded" in content_type:
            return dict(parse_qsl(body.decode("utf-8"), keep_blank_values=False))
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _declared_source_ip(request: Request) -> str | None:
    """Adresse transmise par le proxy, à titre de diagnostic seulement (jamais une vérification)."""
    real_ip = request.headers.get("x-real-ip")
    forwarded = request.headers.get("x-forwarded-for")
    if real_ip:
        return real_ip.strip()
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


# Page d'accueil publique (2026-11-16) : tarifs de la grille active, sans authentification. La page
# les lit côté serveur au plus une fois toutes les 5 minutes ; aucune donnée d'école n'y figure.
@router.get("/public/subscription-pricing", response_model=PublicPricingOut)
async def public_subscription_pricing(request: Request, response: Response, db: DbSession) -> PublicPricingOut:
    client_ip = request.client.host if request.client else None
    await ensure_public_pricing_not_rate_limited(client_ip)
    await register_public_pricing_attempt(client_ip)
    response.headers["Cache-Control"] = "public, max-age=300"
    return await service.public_pricing(db)


# Pages juridiques du site (2026-11-24) : identité de l'entreprise, lue dans la configuration du serveur
# (la même que sur les reçus). Sans authentification, en lecture seule ; même limite par IP que les
# tarifs publics. Les pages la lisent côté serveur, au plus une fois par heure.
@router.get("/public/legal-identity", response_model=LegalIdentityOut)
async def public_legal_identity(request: Request, response: Response) -> LegalIdentityOut:
    client_ip = request.client.host if request.client else None
    await ensure_public_pricing_not_rate_limited(client_ip)
    await register_public_pricing_attempt(client_ip)
    response.headers["Cache-Control"] = "public, max-age=3600"
    return LegalIdentityOut(
        trade_name=settings.billing_trade_name,
        legal_name=settings.billing_legal_name,
        legal_form=settings.billing_legal_form,
        address=settings.billing_address,
        nif=settings.billing_nif,
        rccm=settings.billing_rccm,
        phone=settings.billing_phone,
        email=settings.billing_email,
    )


@router.post("/payment-providers/paygate/callback")
async def paygate_callback(request: Request, background_tasks: BackgroundTasks, db: DbSession) -> dict[str, str]:
    """Notification de PayGate (« Callback URL » du profil marchand). Réponse toujours identique :
    elle ne révèle ni l'existence d'un identifiant ni l'état d'un paiement. La vérification d'état
    s'exécute après la réponse, dans sa propre session."""
    client_ip = request.client.host if request.client else None
    await ensure_paygate_callback_not_rate_limited(client_ip)
    await register_paygate_callback_attempt(client_ip)
    payload = _parse_callback_body(await request.body(), request.headers.get("content-type", ""))
    payment_id = await online_payments.record_paygate_callback(db, payload, _declared_source_ip(request))
    if payment_id is not None:
        background_tasks.add_task(online_payments.check_payment_in_new_session, payment_id)
    return {"status": "ok"}


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
