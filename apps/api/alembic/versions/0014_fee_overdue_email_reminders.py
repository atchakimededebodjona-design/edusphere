"""fee overdue email reminders (Sprint 1.3 — rappels de frais en retard par email pour les
tuteurs sans compte utilisateur)

Ajoute uniquement une table dédiée `fee_overdue_email_reminders`. Additive et non destructive :
aucune modification des migrations 0001-0013.

Pourquoi une nouvelle table plutôt qu'étendre `notifications` (migration 0011/0013) : cette
dernière a `recipient_user_id` NOT NULL + FK vers `users.id`. Un tuteur sans compte utilisateur
(`Guardian.user_id IS NULL`) n'a structurellement aucun `user_id` à y placer — relâcher cette
contrainte modifierait la policy RLS `notifications_recipient_isolation` (basée sur
`recipient_user_id`) et tous ses index existants. Voir app/modules/fees/models.py::
FeeOverdueEmailReminder.

RLS : policy générique `{table}_tenant_isolation` basée sur `organization_id` (même motif que
`fee_categories`/`fee_schedules`/`student_fees`/`payments`/`payment_allocations`, migration 0009)
— PAS le motif spécifique par destinataire de `notifications` : cette table n'est jamais lue via
une API utilisateur, uniquement par le job `app/jobs/overdue_fee_reminders.py` sous
`set_platform_wide_context`.

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "fee_overdue_email_reminders",
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
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_fee_id", "guardian_id", name="uq_fee_overdue_email_reminder"),
    )
    op.create_index("ix_fee_overdue_email_reminders_school_id", "fee_overdue_email_reminders", ["school_id"])
    op.create_index(
        "ix_fee_overdue_email_reminders_organization_id", "fee_overdue_email_reminders", ["organization_id"]
    )
    op.create_index(
        "ix_fee_overdue_email_reminders_student_fee_id", "fee_overdue_email_reminders", ["student_fee_id"]
    )
    op.create_index("ix_fee_overdue_email_reminders_guardian_id", "fee_overdue_email_reminders", ["guardian_id"])

    op.execute("ALTER TABLE fee_overdue_email_reminders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE fee_overdue_email_reminders FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY fee_overdue_email_reminders_tenant_isolation ON fee_overdue_email_reminders
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
    op.execute(
        "DROP POLICY IF EXISTS fee_overdue_email_reminders_tenant_isolation ON fee_overdue_email_reminders"
    )
    op.drop_table("fee_overdue_email_reminders")
