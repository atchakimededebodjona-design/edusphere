"""Commissions des partenaires — logique métier (voir commissions/models.py pour les règles).

Création : `accrue_for_paid_invoice`, appelée par le point UNIQUE de confirmation d'un paiement
d'abonnement (`subscriptions.service._mark_paid_and_create_period`), donc dans la même transaction
que la facture `PAID` et la période — paiement manuel comme paiement Mobile Money confirmé. Une
seule commission par facture (UNIQUE en base, en plus du contrôle applicatif).

Contexte RLS : les commissions et les partenaires sont « plateforme seulement ». Chaque fonction
élève explicitement le contexte (`set_platform_wide_context`) ; l'autorisation réelle reste la
permission vérifiée par la route et, côté partenaire, le filtre explicite sur SON `partner_id`.
"""

import logging
import uuid
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.modules.audit import service as audit_service
from app.modules.commissions.models import (
    COMMISSION_STATUS_CANCELLED,
    COMMISSION_STATUS_DUE,
    COMMISSION_STATUS_PAID,
    PartnerCommission,
)
from app.modules.commissions.schemas import (
    CommissionOut,
    CommissionTotals,
    MarkPaidInput,
)
from app.modules.partners.models import (
    ENROLLMENT_STATUS_ACTIVE,
    PARTNER_STATUS_ACTIVE,
    Partner,
    PartnerSchoolEnrollment,
)
from app.modules.schools.models import School
from app.modules.subscriptions import pricing
from app.modules.subscriptions.models import SubscriptionInvoice, SubscriptionPayment
from app.modules.users.models import User

logger = logging.getLogger(__name__)


