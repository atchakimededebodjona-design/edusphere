"""school subscriptions (Phase 29, lot A — abonnements des écoles, sans paiement en ligne)

Strictement additive : aucune migration précédente modifiée, aucune table existante modifiée,
aucune donnée existante réécrite (seule la DESCRIPTION de la permission existante
`platform.subscriptions.read` est mise à jour, l'ancienne étant restaurée au downgrade — même motif
que `payments.manage` en 0025).

1. Tables (voir app/modules/subscriptions/models.py, contraintes identiques) :
   - `subscription_price_grids`, `subscription_price_lines` : grille versionnée (une seule ACTIVE).
     Aucune organisation : RLS ENABLE+FORCE avec deux policies — lecture ouverte
     (`{table}_read_all`, un prix n'est pas une donnée sensible et l'école calcule son aperçu),
     écriture réservée au contexte platform-wide (`{table}_platform_write`) ;
   - `subscription_invoice_number_counters` : compteur annuel de numérotation sans trou. Aucune
     donnée tenant : PAS de RLS (une session d'école doit pouvoir émettre une facture) ;
   - `subscription_invoices`, `subscription_payments`, `school_subscription_periods` :
     school_id + organization_id, RLS `{table}_tenant_isolation` identique aux tables tenant
     existantes (migration 0026).
2. Index uniques partiels (concurrence, en plus des verrous applicatifs) : une grille ACTIVE ; une
   facture ouverte par école ; un paiement SUCCEEDED et une tentative en cours par facture ; un
   trimestre gratuit par école.
3. Permissions (rbac/seed.py::SUBSCRIPTION_*) : `subscriptions.read|pay` (école),
   `platform.subscriptions.manage` (plateforme). Aucune permission existante retirée.

Downgrade (ordre inverse) : description et permissions, puis policies et tables. Les grilles,
factures, paiements et périodes éventuels sont perdus (inévitable pour retirer ces tables).

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-12
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import (
    PLATFORM_SUBSCRIPTIONS_READ_DESCRIPTION,
    PLATFORM_SUBSCRIPTIONS_READ_PREVIOUS_DESCRIPTION,
    SUBSCRIPTION_PERMISSIONS,
    SUBSCRIPTION_PLATFORM_PERMISSIONS,
    SUBSCRIPTION_PLATFORM_ROLE_PERMISSIONS,
    SUBSCRIPTION_ROLE_PERMISSIONS,
)

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TENANT_TABLES = ["subscription_invoices", "subscription_payments", "school_subscription_periods"]
GRID_TABLES = ["subscription_price_grids", "subscription_price_lines"]
_ALL_PERMISSIONS: dict[str, str] = {**SUBSCRIPTION_PERMISSIONS, **SUBSCRIPTION_PLATFORM_PERMISSIONS}

_PLATFORM_WIDE = "current_setting('app.is_platform_wide', true) = 'true'"


def _uuid_pk() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def _tenant_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
    ]


def _user_fk(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable
    )


def _timestamps(with_updated: bool = True) -> list[sa.Column]:
    columns = [sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]
    if with_updated:
        columns.append(sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    return columns


def upgrade() -> None:
    # --- Grille de prix ----------------------------------------------------------------------------
    op.create_table(
        "subscription_price_grids",
        _uuid_pk(),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        _user_fk("created_by"),
        _user_fk("activated_by", nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'ARCHIVED')", name="ck_subscription_grid_status"),
        sa.CheckConstraint("currency = 'XOF'", name="ck_subscription_grid_currency"),
        sa.CheckConstraint(
            "status = 'DRAFT' OR (activated_at IS NOT NULL AND activated_by IS NOT NULL)",
            name="ck_subscription_grid_activation_traced",
        ),
        sa.CheckConstraint("status <> 'ARCHIVED' OR archived_at IS NOT NULL", name="ck_subscription_grid_archive_traced"),
        sa.CheckConstraint("length(btrim(label)) > 0", name="ck_subscription_grid_label_present"),
    )
    op.create_index(
        "uq_subscription_price_grids_one_active",
        "subscription_price_grids",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE'"),
    )

    op.create_table(
        "subscription_price_lines",
        _uuid_pk(),
        sa.Column(
            "grid_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_price_grids.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_months", sa.Integer, nullable=False),
        sa.Column("tier", sa.Integer, nullable=False),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("supplement_amount", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("grid_id", "period_months", "tier", name="uq_subscription_price_line"),
        sa.CheckConstraint("period_months IN (3, 6, 12)", name="ck_subscription_price_line_period"),
        sa.CheckConstraint("tier BETWEEN 0 AND 3", name="ck_subscription_price_line_tier"),
        sa.CheckConstraint(
            "base_amount > 0 AND base_amount = trunc(base_amount)", name="ck_subscription_price_line_base_whole"
        ),
        sa.CheckConstraint(
            "supplement_amount >= 0 AND supplement_amount = trunc(supplement_amount)",
            name="ck_subscription_price_line_supplement_whole",
        ),
        sa.CheckConstraint(
            "tier > 0 OR supplement_amount = 0", name="ck_subscription_price_line_base_tier_no_supplement"
        ),
    )

    # --- Compteur de numérotation (pas de RLS : aucune donnée tenant) --------------------------------
    op.create_table(
        "subscription_invoice_number_counters",
        sa.Column("year", sa.Integer, primary_key=True, autoincrement=False),
        sa.Column("last_value", sa.Integer, nullable=False),
        sa.CheckConstraint("last_value > 0", name="ck_subscription_invoice_counter_positive"),
    )

    # --- Factures ------------------------------------------------------------------------------------
    op.create_table(
        "subscription_invoices",
        _uuid_pk(),
        *_tenant_columns(),
        sa.Column("number", sa.String(32), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("period_months", sa.Integer, nullable=False),
        sa.Column("student_count", sa.Integer, nullable=False),
        sa.Column("tier", sa.Integer, nullable=True),
        sa.Column(
            "grid_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_price_grids.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("base_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("supplement_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        _user_fk("created_by"),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("quote_amount_set_by", nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("cancelled_by", nullable=True),
        sa.Column("cancel_reason", sa.Text, nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('QUOTE_REQUIRED', 'ISSUED', 'PAID', 'EXPIRED', 'CANCELLED')",
            name="ck_subscription_invoice_status",
        ),
        sa.CheckConstraint("period_months IN (3, 6, 12)", name="ck_subscription_invoice_period"),
        sa.CheckConstraint("student_count >= 0", name="ck_subscription_invoice_student_count"),
        sa.CheckConstraint("currency = 'XOF'", name="ck_subscription_invoice_currency"),
        sa.CheckConstraint(
            "(tier IS NULL) = (grid_id IS NULL) AND (tier IS NULL) = (base_amount IS NULL) "
            "AND (tier IS NULL) = (supplement_amount IS NULL)",
            name="ck_subscription_invoice_grid_fields_together",
        ),
        sa.CheckConstraint(
            "tier IS NULL OR total_amount IS NULL OR total_amount = base_amount + supplement_amount",
            name="ck_subscription_invoice_total_formula",
        ),
        sa.CheckConstraint(
            "total_amount IS NULL OR (total_amount > 0 AND total_amount = trunc(total_amount))",
            name="ck_subscription_invoice_total_whole",
        ),
        sa.CheckConstraint(
            "(number IS NULL) = (issued_at IS NULL) AND (number IS NULL) = (expires_at IS NULL) "
            "AND (number IS NULL) = (total_amount IS NULL)",
            name="ck_subscription_invoice_issue_fields_together",
        ),
        sa.CheckConstraint(
            "status NOT IN ('ISSUED', 'PAID', 'EXPIRED') OR number IS NOT NULL",
            name="ck_subscription_invoice_issued_has_number",
        ),
        sa.CheckConstraint(
            "status <> 'QUOTE_REQUIRED' OR number IS NULL", name="ck_subscription_invoice_quote_unnumbered"
        ),
        sa.CheckConstraint("(status = 'PAID') = (paid_at IS NOT NULL)", name="ck_subscription_invoice_paid_at"),
        sa.CheckConstraint(
            "status <> 'CANCELLED' OR (cancelled_at IS NOT NULL AND cancelled_by IS NOT NULL "
            "AND cancel_reason IS NOT NULL AND length(btrim(cancel_reason)) > 0)",
            name="ck_subscription_invoice_cancel_traced",
        ),
        sa.UniqueConstraint("number", name="uq_subscription_invoices_number"),
        sa.UniqueConstraint("school_id", "idempotency_key", name="uq_subscription_invoices_idempotency"),
    )
    op.create_index(
        "uq_subscription_invoices_one_open_per_school",
        "subscription_invoices",
        ["school_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('QUOTE_REQUIRED', 'ISSUED')"),
    )
    op.create_index("ix_subscription_invoices_school_created", "subscription_invoices", ["school_id", "created_at"])
    op.create_index("ix_subscription_invoices_status_created", "subscription_invoices", ["status", "created_at"])

    # --- Paiements -----------------------------------------------------------------------------------
    op.create_table(
        "subscription_payments",
        _uuid_pk(),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_invoices.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_tenant_columns(),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("identifier", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("tx_reference", sa.String(128), nullable=True),
        sa.Column("payment_reference", sa.String(128), nullable=True),
        sa.Column("payer_phone_last4", sa.String(4), nullable=True),
        sa.Column("provider_status_code", sa.String(16), nullable=True),
        _user_fk("initiated_by", nullable=True),
        _user_fk("recorded_by", nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("provider IN ('PAYGATE', 'MANUAL')", name="ck_subscription_payment_provider"),
        sa.CheckConstraint(
            "method IN ('FLOOZ', 'TMONEY', 'BANK_TRANSFER', 'CASH', 'OTHER')", name="ck_subscription_payment_method"
        ),
        sa.CheckConstraint(
            "status IN ('INITIATED', 'PENDING', 'SUCCEEDED', 'FAILED', 'EXPIRED', 'ANOMALY')",
            name="ck_subscription_payment_status",
        ),
        sa.CheckConstraint("currency = 'XOF'", name="ck_subscription_payment_currency"),
        sa.CheckConstraint("amount > 0 AND amount = trunc(amount)", name="ck_subscription_payment_amount_whole"),
        sa.CheckConstraint(
            "provider <> 'MANUAL' OR (recorded_by IS NOT NULL AND reference IS NOT NULL "
            "AND length(btrim(reference)) > 0)",
            name="ck_subscription_payment_manual_traced",
        ),
        sa.CheckConstraint(
            "status <> 'SUCCEEDED' OR confirmed_at IS NOT NULL", name="ck_subscription_payment_confirmed_at"
        ),
        sa.CheckConstraint(
            "payer_phone_last4 IS NULL OR payer_phone_last4 ~ '^[0-9]{4}$'",
            name="ck_subscription_payment_phone_last4",
        ),
        sa.UniqueConstraint("identifier", name="uq_subscription_payments_identifier"),
        sa.UniqueConstraint("tx_reference", name="uq_subscription_payments_tx_reference"),
        sa.UniqueConstraint("invoice_id", "idempotency_key", name="uq_subscription_payments_idempotency"),
    )
    op.create_index(
        "uq_subscription_payments_one_succeeded_per_invoice",
        "subscription_payments",
        ["invoice_id"],
        unique=True,
        postgresql_where=sa.text("status = 'SUCCEEDED'"),
    )
    op.create_index(
        "uq_subscription_payments_one_in_progress_per_invoice",
        "subscription_payments",
        ["invoice_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('INITIATED', 'PENDING')"),
    )
    op.create_index("ix_subscription_payments_school_created", "subscription_payments", ["school_id", "created_at"])

    # --- Périodes ------------------------------------------------------------------------------------
    op.create_table(
        "school_subscription_periods",
        _uuid_pk(),
        *_tenant_columns(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_invoices.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("starts_on", sa.Date, nullable=False),
        sa.Column("ends_on", sa.Date, nullable=False),
        *_timestamps(with_updated=False),
        sa.CheckConstraint("kind IN ('FREE_TRIAL', 'PAID')", name="ck_school_subscription_period_kind"),
        sa.CheckConstraint("ends_on >= starts_on", name="ck_school_subscription_period_dates"),
        sa.CheckConstraint(
            "(kind = 'PAID') = (invoice_id IS NOT NULL)", name="ck_school_subscription_period_invoice"
        ),
        sa.UniqueConstraint("invoice_id", name="uq_school_subscription_periods_invoice"),
    )
    op.create_index(
        "uq_school_subscription_periods_one_free_trial",
        "school_subscription_periods",
        ["school_id"],
        unique=True,
        postgresql_where=sa.text("kind = 'FREE_TRIAL'"),
    )
    op.create_index(
        "ix_school_subscription_periods_school_starts", "school_subscription_periods", ["school_id", "starts_on"]
    )

    # --- RLS -----------------------------------------------------------------------------------------
    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            USING (
                {_PLATFORM_WIDE}
                OR (
                    COALESCE(current_setting('app.tenant_org_ids', true), '') <> ''
                    AND organization_id = ANY(
                        string_to_array(current_setting('app.tenant_org_ids', true), ',')::uuid[]
                    )
                )
            )
            """
        )
    for table in GRID_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_read_all ON {table} FOR SELECT USING (true)")
        op.execute(
            f"CREATE POLICY {table}_platform_write ON {table} FOR ALL "
            f"USING ({_PLATFORM_WIDE}) WITH CHECK ({_PLATFORM_WIDE})"
        )

    # --- Permissions ---------------------------------------------------------------------------------
    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [{"id": uuid.uuid4(), "code": code, "description": description} for code, description in _ALL_PERMISSIONS.items()],
    )
    pairs = [
        f"('{role_code}', '{perm_code}')"
        for mapping in (SUBSCRIPTION_ROLE_PERMISSIONS, SUBSCRIPTION_PLATFORM_ROLE_PERMISSIONS)
        for role_code, perm_codes in mapping.items()
        for perm_code in perm_codes
    ]
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT roles.id, permissions.id
        FROM (VALUES {", ".join(pairs)}) AS pairs(role_code, perm_code)
        JOIN roles ON roles.code = pairs.role_code
        JOIN permissions ON permissions.code = pairs.perm_code
        """
    )
    op.execute(
        sa.text("UPDATE permissions SET description = :description WHERE code = 'platform.subscriptions.read'").bindparams(
            description=PLATFORM_SUBSCRIPTIONS_READ_DESCRIPTION
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE permissions SET description = :description WHERE code = 'platform.subscriptions.read'").bindparams(
            description=PLATFORM_SUBSCRIPTIONS_READ_PREVIOUS_DESCRIPTION
        )
    )
    codes_sql = ", ".join(f"'{code}'" for code in _ALL_PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({codes_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes_sql})")

    for table in reversed(GRID_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_platform_write ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_read_all ON {table}")
    for table in reversed(TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    op.drop_table("school_subscription_periods")
    op.drop_table("subscription_payments")
    op.drop_table("subscription_invoices")
    op.drop_table("subscription_invoice_number_counters")
    op.drop_table("subscription_price_lines")
    op.drop_table("subscription_price_grids")
