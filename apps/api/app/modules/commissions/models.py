"""Commissions des partenaires commerciaux (migration 0031, décisions du 2026-11-15).

Règles :
- un partenaire touche un pourcentage (`partners.commission_rate`, 20 par défaut, réglable par
  partenaire) du montant **HT** de chaque facture d'abonnement **payée et confirmée** d'une école
  qu'il a inscrite (`partner_school_enrollments.commission_eligible`), à chaque paiement, sans
  limite de durée ;
- aucune commission pour un paiement confirmé pendant que le partenaire est suspendu ;
- versement **manuel** par la plateforme : la commission passe de `DUE` à `PAID` avec le moyen et
  la référence du versement ; une commission due peut être annulée avec un motif.

Une seule commission par facture (et par paiement), garanti en base (UNIQUE). Le taux et la base HT
sont FIGÉS sur la commission : un changement de taux ne modifie jamais une commission existante.

RLS : « plateforme seulement », comme `partners` — les écoles ne voient jamais les commissions ; un
partenaire ne lit que les siennes, via un filtre explicite sur SON `partner_id` (motif
partners/service.py).
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

COMMISSION_STATUS_DUE = "DUE"
COMMISSION_STATUS_PAID = "PAID"
COMMISSION_STATUS_CANCELLED = "CANCELLED"
COMMISSION_STATUSES = (COMMISSION_STATUS_DUE, COMMISSION_STATUS_PAID, COMMISSION_STATUS_CANCELLED)
SETTLEMENT_METHODS = ("MOBILE_MONEY", "BANK_TRANSFER", "CASH", "OTHER")


def _sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class PartnerCommission(Base):
    __tablename__ = "partner_commissions"
    __table_args__ = (
        CheckConstraint(f"status IN ({_sql_in(COMMISSION_STATUSES)})", name="ck_partner_commission_status"),
        CheckConstraint("currency = 'XOF'", name="ck_partner_commission_currency"),
        CheckConstraint("rate >= 0 AND rate <= 100", name="ck_partner_commission_rate"),
        CheckConstraint("base_amount_excl_vat >= 0", name="ck_partner_commission_base"),
        CheckConstraint("amount >= 0 AND amount = trunc(amount)", name="ck_partner_commission_amount_whole"),
        CheckConstraint(
            f"settlement_method IS NULL OR settlement_method IN ({_sql_in(SETTLEMENT_METHODS)})",
            name="ck_partner_commission_settlement_method",
        ),
        CheckConstraint(
            "(status = 'PAID') = (paid_at IS NOT NULL) AND (status <> 'PAID' OR (paid_by IS NOT NULL "
            "AND settlement_method IS NOT NULL AND settlement_reference IS NOT NULL "
            "AND length(btrim(settlement_reference)) > 0))",
            name="ck_partner_commission_paid_traced",
        ),
        CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) AND (status <> 'CANCELLED' OR "
            "(cancelled_by IS NOT NULL AND cancel_reason IS NOT NULL AND length(btrim(cancel_reason)) > 0))",
            name="ck_partner_commission_cancel_traced",
        ),
        UniqueConstraint("invoice_id", name="uq_partner_commissions_invoice"),
        UniqueConstraint("payment_id", name="uq_partner_commissions_payment"),
        Index("ix_partner_commissions_partner_status", "partner_id", "status"),
        Index("ix_partner_commissions_created", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("partners.id", ondelete="RESTRICT"), nullable=False
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="RESTRICT"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="RESTRICT"), nullable=False
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_invoices.id", ondelete="RESTRICT"), nullable=False
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_payments.id", ondelete="RESTRICT"), nullable=False
    )
    base_amount_excl_vat: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="XOF")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=COMMISSION_STATUS_DUE)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    settlement_method: Mapped[str | None] = mapped_column(String(16), nullable=True)
    settlement_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
