"""Abonnements des écoles (Phase 29, lot A) — grille de prix, factures, paiements, périodes.

Voir docs/phases/PHASE_29_SCHOOL_SUBSCRIPTIONS_DISCOVERY.md. Module DISTINCT de `fees` (l'école qui
facture ses élèves) : ici, c'est EduLinkage qui facture l'école. Aucune table de `fees`, `cash` ou
`partners` n'est réutilisée ni modifiée.

Isolation (migration 0027) :
- `subscription_invoices`, `subscription_payments`, `school_subscription_periods` portent
  school_id + organization_id, avec la policy RLS générique `{table}_tenant_isolation`, comme toutes
  les tables tenant ;
- `subscription_price_grids` / `subscription_price_lines` n'appartiennent à aucune organisation :
  lecture ouverte (un prix n'est pas une donnée sensible, et l'école doit pouvoir calculer son
  aperçu), écriture réservée au contexte platform-wide ;
- `subscription_invoice_number_counters` ne contient qu'une année et un compteur (aucune donnée
  tenant) : pas de RLS, pour que la numérotation séquentielle reste possible depuis une session
  d'école.

Montants : Numeric(12, 2) comme le reste du dépôt, mais toujours ENTIERS (CHECK), car le XOF n'a
pas de centimes et PayGate ne traite que des FCFA entiers.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

SUBSCRIPTION_CURRENCY = "XOF"

GRID_STATUS_DRAFT = "DRAFT"
GRID_STATUS_ACTIVE = "ACTIVE"
GRID_STATUS_ARCHIVED = "ARCHIVED"
GRID_STATUSES = (GRID_STATUS_DRAFT, GRID_STATUS_ACTIVE, GRID_STATUS_ARCHIVED)

INVOICE_STATUS_QUOTE_REQUIRED = "QUOTE_REQUIRED"
INVOICE_STATUS_ISSUED = "ISSUED"
INVOICE_STATUS_PAID = "PAID"
INVOICE_STATUS_EXPIRED = "EXPIRED"
INVOICE_STATUS_CANCELLED = "CANCELLED"
INVOICE_STATUSES = (
    INVOICE_STATUS_QUOTE_REQUIRED,
    INVOICE_STATUS_ISSUED,
    INVOICE_STATUS_PAID,
    INVOICE_STATUS_EXPIRED,
    INVOICE_STATUS_CANCELLED,
)
OPEN_INVOICE_STATUSES = (INVOICE_STATUS_QUOTE_REQUIRED, INVOICE_STATUS_ISSUED)

PAYMENT_PROVIDER_PAYGATE = "PAYGATE"
PAYMENT_PROVIDER_MANUAL = "MANUAL"
PAYMENT_PROVIDERS = (PAYMENT_PROVIDER_PAYGATE, PAYMENT_PROVIDER_MANUAL)
PAYMENT_METHODS = ("FLOOZ", "TMONEY", "BANK_TRANSFER", "CASH", "OTHER")
PAYMENT_STATUS_SUCCEEDED = "SUCCEEDED"
# INITIATED/PENDING/FAILED/EXPIRED/ANOMALY servent au paiement en ligne (lot B) : déclarés dès
# maintenant pour que la table n'ait pas à changer de contrainte au lot B.
PAYMENT_STATUSES = ("INITIATED", "PENDING", PAYMENT_STATUS_SUCCEEDED, "FAILED", "EXPIRED", "ANOMALY")

PERIOD_KINDS = ("FREE_TRIAL", "PAID")


def _sql_in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


class SubscriptionPriceGrid(Base):
    """Une version de la grille. Une seule `ACTIVE` à la fois (index unique partiel). Seule une
    grille `DRAFT` est modifiable ; une grille activée puis archivée n'est plus jamais modifiée :
    chaque facture référence la version qui a servi à la calculer.

    Trace : `created_by`/`activated_by` et leurs dates. Le journal d'audit (`audit_logs`) exige une
    école ; une grille n'en a pas, d'où ces colonnes plutôt qu'une entrée d'audit."""

    __tablename__ = "subscription_price_grids"
    __table_args__ = (
        CheckConstraint(f"status IN ({_sql_in(GRID_STATUSES)})", name="ck_subscription_grid_status"),
        CheckConstraint(f"currency = '{SUBSCRIPTION_CURRENCY}'", name="ck_subscription_grid_currency"),
        CheckConstraint(
            "status = 'DRAFT' OR (activated_at IS NOT NULL AND activated_by IS NOT NULL)",
            name="ck_subscription_grid_activation_traced",
        ),
        CheckConstraint("status <> 'ARCHIVED' OR archived_at IS NOT NULL", name="ck_subscription_grid_archive_traced"),
        CheckConstraint("length(btrim(label)) > 0", name="ck_subscription_grid_label_present"),
        Index(
            "uq_subscription_price_grids_one_active",
            "status",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=SUBSCRIPTION_CURRENCY)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=GRID_STATUS_DRAFT)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    activated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SubscriptionPriceLine(Base):
    """Une ligne par couple (durée, tranche) : 3 durées × 4 tranches = 12 lignes par grille.
    `base_amount` est le forfait de base de la durée (identique pour les 4 tranches d'une même durée,
    garanti par le service) ; `supplement_amount` est le supplément de la tranche (0 pour la tranche
    de base, garanti en base)."""

    __tablename__ = "subscription_price_lines"
    __table_args__ = (
        UniqueConstraint("grid_id", "period_months", "tier", name="uq_subscription_price_line"),
        CheckConstraint("period_months IN (3, 6, 12)", name="ck_subscription_price_line_period"),
        CheckConstraint("tier BETWEEN 0 AND 3", name="ck_subscription_price_line_tier"),
        CheckConstraint(
            "base_amount > 0 AND base_amount = trunc(base_amount)", name="ck_subscription_price_line_base_whole"
        ),
        CheckConstraint(
            "supplement_amount >= 0 AND supplement_amount = trunc(supplement_amount)",
            name="ck_subscription_price_line_supplement_whole",
        ),
        CheckConstraint("tier > 0 OR supplement_amount = 0", name="ck_subscription_price_line_base_tier_no_supplement"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    grid_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_price_grids.id", ondelete="CASCADE"), nullable=False
    )
    period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    supplement_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)


class SubscriptionInvoiceNumberCounter(Base):
    """Compteur de numérotation séquentielle SANS TROU, par année : la ligne est verrouillée
    (`UPDATE … RETURNING`) dans la transaction qui émet la facture. Un rollback annule donc aussi
    l'incrément. Aucune donnée tenant : pas de RLS (voir docstring du module)."""

    __tablename__ = "subscription_invoice_number_counters"
    __table_args__ = (CheckConstraint("last_value > 0", name="ck_subscription_invoice_counter_positive"),)

    year: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False)


