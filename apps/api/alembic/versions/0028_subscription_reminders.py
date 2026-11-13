"""subscription reminders (Phase 29, lot C — rappels d'abonnement des écoles)

Strictement additive : aucune migration précédente modifiée, aucune table existante modifiée.

1. Table `subscription_reminders` (voir app/modules/subscriptions/models.py, contraintes identiques) :
   idempotence des rappels, une ligne par (cible, palier). Cible : une période (paliers J30, J7, J0)
   ou une facture (palier INVOICE_J3). school_id + organization_id, RLS `{table}_tenant_isolation`
   identique aux tables tenant existantes (migration 0027).
2. Les nouveaux types de notification (SUBSCRIPTION_RENEWAL_DUE, SUBSCRIPTION_EXPIRED,
   SUBSCRIPTION_INVOICE_DUE) ne demandent aucune migration : `notifications.type` n'a pas de
   contrainte CHECK (migration 0013).

Downgrade : policy puis table (les traces d'idempotence sont perdues ; les notifications déjà
créées restent).

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "subscription_reminders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "period_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("school_subscription_periods.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_invoices.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("stage", sa.String(16), nullable=False),
        sa.Column("recipients_count", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("stage IN ('J30', 'J7', 'J0', 'INVOICE_J3')", name="ck_subscription_reminder_stage"),
        sa.CheckConstraint("(period_id IS NULL) <> (invoice_id IS NULL)", name="ck_subscription_reminder_one_target"),
        sa.CheckConstraint(
            "(stage = 'INVOICE_J3') = (invoice_id IS NOT NULL)", name="ck_subscription_reminder_stage_target"
        ),
        sa.CheckConstraint("recipients_count >= 0", name="ck_subscription_reminder_recipients"),
    )
    op.create_index(
        "uq_subscription_reminders_period_stage",
        "subscription_reminders",
        ["period_id", "stage"],
        unique=True,
        postgresql_where=sa.text("period_id IS NOT NULL"),
    )
    op.create_index(
        "uq_subscription_reminders_invoice_stage",
        "subscription_reminders",
        ["invoice_id", "stage"],
        unique=True,
        postgresql_where=sa.text("invoice_id IS NOT NULL"),
    )
    op.create_index("ix_subscription_reminders_school_created", "subscription_reminders", ["school_id", "created_at"])

    op.execute("ALTER TABLE subscription_reminders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE subscription_reminders FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY subscription_reminders_tenant_isolation ON subscription_reminders
        USING (
            current_setting('app.is_platform_wide', true) = 'true'
            OR (
                COALESCE(current_setting('app.tenant_org_ids', true), '') <> ''
                AND organization_id = ANY(
                    string_to_array(current_setting('app.tenant_org_ids', true), ',')::uuid[]
                )
            )
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS subscription_reminders_tenant_isolation ON subscription_reminders")
    op.drop_table("subscription_reminders")
