"""fee overdue sms reminders (PR #16 — canal SMS des rappels de frais en retard)

Ajoute uniquement la table `fee_overdue_sms_reminders` — pendant SMS de
`fee_overdue_email_reminders` (migration 0009/0021), pour les tuteurs sans compte utilisateur
disposant d'un numéro de téléphone normalisable en E.164 (voir app/core/phone.py). Additive et
non destructive : ne modifie AUCUNE migration ni table précédente (0001-0021 inchangées).

Contrainte d'unicité `(student_fee_id, guardian_id, reminder_stage)` — même motif exact que
`uq_fee_overdue_email_reminder_stage` (migration 0021) : au plus une ligne par (frais, tuteur,
palier), garantie EN BASE, jamais seulement applicative (voir
fees/overdue_reminders.py::_prepare_overdue_sms).

RLS : policy générique `{table}_tenant_isolation` basée sur `organization_id`, identique à toutes
les tables tenant existantes (voir migration 0021 pour le même schéma de policy).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fee_overdue_sms_reminders",
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
            "student_fee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("student_fees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "guardian_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("guardians.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("reminder_stage", sa.String(8), nullable=False),
        sa.Column("transport_status", sa.String(32), nullable=False, server_default="ATTEMPTED"),
        sa.Column("transport_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_message_id", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_fee_id", "guardian_id", "reminder_stage", name="uq_fee_overdue_sms_reminder_stage"),
    )
    op.create_index("ix_fee_overdue_sms_reminders_school_id", "fee_overdue_sms_reminders", ["school_id"])
    op.create_index("ix_fee_overdue_sms_reminders_organization_id", "fee_overdue_sms_reminders", ["organization_id"])
    op.create_index("ix_fee_overdue_sms_reminders_student_fee_id", "fee_overdue_sms_reminders", ["student_fee_id"])
    op.create_index("ix_fee_overdue_sms_reminders_guardian_id", "fee_overdue_sms_reminders", ["guardian_id"])

    op.execute("ALTER TABLE fee_overdue_sms_reminders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fee_overdue_sms_reminders FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY fee_overdue_sms_reminders_tenant_isolation ON fee_overdue_sms_reminders
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
    op.execute("DROP POLICY IF EXISTS fee_overdue_sms_reminders_tenant_isolation ON fee_overdue_sms_reminders")
    op.drop_table("fee_overdue_sms_reminders")