class SubscriptionInvoice(Base):
    """Facture d'abonnement FIGÉE à l'émission : effectif, tranche, version de grille, montants,
    durée. Un devis (au-delà de 1 000 élèves) est créé en `QUOTE_REQUIRED`, sans numéro ni montant,
    jusqu'à ce que la plateforme saisisse le montant.

    Une seule facture « ouverte » (`QUOTE_REQUIRED` ou `ISSUED`) par école (index unique partiel).
    Une facture `ISSUED` dont `expires_at` est dépassé est expirée : elle passe en `EXPIRED` dès
    qu'une nouvelle facture est demandée pour l'école (expiration paresseuse, sous verrou ; la tâche
    quotidienne du lot C le fera aussi) et elle n'est plus payable dans tous les cas."""

    __tablename__ = "subscription_invoices"
    __table_args__ = (
        CheckConstraint(f"status IN ({_sql_in(INVOICE_STATUSES)})", name="ck_subscription_invoice_status"),
        CheckConstraint("period_months IN (3, 6, 12)", name="ck_subscription_invoice_period"),
        CheckConstraint("student_count >= 0", name="ck_subscription_invoice_student_count"),
        CheckConstraint(f"currency = '{SUBSCRIPTION_CURRENCY}'", name="ck_subscription_invoice_currency"),
        # Facture calculée par la grille (tranche connue) ou devis (tout à NULL ensemble).
        CheckConstraint(
            "(tier IS NULL) = (grid_id IS NULL) AND (tier IS NULL) = (base_amount IS NULL) "
            "AND (tier IS NULL) = (supplement_amount IS NULL)",
            name="ck_subscription_invoice_grid_fields_together",
        ),
        CheckConstraint(
            "tier IS NULL OR total_amount IS NULL OR total_amount = base_amount + supplement_amount",
            name="ck_subscription_invoice_total_formula",
        ),
        CheckConstraint(
            "total_amount IS NULL OR (total_amount > 0 AND total_amount = trunc(total_amount))",
            name="ck_subscription_invoice_total_whole",
        ),
        # Émission : numéro, date d'émission, date d'expiration et montant total vont ensemble.
        CheckConstraint(
            "(number IS NULL) = (issued_at IS NULL) AND (number IS NULL) = (expires_at IS NULL) "
            "AND (number IS NULL) = (total_amount IS NULL)",
            name="ck_subscription_invoice_issue_fields_together",
        ),
        CheckConstraint(
            "status NOT IN ('ISSUED', 'PAID', 'EXPIRED') OR number IS NOT NULL",
            name="ck_subscription_invoice_issued_has_number",
        ),
        CheckConstraint("status <> 'QUOTE_REQUIRED' OR number IS NULL", name="ck_subscription_invoice_quote_unnumbered"),
        CheckConstraint("(status = 'PAID') = (paid_at IS NOT NULL)", name="ck_subscription_invoice_paid_at"),
        CheckConstraint(
            "status <> 'CANCELLED' OR (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND cancel_reason IS NOT NULL AND length(btrim(cancel_reason)) > 0)",
            name="ck_subscription_invoice_cancel_traced",
        ),
        UniqueConstraint("number", name="uq_subscription_invoices_number"),
        UniqueConstraint("school_id", "idempotency_key", name="uq_subscription_invoices_idempotency"),
        Index(
            "uq_subscription_invoices_one_open_per_school",
            "school_id",
            unique=True,
            postgresql_where=text("status IN ('QUOTE_REQUIRED', 'ISSUED')"),
        ),
        Index("ix_subscription_invoices_school_created", "school_id", "created_at"),
        Index("ix_subscription_invoices_status_created", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    period_months: Mapped[int] = mapped_column(Integer, nullable=False)
    student_count: Mapped[int] = mapped_column(Integer, nullable=False)
    tier: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grid_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_price_grids.id", ondelete="RESTRICT"), nullable=True
    )
    base_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    supplement_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=SUBSCRIPTION_CURRENCY)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quote_amount_set_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SubscriptionPayment(Base):
    """Paiement (ou tentative de paiement en ligne, lot B) d'une facture. Lot A : uniquement des
    paiements `MANUAL` enregistrés par la plateforme, directement `SUCCEEDED`.

    Au plus un paiement `SUCCEEDED` et au plus une tentative en cours (`INITIATED`/`PENDING`) par
    facture (index uniques partiels). `identifier` : identifiant aléatoire généré côté serveur (au
    lot B, c'est celui transmis à PayGate) — jamais devinable, jamais l'id de la facture."""

    __tablename__ = "subscription_payments"
    __table_args__ = (
        CheckConstraint(f"provider IN ({_sql_in(PAYMENT_PROVIDERS)})", name="ck_subscription_payment_provider"),
        CheckConstraint(f"method IN ({_sql_in(PAYMENT_METHODS)})", name="ck_subscription_payment_method"),
        CheckConstraint(f"status IN ({_sql_in(PAYMENT_STATUSES)})", name="ck_subscription_payment_status"),
        CheckConstraint(f"currency = '{SUBSCRIPTION_CURRENCY}'", name="ck_subscription_payment_currency"),
        CheckConstraint("amount > 0 AND amount = trunc(amount)", name="ck_subscription_payment_amount_whole"),
        CheckConstraint(
            "provider <> 'MANUAL' OR (recorded_by IS NOT NULL AND reference IS NOT NULL "
            "AND length(btrim(reference)) > 0)",
            name="ck_subscription_payment_manual_traced",
        ),
        CheckConstraint(
            "status <> 'SUCCEEDED' OR confirmed_at IS NOT NULL", name="ck_subscription_payment_confirmed_at"
        ),
        CheckConstraint(
            "payer_phone_last4 IS NULL OR payer_phone_last4 ~ '^[0-9]{4}$'",
            name="ck_subscription_payment_phone_last4",
        ),
        UniqueConstraint("identifier", name="uq_subscription_payments_identifier"),
        UniqueConstraint("tx_reference", name="uq_subscription_payments_tx_reference"),
        UniqueConstraint("invoice_id", "idempotency_key", name="uq_subscription_payments_idempotency"),
        Index(
            "uq_subscription_payments_one_succeeded_per_invoice",
            "invoice_id",
            unique=True,
            postgresql_where=text("status = 'SUCCEEDED'"),
        ),
        Index(
            "uq_subscription_payments_one_in_progress_per_invoice",
            "invoice_id",
            unique=True,
            postgresql_where=text("status IN ('INITIATED', 'PENDING')"),
        ),
        Index("ix_subscription_payments_school_created", "school_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_invoices.id", ondelete="RESTRICT"), nullable=False
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default=SUBSCRIPTION_CURRENCY)
    identifier: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tx_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payer_phone_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    provider_status_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    initiated_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SchoolSubscriptionPeriod(Base):
    """Période couverte, payée (`PAID`, liée à sa facture) ou gratuite (`FREE_TRIAL`, sans facture).
    Un seul trimestre gratuit par école, à vie (index unique partiel). Aucun chevauchement : garanti
    par le service, sous verrou consultatif par école (`service.lock_school_subscription`), pour
    le paiement comme pour l'attribution du trimestre gratuit."""

    __tablename__ = "school_subscription_periods"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_sql_in(PERIOD_KINDS)})", name="ck_school_subscription_period_kind"),
        CheckConstraint("ends_on >= starts_on", name="ck_school_subscription_period_dates"),
        CheckConstraint("(kind = 'PAID') = (invoice_id IS NOT NULL)", name="ck_school_subscription_period_invoice"),
        UniqueConstraint("invoice_id", name="uq_school_subscription_periods_invoice"),
        Index(
            "uq_school_subscription_periods_one_free_trial",
            "school_id",
            unique=True,
            postgresql_where=text("kind = 'FREE_TRIAL'"),
        ),
        Index("ix_school_subscription_periods_school_starts", "school_id", "starts_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_invoices.id", ondelete="RESTRICT"), nullable=True
    )
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


