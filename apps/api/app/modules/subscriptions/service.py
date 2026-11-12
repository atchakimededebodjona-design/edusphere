"""Abonnements des écoles (Phase 29, lot A) — logique métier.

Verrouillage (concurrence) :
- toute opération qui crée une facture, la modifie, la paie ou crée une période prend d'abord le
  verrou consultatif TRANSACTIONNEL de l'école (`lock_school_subscription`), puis verrouille la
  facture concernée `FOR UPDATE`. Toujours dans cet ordre : jamais d'interblocage entre ces
  opérations. Deux demandes simultanées pour une même école sont donc sérialisées : une seule
  facture ouverte, aucune période qui se chevauche, aucun double paiement ;
- l'activation d'une grille prend un verrou consultatif dédié (`_lock_grids`).
Les index uniques partiels de la migration 0027 restent la seconde ligne de défense.

Contexte RLS : `set_config(..., is_local=true)` ne vaut que pour la transaction — après chaque
commit, le contexte de l'utilisateur est ré-appliqué (`_commit`), même motif que cash/service.py.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenancy import apply_tenant_context
from app.modules.audit import service as audit_service
from app.modules.cash.service import school_today
from app.modules.platform.service import student_counts_by_school
from app.modules.schools.models import School
from app.modules.students.models import Student
from app.modules.subscriptions import pricing
from app.modules.subscriptions.models import (
    GRID_STATUS_ACTIVE,
    GRID_STATUS_ARCHIVED,
    GRID_STATUS_DRAFT,
    INVOICE_STATUS_CANCELLED,
    INVOICE_STATUS_EXPIRED,
    INVOICE_STATUS_ISSUED,
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_QUOTE_REQUIRED,
    OPEN_INVOICE_STATUSES,
    PAYMENT_PROVIDER_MANUAL,
    PAYMENT_STATUS_SUCCEEDED,
    SUBSCRIPTION_CURRENCY,
    SchoolSubscriptionPeriod,
    SubscriptionInvoice,
    SubscriptionPayment,
    SubscriptionPriceGrid,
    SubscriptionPriceLine,
)
from app.modules.subscriptions.schemas import (
    GridInput,
    GridOut,
    GridPeriodPrices,
    InvoiceCreate,
    InvoiceOut,
    InvoiceSummaryOut,
    ManualPaymentInput,
    OfferOut,
    PaymentOut,
    PeriodOut,
    PlatformInvoiceOut,
    PlatformSchoolSubscriptionOut,
    QuoteInput,
    SchoolSubscriptionOut,
)
from app.modules.users.models import User

INVOICE_LIST_MAX_ROWS = 200

_ADVISORY_LOCK_SQL = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")
# Numérotation séquentielle SANS TROU : la ligne du compteur reste verrouillée jusqu'au commit de
# la transaction qui émet la facture ; un rollback annule aussi l'incrément.
_NEXT_INVOICE_NUMBER_SQL = text(
    "INSERT INTO subscription_invoice_number_counters (year, last_value) VALUES (:year, 1) "
    "ON CONFLICT (year) DO UPDATE SET last_value = subscription_invoice_number_counters.last_value + 1 "
    "RETURNING last_value"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


# --- Verrous et transaction --------------------------------------------------------------------
async def lock_school_subscription(db: AsyncSession, school_id: uuid.UUID) -> None:
    await db.execute(_ADVISORY_LOCK_SQL, {"key": f"edulinkage:subscription:school:{school_id}"})


async def _lock_grids(db: AsyncSession) -> None:
    await db.execute(_ADVISORY_LOCK_SQL, {"key": "edulinkage:subscription:grids"})


async def _commit(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.commit()
    await apply_tenant_context(db, user_id)


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


# --- Lectures de base --------------------------------------------------------------------------
async def get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


async def active_student_count(db: AsyncSession, school_id: uuid.UUID) -> int:
    """Même définition que le tableau de bord d'école et l'agrégat plateforme
    (`Student.status == "ACTIVE"`)."""
    result = await db.execute(
        select(func.count()).select_from(Student).where(Student.school_id == school_id, Student.status == "ACTIVE")
    )
    return int(result.scalar_one())


async def school_periods(db: AsyncSession, school_id: uuid.UUID) -> list[SchoolSubscriptionPeriod]:
    result = await db.execute(
        select(SchoolSubscriptionPeriod)
        .where(SchoolSubscriptionPeriod.school_id == school_id)
        .order_by(SchoolSubscriptionPeriod.starts_on)
    )
    return list(result.scalars().all())


def spans(periods: list[SchoolSubscriptionPeriod]) -> list[pricing.PeriodSpan]:
    return [pricing.PeriodSpan(period.kind, period.starts_on, period.ends_on) for period in periods]


async def _active_grid(db: AsyncSession) -> tuple[SubscriptionPriceGrid, list[SubscriptionPriceLine]] | None:
    grid = (
        await db.execute(select(SubscriptionPriceGrid).where(SubscriptionPriceGrid.status == GRID_STATUS_ACTIVE))
    ).scalar_one_or_none()
    if grid is None:
        return None
    lines = (
        await db.execute(select(SubscriptionPriceLine).where(SubscriptionPriceLine.grid_id == grid.id))
    ).scalars()
    return grid, list(lines)


def _line_for(lines: list[SubscriptionPriceLine], period_months: int, tier: int) -> SubscriptionPriceLine | None:
    return next((line for line in lines if line.period_months == period_months and line.tier == tier), None)


def effective_invoice_status(invoice: SubscriptionInvoice, now: datetime) -> str:
    """Une facture `ISSUED` dont la validité est dépassée est expirée, même avant que son statut
    stocké ne soit mis à jour (expiration paresseuse) : elle n'est plus ni payable ni « ouverte »."""
    if invoice.status == INVOICE_STATUS_ISSUED and invoice.expires_at is not None and invoice.expires_at <= now:
        return INVOICE_STATUS_EXPIRED
    return invoice.status


