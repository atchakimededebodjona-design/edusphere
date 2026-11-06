"""Caisse scolaire, lot 3 — sessions de caisse, mouvements d'espèces et comptages physiques.

Construit AUTOUR du flux de paiement existant (fees/service.py::record_payment), jamais en
parallèle : un paiement reste un `Payment` ; une session ne fait que rattacher (Payment.cash_session_id)
les paiements CASH de son caissier et y ajouter ce qui n'est pas un paiement d'élève (fonds initial,
mouvements, comptage). Même convention que le reste du dépôt : school_id + organization_id sur
chaque table (RLS `{table}_tenant_isolation`, migration 0026), montants Numeric(12, 2), jamais float.

Règle du solde théorique (UNIQUE source : cash/service.py::expected_amount_sql) :
    expected = opening_amount
             + Σ Payment.amount  (method = CASH, status = COMPLETED, cash_session_id = session)
             + Σ CashMovement.amount (direction = IN)
             − Σ CashMovement.amount (direction = OUT)
Direction d'un mouvement : CASH_IN -> IN ; CASH_OUT, BANK_DEPOSIT -> OUT ; OTHER -> choisie
explicitement à la saisie (obligatoire). Un paiement annulé (CANCELLED) ne contribue jamais.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

CASH_SESSION_STATUSES = ("OPEN", "CLOSED")
CASH_MOVEMENT_TYPES = ("CASH_IN", "CASH_OUT", "BANK_DEPOSIT", "OTHER")
CASH_MOVEMENT_DIRECTIONS = ("IN", "OUT")
# Direction imposée par type ; OTHER n'en a pas (la saisie doit la préciser).
CASH_MOVEMENT_FIXED_DIRECTIONS: dict[str, str] = {"CASH_IN": "IN", "CASH_OUT": "OUT", "BANK_DEPOSIT": "OUT"}
# Motifs d'écart (catalogue fermé côté code, comme `notifications.type`) — la note libre reste
# obligatoire en plus du motif dès qu'un écart existe.
CASH_VARIANCE_REASONS = (
    "COUNTING_ERROR",
    "CHANGE_ERROR",
    "UNRECORDED_PAYMENT",
    "UNRECORDED_MOVEMENT",
    "LOSS_OR_THEFT",
    "OTHER",
)


class CashSession(Base):
    __tablename__ = "cash_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_cash_session_status"),
        CheckConstraint("opening_amount >= 0", name="ck_cash_session_opening_non_negative"),
        CheckConstraint(
            "status = 'OPEN' OR (closed_at IS NOT NULL AND closed_by IS NOT NULL AND expected_amount IS NOT NULL "
            "AND counted_amount IS NOT NULL AND variance_amount IS NOT NULL)",
            name="ck_cash_session_closed_complete",
        ),
        CheckConstraint(
            "variance_amount IS NULL OR variance_amount = counted_amount - expected_amount",
            name="ck_cash_session_variance_formula",
        ),
        CheckConstraint(
            "variance_amount IS NULL OR variance_amount = 0 OR (variance_reason IS NOT NULL AND variance_note IS NOT NULL)",
            name="ck_cash_session_variance_justified",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    cashier_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    opened_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    opening_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    # Figés à la clôture (jamais recalculés ensuite) : le rapport d'une session close reste celui
    # qui a été validé, même si un paiement est annulé plus tard par un superviseur.
    expected_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    counted_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    variance_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    variance_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    variance_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CashMovement(Base):
    """Entrée/sortie d'espèces qui n'est PAS un paiement d'élève (apport de monnaie, dépense,
    versement en banque...). Immuable : jamais modifiée ni supprimée (aucune route ne le permet)."""

    __tablename__ = "cash_movements"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_cash_movement_amount_positive"),
        CheckConstraint("type IN ('CASH_IN', 'CASH_OUT', 'BANK_DEPOSIT', 'OTHER')", name="ck_cash_movement_type"),
        CheckConstraint(
            "(type = 'CASH_IN' AND direction = 'IN') OR (type IN ('CASH_OUT', 'BANK_DEPOSIT') AND direction = 'OUT') "
            "OR (type = 'OTHER' AND direction IN ('IN', 'OUT'))",
            name="ck_cash_movement_direction",
        ),
        CheckConstraint("length(btrim(reason)) > 0", name="ck_cash_movement_reason_present"),
        # Double clic / nouvelle tentative réseau : même clé = même mouvement (jamais un doublon).
        UniqueConstraint("cash_session_id", "idempotency_key", name="uq_cash_movement_idempotency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cash_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cash_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CashCount(Base):
    """Comptage physique par coupure. Plusieurs comptages possibles tant que la session est OPEN
    (recomptage) : le plus récent fait foi à la clôture. Total calculé côté serveur uniquement."""

    __tablename__ = "cash_counts"
    __table_args__ = (CheckConstraint("total_amount >= 0", name="ck_cash_count_total_non_negative"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cash_session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cash_sessions.id", ondelete="RESTRICT"), nullable=False
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    counted_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class CashCountLine(Base):
    __tablename__ = "cash_count_lines"
    __table_args__ = (
        UniqueConstraint("cash_count_id", "denomination", name="uq_cash_count_line_denomination"),
        CheckConstraint("denomination > 0", name="ck_cash_count_line_denomination_positive"),
        CheckConstraint("quantity >= 0", name="ck_cash_count_line_quantity_non_negative"),
        CheckConstraint("line_total = denomination * quantity", name="ck_cash_count_line_total"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cash_count_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("cash_counts.id", ondelete="CASCADE"), nullable=False
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    denomination: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
