"""payment provider callbacks (Phase 29, lot B — paiement Mobile Money PayGate Global)

Strictement additive : aucune migration précédente modifiée, aucune table existante modifiée.

1. Table `payment_provider_callbacks` (voir app/modules/subscriptions/models.py, contraintes
   identiques) : journal minimal des notifications reçues de PayGate. La notification n'est pas
   signée : elle ne fait jamais foi, elle déclenche seulement une vérification d'état par le
   serveur. Ni corps intégral ni numéro de téléphone.
2. RLS ENABLE + FORCE avec une policy « plateforme seulement », même motif que
   `partners_platform_only` (migration 0023) : aucun compte d'école ne lit ce journal.
3. `subscription_payments` n'est pas modifiée : ses statuts INITIATED/PENDING/FAILED/EXPIRED/ANOMALY
   et ses colonnes du paiement en ligne existent depuis 0027.
4. Le nouveau type de notification SUBSCRIPTION_PAYMENT_CONFIRMED ne demande aucune migration :
   `notifications.type` n'a pas de contrainte CHECK (migration 0013).

Downgrade : policy puis table (le journal des notifications est perdu ; les paiements restent).

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_provider_callbacks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("identifier", sa.String(64), nullable=True),
        sa.Column("tx_reference", sa.String(128), nullable=True),
        sa.Column("declared_amount", sa.String(32), nullable=True),
        sa.Column("source_ip", sa.String(64), nullable=True),
        sa.Column("result", sa.String(24), nullable=False),
        sa.Column(
            "payment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscription_payments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.CheckConstraint("provider IN ('PAYGATE')", name="ck_payment_provider_callback_provider"),
        sa.CheckConstraint(
            "result IN ('INVALID', 'UNKNOWN_IDENTIFIER', 'NOT_IN_PROGRESS', 'CHECK_SCHEDULED')",
            name="ck_payment_provider_callback_result",
        ),
    )
    op.create_index("ix_payment_provider_callbacks_received", "payment_provider_callbacks", ["received_at"])
    op.create_index("ix_payment_provider_callbacks_payment", "payment_provider_callbacks", ["payment_id"])

    op.execute("ALTER TABLE payment_provider_callbacks ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE payment_provider_callbacks FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY payment_provider_callbacks_platform_only ON payment_provider_callbacks
        USING (current_setting('app.is_platform_wide', true) = 'true')
        WITH CHECK (current_setting('app.is_platform_wide', true) = 'true')
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS payment_provider_callbacks_platform_only ON payment_provider_callbacks")
    op.drop_table("payment_provider_callbacks")