def _summary_fields(invoice: SubscriptionInvoice, now: datetime) -> dict:
    return {
        "id": invoice.id,
        "number": invoice.number,
        "status": effective_invoice_status(invoice, now),
        "period_months": invoice.period_months,
        "student_count": invoice.student_count,
        "tier": invoice.tier,
        "total_amount": invoice.total_amount,
        "currency": invoice.currency,
        "issued_at": invoice.issued_at,
        "expires_at": invoice.expires_at,
        "paid_at": invoice.paid_at,
        "created_at": invoice.created_at,
    }


def invoice_summary(invoice: SubscriptionInvoice, now: datetime) -> InvoiceSummaryOut:
    return InvoiceSummaryOut(**_summary_fields(invoice, now))


async def invoice_out(db: AsyncSession, invoice: SubscriptionInvoice, now: datetime) -> InvoiceOut:
    payments = (
        await db.execute(
            select(SubscriptionPayment)
            .where(SubscriptionPayment.invoice_id == invoice.id)
            .order_by(SubscriptionPayment.created_at)
        )
    ).scalars()
    period = (
        await db.execute(select(SchoolSubscriptionPeriod).where(SchoolSubscriptionPeriod.invoice_id == invoice.id))
    ).scalar_one_or_none()
    return InvoiceOut(
        **_summary_fields(invoice, now),
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        base_amount=invoice.base_amount,
        supplement_amount=invoice.supplement_amount,
        grid_id=invoice.grid_id,
        cancelled_at=invoice.cancelled_at,
        cancel_reason=invoice.cancel_reason,
        payments=[PaymentOut.model_validate(payment) for payment in payments],
        period=PeriodOut.model_validate(period) if period is not None else None,
    )


async def platform_invoice_out(db: AsyncSession, invoice: SubscriptionInvoice, now: datetime) -> PlatformInvoiceOut:
    school_name = await db.scalar(select(School.name).where(School.id == invoice.school_id))
    base = await invoice_out(db, invoice, now)
    return PlatformInvoiceOut(**base.model_dump(), school_name=school_name or "")