def commission_amount(base_amount_excl_vat: Decimal, rate: Decimal) -> Decimal:
    """Montant de la commission, arrondi au franc (le XOF n'a pas de centimes)."""
    return (Decimal(base_amount_excl_vat) * Decimal(rate) / 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


# --- Création ------------------------------------------------------------------------------------
async def accrue_for_paid_invoice(
    db: AsyncSession,
    school: School,
    invoice: SubscriptionInvoice,
    payment: SubscriptionPayment,
    now: datetime,
) -> PartnerCommission | None:
    """Enregistre la commission due au partenaire de l'école pour cette facture payée, si :
    l'école a été inscrite par un partenaire (inscription active et éligible) et ce partenaire est
    actif au moment de la confirmation. Opération système (acteur système dans l'audit)."""
    await set_platform_wide_context(db)
    enrollment = (
        await db.execute(select(PartnerSchoolEnrollment).where(PartnerSchoolEnrollment.school_id == school.id))
    ).scalar_one_or_none()
    if (
        enrollment is None
        or enrollment.partner_id is None
        or not enrollment.commission_eligible
        or enrollment.status != ENROLLMENT_STATUS_ACTIVE
    ):
        return None
    partner = await db.get(Partner, enrollment.partner_id)
    if partner is None:
        return None
    if partner.status != PARTNER_STATUS_ACTIVE:
        logger.info(
            "Aucune commission pour la facture %s : partenaire %s suspendu au moment du paiement.",
            invoice.number,
            partner.id,
        )
        return None
    existing = (
        await db.execute(select(PartnerCommission).where(PartnerCommission.invoice_id == invoice.id))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    assert invoice.total_amount is not None  # facture payée : montant toujours défini
    base = pricing.amount_excl_vat(Decimal(invoice.total_amount), invoice.vat_rate)
    rate = Decimal(partner.commission_rate)
    commission = PartnerCommission(
        id=uuid.uuid4(),
        partner_id=partner.id,
        school_id=school.id,
        organization_id=school.organization_id,
        invoice_id=invoice.id,
        payment_id=payment.id,
        base_amount_excl_vat=base,
        rate=rate,
        amount=commission_amount(base, rate),
        currency=invoice.currency,
        status=COMMISSION_STATUS_DUE,
    )
    db.add(commission)
    await db.flush()
    await audit_service.record_audit_event(
        db,
        school_id=school.id,
        organization_id=school.organization_id,
        actor_user_id=None,
        action=audit_service.ACTION_PARTNER_COMMISSION_ACCRUED,
        entity_type=audit_service.ENTITY_PARTNER_COMMISSION,
        entity_id=commission.id,
        summary=(
            f"Commission due au partenaire {partner.display_name} pour la facture {invoice.number} : "
            f"{commission.amount} {commission.currency} ({rate} % de {base} HT)"
        ),
        metadata={
            "partner_id": str(partner.id),
            "invoice_number": invoice.number,
            "base_amount_excl_vat": str(base),
            "rate": str(rate),
            "amount": str(commission.amount),
            "vat_rate": str(invoice.vat_rate) if invoice.vat_rate is not None else None,
        },
    )
    return commission


# --- Lectures --------------------------------------------------------------------------------------
def _listing_query() -> Select:
    return (
        select(PartnerCommission, Partner.display_name, School.name, SubscriptionInvoice.number, SubscriptionInvoice.period_months)
        .join(Partner, Partner.id == PartnerCommission.partner_id)
        .join(School, School.id == PartnerCommission.school_id)
        .join(SubscriptionInvoice, SubscriptionInvoice.id == PartnerCommission.invoice_id)
    )


def _out(row: Any) -> CommissionOut:
    commission, partner_name, school_name, invoice_number, period_months = row
    return CommissionOut(
        id=commission.id,
        partner_id=commission.partner_id,
        partner_name=partner_name,
        school_id=commission.school_id,
        school_name=school_name,
        invoice_id=commission.invoice_id,
        invoice_number=invoice_number,
        period_months=period_months,
        base_amount_excl_vat=commission.base_amount_excl_vat,
        rate=commission.rate,
        amount=commission.amount,
        currency=commission.currency,
        status=commission.status,
        created_at=commission.created_at,
        paid_at=commission.paid_at,
        settlement_method=commission.settlement_method,
        settlement_reference=commission.settlement_reference,
        cancelled_at=commission.cancelled_at,
        cancel_reason=commission.cancel_reason,
    )


async def _totals(db: AsyncSession, partner_id: uuid.UUID | None) -> CommissionTotals:
    query = select(
        func.coalesce(func.sum(case((PartnerCommission.status == COMMISSION_STATUS_DUE, PartnerCommission.amount))), 0),
        func.count(case((PartnerCommission.status == COMMISSION_STATUS_DUE, 1))),
        func.coalesce(func.sum(case((PartnerCommission.status == COMMISSION_STATUS_PAID, PartnerCommission.amount))), 0),
        func.count(case((PartnerCommission.status == COMMISSION_STATUS_PAID, 1))),
    )
    if partner_id is not None:
        query = query.where(PartnerCommission.partner_id == partner_id)
    due_amount, due_count, paid_amount, paid_count = (await db.execute(query)).one()
    return CommissionTotals(
        due_amount=Decimal(due_amount), due_count=int(due_count), paid_amount=Decimal(paid_amount), paid_count=int(paid_count)
    )


async def list_commissions(
    db: AsyncSession, page: int, page_size: int, status_filter: str | None, partner_id: uuid.UUID | None
) -> tuple[list[CommissionOut], int, CommissionTotals]:
    """Vue plateforme. Les totaux portent sur le partenaire filtré (ou sur tous), tous statuts."""
    await set_platform_wide_context(db)
    query = _listing_query()
    if status_filter is not None:
        query = query.where(PartnerCommission.status == status_filter)
    if partner_id is not None:
        query = query.where(PartnerCommission.partner_id == partner_id)
    total = int((await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one())
    rows = (
        await db.execute(
            query.order_by(PartnerCommission.created_at.desc(), PartnerCommission.id).offset((page - 1) * page_size).limit(page_size)
        )
    ).all()
    return [_out(row) for row in rows], total, await _totals(db, partner_id)


async def list_partner_commissions(db: AsyncSession, partner: Partner, limit: int = 500) -> tuple[list[CommissionOut], CommissionTotals]:
    """Vue partenaire : uniquement les commissions de CE partenaire (filtre explicite)."""
    await set_platform_wide_context(db)
    rows = (
        await db.execute(
            _listing_query()
            .where(PartnerCommission.partner_id == partner.id)
            .order_by(PartnerCommission.created_at.desc(), PartnerCommission.id)
            .limit(limit)
        )
    ).all()
    return [_out(row) for row in rows], await _totals(db, partner.id)


# --- Versement, annulation, taux -------------------------------------------------------------------
def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _commit(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.commit()
    await apply_tenant_context(db, user_id)


async def mark_paid(db: AsyncSession, user: User, payload: MarkPaidInput, now: datetime) -> list[uuid.UUID]:
    """Marque comme versées des commissions DUES d'UN SEUL partenaire, avec le moyen et la référence
    du versement fait hors application. Renvoyer exactement le même versement (double clic) est sans
    effet ; toute autre commission déjà versée ou annulée est refusée."""
    user_id = user.id
    await set_platform_wide_context(db)
    rows = list(
        (
            await db.execute(
                select(PartnerCommission)
                .where(PartnerCommission.id.in_(payload.commission_ids))
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalars()
    )
    if len(rows) != len(payload.commission_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commission not found")
    if len({row.partner_id for row in rows}) != 1:
        raise _conflict("A settlement covers the commissions of a single partner")
    same_settlement = all(
        row.status == COMMISSION_STATUS_PAID
        and row.settlement_method == payload.method
        and row.settlement_reference == payload.reference
        for row in rows
    )
    if same_settlement:
        return [row.id for row in rows]
    if any(row.status != COMMISSION_STATUS_DUE for row in rows):
        raise _conflict("Only due commissions can be marked as paid")
    for row in rows:
        row.status = COMMISSION_STATUS_PAID
        row.paid_at = now
        row.paid_by = user_id
        row.settlement_method = payload.method
        row.settlement_reference = payload.reference
        await audit_service.record_audit_event(
            db,
            school_id=row.school_id,
            organization_id=row.organization_id,
            actor_user_id=user_id,
            action=audit_service.ACTION_PARTNER_COMMISSION_PAID,
            entity_type=audit_service.ENTITY_PARTNER_COMMISSION,
            entity_id=row.id,
            summary=f"Commission de {row.amount} {row.currency} versée au partenaire ({payload.method}, réf. {payload.reference})",
            metadata={"partner_id": str(row.partner_id), "method": payload.method, "reference": payload.reference},
        )
    ids = [row.id for row in rows]
    await _commit(db, user_id)
    return ids


async def cancel(db: AsyncSession, user: User, commission_id: uuid.UUID, reason: str, now: datetime) -> uuid.UUID:
    user_id = user.id
    await set_platform_wide_context(db)
    row = (
        await db.execute(
            select(PartnerCommission)
            .where(PartnerCommission.id == commission_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Commission not found")
    if row.status != COMMISSION_STATUS_DUE:
        raise _conflict("Only a due commission can be cancelled")
    row.status = COMMISSION_STATUS_CANCELLED
    row.cancelled_at = now
    row.cancelled_by = user_id
    row.cancel_reason = reason
    await audit_service.record_audit_event(
        db,
        school_id=row.school_id,
        organization_id=row.organization_id,
        actor_user_id=user_id,
        action=audit_service.ACTION_PARTNER_COMMISSION_CANCELLED,
        entity_type=audit_service.ENTITY_PARTNER_COMMISSION,
        entity_id=row.id,
        summary=f"Commission de {row.amount} {row.currency} annulée : {reason}",
        metadata={"partner_id": str(row.partner_id), "reason": reason},
    )
    await _commit(db, user_id)
    return row.id


async def set_partner_rate(db: AsyncSession, user: User, partner_id: uuid.UUID, rate: Decimal, now: datetime) -> Partner:
    """Nouveau taux pour les PROCHAINES commissions de ce partenaire ; les commissions existantes
    gardent leur taux. Tracé sur la fiche du partenaire (pas d'école, donc pas d'audit_logs)."""
    user_id = user.id
    await set_platform_wide_context(db)
    partner = (
        await db.execute(select(Partner).where(Partner.id == partner_id).with_for_update())
    ).scalar_one_or_none()
    if partner is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Partner not found")
    partner.commission_rate = rate
    partner.commission_rate_updated_at = now
    partner.commission_rate_updated_by = user_id
    await _commit(db, user_id)
    await set_platform_wide_context(db)
    await db.refresh(partner)
    return partner
