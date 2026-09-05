import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Phase 19 (School Fees & Billing). Même convention que tous les autres modules métier :
# school_id + organization_id dénormalisés sur chaque table (RLS, voir migration 0009_fees.py).
#
# Tous les montants sont des Numeric(12, 2) — jamais float — pour éviter toute erreur d'arrondi
# sur des données financières. C'est la première introduction d'un type monétaire dans ce dépôt
# (aucune convention préexistante à réutiliser) : Numeric/Decimal est le choix le plus sûr,
# cohérent avec l'usage déjà fait de `Decimal` pour les calculs de moyennes (grades/service.py).
#
# Volontairement 5 tables, pas 7 (voir docs/phases/PHASE_19_DISCOVERY.md §14) : pas d'`Invoice`
# séparée (StudentFee sert de ligne de dette ET de mini-facture), pas de `Receipt` séparée (ses
# champs vivent directement sur Payment, qui lui est toujours 1:1).

PAYMENT_METHODS = ("CASH", "BANK_TRANSFER", "CHEQUE", "AGENT_DEPOSIT", "OTHER")
STUDENT_FEE_STATUSES = ("PENDING", "PARTIALLY_PAID", "PAID", "CANCELLED")
PAYMENT_STATUSES = ("COMPLETED", "CANCELLED")
FEE_SCOPE_TYPES = ("SCHOOL", "CLASS", "LEVEL")


class FeeCategory(Base):
    __tablename__ = "fee_categories"
    __table_args__ = (UniqueConstraint("school_id", "name", name="uq_fee_category_school_name"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class FeeSchedule(Base):
    """Barème : un montant pour une portée (école entière / une classe / un niveau) et une année
    académique. L'affectation aux élèves (StudentFee) se fait par une action explicite
    (`generate_student_fees`), jamais automatiquement — voir PHASE_19_DISCOVERY.md §15."""

    __tablename__ = "fee_schedules"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_fee_schedule_amount_positive"),
        CheckConstraint(
            "(scope_type = 'SCHOOL' AND scope_class_id IS NULL AND scope_education_level_id IS NULL) OR "
            "(scope_type = 'CLASS' AND scope_class_id IS NOT NULL AND scope_education_level_id IS NULL) OR "
            "(scope_type = 'LEVEL' AND scope_education_level_id IS NOT NULL AND scope_class_id IS NULL)",
            name="ck_fee_schedule_scope_consistency",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fee_category_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fee_categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Copiée depuis School.currency à la création (affichage uniquement — EduSphere reste
    # mono-devise par école au MVP, voir PHASE_19_DISCOVERY.md §31).
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_class_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    scope_education_level_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("education_levels.id", ondelete="CASCADE"), nullable=True, index=True
    )
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class StudentFee(Base):
    """Obligation financière d'un élève pour un barème donné — sert à la fois de ligne de dette
    et de mini-facture (pas d'entité `Invoice` séparée, voir PHASE_19_DISCOVERY.md §14).
    `status` est dérivé des paiements alloués (voir fees/service.py::_refresh_student_fee_status)
    mais persisté pour permettre un requêtage direct."""

    __tablename__ = "student_fees"
    __table_args__ = (
        UniqueConstraint("student_id", "fee_schedule_id", name="uq_student_fee"),
        CheckConstraint("amount_due > 0", name="ck_student_fee_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    fee_schedule_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("fee_schedules.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount_due: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Phase 20 (durcissement pré-pilote) : nullable — les lignes créées par `generate_student_fees`
    # ne sont l'œuvre d'aucun utilisateur en particulier (action système déclenchée par un
    # administrateur sur le barème, pas une modification de CETTE ligne). Renseigné uniquement par
    # `PATCH /student-fees/{id}` (ajustement manuel), qui exige aussi une `note` non vide dès que
    # `amount_due` change — voir fees/router.py::update_student_fee.
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Payment(Base):
    """Paiement manuel enregistré par le personnel de l'école — porte aussi les champs du reçu
    (`receipt_number`, `pdf_path`), pas d'entité `Receipt` séparée (toujours 1:1, jamais brouillon,
    voir PHASE_19_DISCOVERY.md §14/§23). Immutable une fois `COMPLETED` : seule une transition
    vers `CANCELLED` est permise (§18 — jamais de modification en place d'un paiement existant,
    l'historique financier ne doit jamais être réécrit silencieusement)."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("school_id", "idempotency_key", name="uq_payment_idempotency"),
        UniqueConstraint("school_id", "receipt_number", name="uq_payment_receipt_number"),
        CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Fourni par le client (web admin) — protection contre le double-clic/double-soumission
    # (voir fees/service.py::record_payment). Aucun précédent d'idempotency-key dans ce dépôt :
    # première introduction de ce motif, signalée comme telle.
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    paid_at: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    payer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="COMPLETED")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    cancellation_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    receipt_number: Mapped[str] = mapped_column(String(32), nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PaymentAllocation(Base):
    """Répartition d'un paiement sur une ou plusieurs `StudentFee`. La somme des allocations d'un
    paiement doit exactement égaler son montant (pas de trop-perçu au MVP, voir
    PHASE_19_DISCOVERY.md §15/§20) ; la somme des allocations actives d'une `StudentFee` ne peut
    jamais dépasser son `amount_due` (appliqué sous verrou, voir fees/service.py::record_payment)."""

    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint("payment_id", "student_fee_id", name="uq_payment_allocation"),
        CheckConstraint("amount > 0", name="ck_payment_allocation_amount_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("payments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_fee_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("student_fees.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