async def get_invoice_or_404(db: AsyncSession, invoice_id: uuid.UUID) -> SubscriptionInvoice:
    invoice = await db.get(SubscriptionInvoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription invoice not found")
    return invoice


async def _lock_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> SubscriptionInvoice:
    # populate_existing : l'objet a pu être chargé plus tôt dans la requête ; sans cela, la carte
    # d'identité renverrait l'état d'AVANT le verrou.
    invoice = (
        await db.execute(
            select(SubscriptionInvoice)
            .where(SubscriptionInvoice.id == invoice_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription invoice not found")
    return invoice


async def _open_invoice(db: AsyncSession, school_id: uuid.UUID, now: datetime) -> SubscriptionInvoice | None:
    invoice = (
        await db.execute(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.school_id == school_id, SubscriptionInvoice.status.in_(OPEN_INVOICE_STATUSES)
            )
        )
    ).scalar_one_or_none()
    if invoice is None or effective_invoice_status(invoice, now) not in OPEN_INVOICE_STATUSES:
        return None
    return invoice


# --- État de l'abonnement d'une école ----------------------------------------------------------
async def build_school_subscription(db: AsyncSession, school: School) -> SchoolSubscriptionOut:
    now = utc_now()
    today = school_today(school, now)
    periods = await school_periods(db, school.id)
    state = pricing.compute_state(spans(periods), today)
    current = next((p for p in periods if p.starts_on <= today <= p.ends_on), None)

    count = await active_student_count(db, school.id)
    tier = pricing.tier_for_student_count(count)
    active = await _active_grid(db)
    offers: list[OfferOut] = []
    for months in pricing.PERIOD_MONTHS:
        line = _line_for(active[1], months, tier) if active is not None and tier is not None else None
        offers.append(
            OfferOut(
                period_months=months,
                base_amount=line.base_amount if line else None,
                supplement_amount=line.supplement_amount if line else None,
                total_amount=(line.base_amount + line.supplement_amount) if line else None,
            )
        )
    open_invoice = await _open_invoice(db, school.id, now)
    return SchoolSubscriptionOut(
        school_id=school.id,
        school_name=school.name,
        today=today,
        state=state.state,
        current_period=PeriodOut.model_validate(current) if current is not None else None,
        covered_until=state.covered_until,
        next_period_starts_on=state.next_starts_on,
        active_student_count=count,
        tier=tier,
        quote_required=tier is None,
        grid_available=active is not None,
        currency=SUBSCRIPTION_CURRENCY,
        offers=offers,
        open_invoice=invoice_summary(open_invoice, now) if open_invoice is not None else None,
        periods=[PeriodOut.model_validate(period) for period in periods],
    )


# --- Factures (côté école) ---------------------------------------------------------------------
async def _next_invoice_number(db: AsyncSession, now: datetime) -> str:
    value = (await db.execute(_NEXT_INVOICE_NUMBER_SQL, {"year": now.year})).scalar_one()
    return pricing.format_invoice_number(now.year, int(value))


def _issue(invoice: SubscriptionInvoice, number: str, total: Decimal, now: datetime) -> None:
    invoice.number = number
    invoice.total_amount = total
    invoice.issued_at = now
    invoice.expires_at = now + timedelta(days=settings.subscription_invoice_validity_days)
    invoice.status = INVOICE_STATUS_ISSUED


async def create_invoice(db: AsyncSession, school: School, user: User, payload: InvoiceCreate) -> SubscriptionInvoice:
    await lock_school_subscription(db, school.id)
    now = utc_now()

    # Idempotence — même clé + même durée = même demande (double clic, nouvel essai réseau) : la
    # facture existante est renvoyée, jamais modifiée. Même clé + autre durée = conflit explicite.
    existing = (
        await db.execute(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.school_id == school.id,
                SubscriptionInvoice.idempotency_key == payload.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.period_months == payload.period_months:
            return existing
        raise _conflict("Idempotency key already used for a different subscription invoice")

    # Expiration paresseuse des factures de CETTE école dont la validité est dépassée (sous verrou).
    await _expire_stale_invoices_for_school(db, school.id, now)
    if await _open_invoice(db, school.id, now) is not None:
        raise _conflict("An open subscription invoice already exists for this school")

    count = await active_student_count(db, school.id)
    tier = pricing.tier_for_student_count(count)
    invoice = SubscriptionInvoice(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        period_months=payload.period_months,
        student_count=count,
        currency=SUBSCRIPTION_CURRENCY,
        idempotency_key=payload.idempotency_key,
        created_by=user.id,
    )
    if tier is None:
        invoice.status = INVOICE_STATUS_QUOTE_REQUIRED
        action = audit_service.ACTION_SUBSCRIPTION_INVOICE_QUOTE_REQUESTED
        summary = f"Demande de devis d'abonnement ({payload.period_months} mois, {count} élèves actifs)"
    else:
        active = await _active_grid(db)
        if active is None:
            raise _conflict("Subscription prices are not configured yet")
        grid, lines = active
        line = _line_for(lines, payload.period_months, tier)
        if line is None:
            raise _conflict("The active price grid has no price for this period and tier")
        invoice.tier = tier
        invoice.grid_id = grid.id
        invoice.base_amount = line.base_amount
        invoice.supplement_amount = line.supplement_amount
        _issue(invoice, await _next_invoice_number(db, now), line.base_amount + line.supplement_amount, now)
        action = audit_service.ACTION_SUBSCRIPTION_INVOICE_ISSUED
        summary = (
            f"Facture d'abonnement {invoice.number} émise : {payload.period_months} mois, {count} élèves actifs, "
            f"tranche {tier}, {invoice.total_amount} {SUBSCRIPTION_CURRENCY}"
        )

    db.add(invoice)
    await db.flush()
    await audit_service.record_audit_event(
        db,
        school_id=school.id,
        organization_id=school.organization_id,
        actor_user_id=user.id,
        action=action,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_INVOICE,
        entity_id=invoice.id,
        summary=summary,
        metadata={
            "number": invoice.number,
            "period_months": invoice.period_months,
            "student_count": count,
            "tier": invoice.tier,
            "total_amount": str(invoice.total_amount) if invoice.total_amount is not None else None,
        },
    )
    await _commit(db, user.id)
    await db.refresh(invoice)
    return invoice


async def _expire_stale_invoices_for_school(db: AsyncSession, school_id: uuid.UUID, now: datetime) -> None:
    stale = (
        await db.execute(
            select(SubscriptionInvoice)
            .where(
                SubscriptionInvoice.school_id == school_id,
                SubscriptionInvoice.status == INVOICE_STATUS_ISSUED,
                SubscriptionInvoice.expires_at <= now,
            )
            .with_for_update()
        )
    ).scalars()
    for invoice in stale:
        invoice.status = INVOICE_STATUS_EXPIRED
        await audit_service.record_audit_event(
            db,
            school_id=invoice.school_id,
            organization_id=invoice.organization_id,
            actor_user_id=None,
            action=audit_service.ACTION_SUBSCRIPTION_INVOICE_EXPIRED,
            entity_type=audit_service.ENTITY_SUBSCRIPTION_INVOICE,
            entity_id=invoice.id,
            summary=f"Facture d'abonnement {invoice.number} expirée sans paiement",
            metadata={"number": invoice.number},
        )
    await db.flush()


async def list_school_invoices(db: AsyncSession, school_id: uuid.UUID) -> list[SubscriptionInvoice]:
    result = await db.execute(
        select(SubscriptionInvoice)
        .where(SubscriptionInvoice.school_id == school_id)
        .order_by(SubscriptionInvoice.created_at.desc())
        .limit(INVOICE_LIST_MAX_ROWS)
    )
    return list(result.scalars().all())


# --- Paiement et période -----------------------------------------------------------------------
def _new_payment_identifier() -> str:
    """Aléatoire, non devinable, jamais l'id de la facture (cadrage §5.5 et §9)."""
    return f"ELS{secrets.token_hex(16)}"


async def _mark_paid_and_create_period(
    db: AsyncSession, school: School, invoice: SubscriptionInvoice, now: datetime
) -> SchoolSubscriptionPeriod:
    """Point UNIQUE de confirmation d'un paiement (paiement manuel ici, PayGate au lot B) : facture
    `PAID` et création de LA période, sous le verrou de l'école déjà pris par l'appelant. Début :
    aujourd'hui, ou le lendemain de la dernière période existante (continuité, trimestre gratuit
    compris)."""
    periods = await school_periods(db, school.id)
    start = pricing.next_period_start(spans(periods), school_today(school, now))
    period = SchoolSubscriptionPeriod(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        kind=pricing.PERIOD_KIND_PAID,
        invoice_id=invoice.id,
        starts_on=start,
        ends_on=pricing.period_end(start, invoice.period_months),
    )
    invoice.status = INVOICE_STATUS_PAID
    invoice.paid_at = now
    db.add(period)
    await db.flush()
    return period


def _ensure_payable(invoice: SubscriptionInvoice, now: datetime) -> None:
    current = effective_invoice_status(invoice, now)
    if current == INVOICE_STATUS_ISSUED:
        return
    details = {
        INVOICE_STATUS_PAID: "Subscription invoice is already paid",
        INVOICE_STATUS_EXPIRED: "Subscription invoice has expired",
        INVOICE_STATUS_CANCELLED: "Subscription invoice is cancelled",
        INVOICE_STATUS_QUOTE_REQUIRED: "Quote amount has not been set for this subscription invoice",
    }
    raise _conflict(details.get(current, "Subscription invoice is not payable"))


async def record_manual_payment(
    db: AsyncSession, invoice_id: uuid.UUID, user: User, payload: ManualPaymentInput
) -> SubscriptionInvoice:
    loaded = await get_invoice_or_404(db, invoice_id)
    await lock_school_subscription(db, loaded.school_id)
    invoice = await _lock_invoice(db, invoice_id)
    now = utc_now()

    existing = (
        await db.execute(
            select(SubscriptionPayment).where(
                SubscriptionPayment.invoice_id == invoice.id,
                SubscriptionPayment.idempotency_key == payload.idempotency_key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        same = (
            existing.provider == PAYMENT_PROVIDER_MANUAL
            and existing.method == payload.method
            and Decimal(existing.amount) == payload.amount
            and existing.reference == payload.reference
        )
        if same:
            return invoice
        raise _conflict("Idempotency key already used for a different payment")

    _ensure_payable(invoice, now)
    if invoice.total_amount is None or Decimal(invoice.total_amount) != payload.amount:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Payment amount must equal the invoice total",
        )

    school = await get_school_or_404(db, invoice.school_id)
    payment = SubscriptionPayment(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        provider=PAYMENT_PROVIDER_MANUAL,
        method=payload.method,
        status=PAYMENT_STATUS_SUCCEEDED,
        amount=payload.amount,
        currency=SUBSCRIPTION_CURRENCY,
        identifier=_new_payment_identifier(),
        idempotency_key=payload.idempotency_key,
        reference=payload.reference,
        recorded_by=user.id,
        confirmed_at=now,
    )
    db.add(payment)
    await db.flush()
    period = await _mark_paid_and_create_period(db, school, invoice, now)
    await audit_service.record_audit_event(
        db,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        actor_user_id=user.id,
        action=audit_service.ACTION_SUBSCRIPTION_PAYMENT_MANUAL_RECORDED,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_PAYMENT,
        entity_id=payment.id,
        summary=(
            f"Paiement manuel ({payload.method}) de la facture {invoice.number} : {payload.amount} "
            f"{SUBSCRIPTION_CURRENCY}, abonnement du {period.starts_on.isoformat()} au {period.ends_on.isoformat()}"
        ),
        metadata={
            "invoice_number": invoice.number,
            "method": payload.method,
            "amount": str(payload.amount),
            "reference": payload.reference,
            "period_starts_on": period.starts_on.isoformat(),
            "period_ends_on": period.ends_on.isoformat(),
        },
    )
    await _commit(db, user.id)
    await db.refresh(invoice)
    return invoice


# --- Devis et annulation (côté plateforme) -----------------------------------------------------
async def set_quote(db: AsyncSession, invoice_id: uuid.UUID, user: User, payload: QuoteInput) -> SubscriptionInvoice:
    loaded = await get_invoice_or_404(db, invoice_id)
    await lock_school_subscription(db, loaded.school_id)
    invoice = await _lock_invoice(db, invoice_id)
    if invoice.status != INVOICE_STATUS_QUOTE_REQUIRED:
        raise _conflict("Subscription invoice is not awaiting a quote")
    now = utc_now()
    _issue(invoice, await _next_invoice_number(db, now), payload.total_amount, now)
    invoice.quote_amount_set_by = user.id
    await db.flush()
    await audit_service.record_audit_event(
        db,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        actor_user_id=user.id,
        action=audit_service.ACTION_SUBSCRIPTION_INVOICE_QUOTE_SET,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_INVOICE,
        entity_id=invoice.id,
        summary=f"Devis d'abonnement chiffré : facture {invoice.number}, {payload.total_amount} {SUBSCRIPTION_CURRENCY}",
        metadata={"number": invoice.number, "total_amount": str(payload.total_amount)},
    )
    await _commit(db, user.id)
    await db.refresh(invoice)
    return invoice


async def cancel_invoice(db: AsyncSession, invoice_id: uuid.UUID, user: User, reason: str) -> SubscriptionInvoice:
    loaded = await get_invoice_or_404(db, invoice_id)
    await lock_school_subscription(db, loaded.school_id)
    invoice = await _lock_invoice(db, invoice_id)
    if invoice.status == INVOICE_STATUS_PAID:
        raise _conflict("A paid subscription invoice cannot be cancelled")
    if invoice.status not in OPEN_INVOICE_STATUSES:
        raise _conflict("Subscription invoice is not open")
    now = utc_now()
    invoice.status = INVOICE_STATUS_CANCELLED
    invoice.cancelled_at = now
    invoice.cancelled_by = user.id
    invoice.cancel_reason = reason
    await db.flush()
    await audit_service.record_audit_event(
        db,
        school_id=invoice.school_id,
        organization_id=invoice.organization_id,
        actor_user_id=user.id,
        action=audit_service.ACTION_SUBSCRIPTION_INVOICE_CANCELLED,
        entity_type=audit_service.ENTITY_SUBSCRIPTION_INVOICE,
        entity_id=invoice.id,
        summary=f"Facture d'abonnement {invoice.number or '(devis)'} annulée : {reason}",
        metadata={"number": invoice.number, "reason": reason},
    )
    await _commit(db, user.id)
    await db.refresh(invoice)
    return invoice


def _platform_invoices_query(status_filter: str | None, school_id: uuid.UUID | None, now: datetime) -> Select:
    query = select(SubscriptionInvoice)
    if school_id is not None:
        query = query.where(SubscriptionInvoice.school_id == school_id)
    if status_filter == INVOICE_STATUS_ISSUED:
        query = query.where(SubscriptionInvoice.status == INVOICE_STATUS_ISSUED, SubscriptionInvoice.expires_at > now)
    elif status_filter == INVOICE_STATUS_EXPIRED:
        query = query.where(
            or_(
                SubscriptionInvoice.status == INVOICE_STATUS_EXPIRED,
                and_(SubscriptionInvoice.status == INVOICE_STATUS_ISSUED, SubscriptionInvoice.expires_at <= now),
            )
        )
    elif status_filter is not None:
        query = query.where(SubscriptionInvoice.status == status_filter)
    return query


async def list_platform_invoices(
    db: AsyncSession, page: int, page_size: int, status_filter: str | None, school_id: uuid.UUID | None
) -> tuple[list[PlatformInvoiceOut], int]:
    now = utc_now()
    query = _platform_invoices_query(status_filter, school_id, now)
    total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
    invoices = (
        await db.execute(
            query.order_by(SubscriptionInvoice.created_at.desc(), SubscriptionInvoice.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars()
    return [await platform_invoice_out(db, invoice, now) for invoice in invoices], total


# --- Vue plateforme : abonnements par école ----------------------------------------------------
async def list_school_subscriptions(db: AsyncSession, state_filter: str | None) -> list[PlatformSchoolSubscriptionOut]:
    """Toutes les écoles avec leur état calculé. Échelle pilote : l'état étant calculé (jamais
    stocké), le filtre par état se fait ici après calcul ; la pagination est faite par l'appelant."""
    now = utc_now()
    schools = list((await db.execute(select(School).order_by(School.name, School.id))).scalars())
    periods_by_school: dict[uuid.UUID, list[SchoolSubscriptionPeriod]] = {}
    for period in (await db.execute(select(SchoolSubscriptionPeriod))).scalars():
        periods_by_school.setdefault(period.school_id, []).append(period)
    open_by_school: dict[uuid.UUID, SubscriptionInvoice] = {
        invoice.school_id: invoice
        for invoice in (
            await db.execute(select(SubscriptionInvoice).where(SubscriptionInvoice.status.in_(OPEN_INVOICE_STATUSES)))
        ).scalars()
    }
    counts = await student_counts_by_school(db, [school.id for school in schools])

    items: list[PlatformSchoolSubscriptionOut] = []
    for school in schools:
        periods = periods_by_school.get(school.id, [])
        state = pricing.compute_state(spans(periods), school_today(school, now))
        if state_filter is not None and state.state != state_filter:
            continue
        open_invoice = open_by_school.get(school.id)
        open_status = effective_invoice_status(open_invoice, now) if open_invoice is not None else None
        items.append(
            PlatformSchoolSubscriptionOut(
                school_id=school.id,
                school_name=school.name,
                organization_id=school.organization_id,
                state=state.state,
                current_period_kind=state.current.kind if state.current else None,
                covered_until=state.covered_until,
                next_period_starts_on=state.next_starts_on,
                has_free_trial=any(p.kind == pricing.PERIOD_KIND_FREE_TRIAL for p in periods),
                open_invoice_status=open_status if open_status in OPEN_INVOICE_STATUSES else None,
                active_student_count=counts.get(school.id, (0, 0))[1],
            )
        )
    return items


# --- Grilles de prix (côté plateforme) ---------------------------------------------------------
def _grid_out(grid: SubscriptionPriceGrid, lines: list[SubscriptionPriceLine]) -> GridOut:
    periods: list[GridPeriodPrices] = []
    for months in pricing.PERIOD_MONTHS:
        by_tier = {line.tier: line for line in lines if line.period_months == months}
        if len(by_tier) != len(pricing.TIER_NUMBERS):
            continue
        periods.append(
            GridPeriodPrices(
                period_months=months,
                base_amount=by_tier[0].base_amount,
                supplement_tier_1=by_tier[1].supplement_amount,
                supplement_tier_2=by_tier[2].supplement_amount,
                supplement_tier_3=by_tier[3].supplement_amount,
            )
        )
    return GridOut(
        id=grid.id,
        label=grid.label,
        currency=grid.currency,
        status=grid.status,
        created_at=grid.created_at,
        activated_at=grid.activated_at,
        archived_at=grid.archived_at,
        periods=periods,
    )


def _lines_from_payload(grid_id: uuid.UUID, payload: GridInput) -> list[SubscriptionPriceLine]:
    """Le forfait de base d'une durée est recopié sur ses 4 lignes : il est donc identique pour
    toutes les tranches par construction (jamais saisi tranche par tranche)."""
    lines: list[SubscriptionPriceLine] = []
    for period in payload.periods:
        supplements = {
            0: Decimal("0"),
            1: period.supplement_tier_1,
            2: period.supplement_tier_2,
            3: period.supplement_tier_3,
        }
        for tier in pricing.TIER_NUMBERS:
            lines.append(
                SubscriptionPriceLine(
                    id=uuid.uuid4(),
                    grid_id=grid_id,
                    period_months=period.period_months,
                    tier=tier,
                    base_amount=period.base_amount,
                    supplement_amount=supplements[tier],
                )
            )
    return lines


async def _grid_lines(db: AsyncSession, grid_id: uuid.UUID) -> list[SubscriptionPriceLine]:
    return list(
        (await db.execute(select(SubscriptionPriceLine).where(SubscriptionPriceLine.grid_id == grid_id))).scalars()
    )


async def list_grids(db: AsyncSession) -> list[GridOut]:
    grids = list(
        (
            await db.execute(
                select(SubscriptionPriceGrid).order_by(SubscriptionPriceGrid.created_at.desc(), SubscriptionPriceGrid.id)
            )
        ).scalars()
    )
    lines_by_grid: dict[uuid.UUID, list[SubscriptionPriceLine]] = {}
    if grids:
        for line in (
            await db.execute(
                select(SubscriptionPriceLine).where(SubscriptionPriceLine.grid_id.in_([grid.id for grid in grids]))
            )
        ).scalars():
            lines_by_grid.setdefault(line.grid_id, []).append(line)
    return [_grid_out(grid, lines_by_grid.get(grid.id, [])) for grid in grids]


async def create_grid(db: AsyncSession, user: User, payload: GridInput) -> GridOut:
    grid = SubscriptionPriceGrid(
        id=uuid.uuid4(),
        label=payload.label,
        currency=SUBSCRIPTION_CURRENCY,
        status=GRID_STATUS_DRAFT,
        created_by=user.id,
    )
    db.add(grid)
    await db.flush()
    lines = _lines_from_payload(grid.id, payload)
    db.add_all(lines)
    await _commit(db, user.id)
    await db.refresh(grid)
    return _grid_out(grid, await _grid_lines(db, grid.id))


async def _lock_grid(db: AsyncSession, grid_id: uuid.UUID) -> SubscriptionPriceGrid:
    grid = (
        await db.execute(
            select(SubscriptionPriceGrid)
            .where(SubscriptionPriceGrid.id == grid_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if grid is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price grid not found")
    return grid


async def update_grid(db: AsyncSession, grid_id: uuid.UUID, user: User, payload: GridInput) -> GridOut:
    await _lock_grids(db)
    grid = await _lock_grid(db, grid_id)
    if grid.status != GRID_STATUS_DRAFT:
        raise _conflict("Only a draft price grid can be modified")
    grid.label = payload.label
    await db.execute(delete(SubscriptionPriceLine).where(SubscriptionPriceLine.grid_id == grid.id))
    db.add_all(_lines_from_payload(grid.id, payload))
    await _commit(db, user.id)
    await db.refresh(grid)
    return _grid_out(grid, await _grid_lines(db, grid.id))


async def activate_grid(db: AsyncSession, grid_id: uuid.UUID, user: User) -> GridOut:
    """La grille active précédente est archivée dans la même transaction (jamais deux grilles
    actives, jamais aucune entre les deux). Une grille archivée ne revient jamais : on en crée une
    nouvelle."""
    await _lock_grids(db)
    grid = await _lock_grid(db, grid_id)
    if grid.status == GRID_STATUS_ACTIVE:
        return _grid_out(grid, await _grid_lines(db, grid.id))
    if grid.status == GRID_STATUS_ARCHIVED:
        raise _conflict("An archived price grid cannot be reactivated")
    lines = await _grid_lines(db, grid.id)
    if len(lines) != len(pricing.PERIOD_MONTHS) * len(pricing.TIER_NUMBERS):
        raise _conflict("Price grid is incomplete")

    now = utc_now()
    previous = (
        await db.execute(
            select(SubscriptionPriceGrid).where(SubscriptionPriceGrid.status == GRID_STATUS_ACTIVE).with_for_update()
        )
    ).scalar_one_or_none()
    if previous is not None:
        previous.status = GRID_STATUS_ARCHIVED
        previous.archived_at = now
        await db.flush()
    grid.status = GRID_STATUS_ACTIVE
    grid.activated_at = now
    grid.activated_by = user.id
    await _commit(db, user.id)
    await db.refresh(grid)
    return _grid_out(grid, lines)