REMINDER_STAGES = ("J30", "J7", "J0", "INVOICE_J3")


class SubscriptionReminder(Base):
    """Phase 29, lot C — idempotence des rappels d'abonnement : une ligne par (cible, palier), créée
    dans la même transaction que les notifications qu'elle a déclenchées. Cible : la dernière
    période de la couverture en cours (paliers J30, J7, J0) ou une facture émise non payée (palier
    INVOICE_J3). Index uniques partiels : jamais deux rappels du même palier pour la même cible,
    même si la tâche tourne deux fois en même temps."""

    __tablename__ = "subscription_reminders"
    __table_args__ = (
        CheckConstraint(f"stage IN ({_sql_in(REMINDER_STAGES)})", name="ck_subscription_reminder_stage"),
        CheckConstraint("(period_id IS NULL) <> (invoice_id IS NULL)", name="ck_subscription_reminder_one_target"),
        CheckConstraint("(stage = 'INVOICE_J3') = (invoice_id IS NOT NULL)", name="ck_subscription_reminder_stage_target"),
        CheckConstraint("recipients_count >= 0", name="ck_subscription_reminder_recipients"),
        Index(
            "uq_subscription_reminders_period_stage",
            "period_id",
            "stage",
            unique=True,
            postgresql_where=text("period_id IS NOT NULL"),
        ),
        Index(
            "uq_subscription_reminders_invoice_stage",
            "invoice_id",
            "stage",
            unique=True,
            postgresql_where=text("invoice_id IS NOT NULL"),
        ),
        Index("ix_subscription_reminders_school_created", "school_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    period_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("school_subscription_periods.id", ondelete="CASCADE"), nullable=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscription_invoices.id", ondelete="CASCADE"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(16), nullable=False)
    recipients_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
