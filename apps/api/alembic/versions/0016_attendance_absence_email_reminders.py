"""attendance absence email reminders (Sprint 1.8 — email d'absence pour les tuteurs sans compte
utilisateur)

Ajoute uniquement une table dédiée `attendance_absence_email_reminders`, incluant dès sa création
`transport_status`/`transport_checked_at` (même convention que `fee_overdue_email_reminders` après
sa migration 0015, pas besoin ici de deux migrations séparées puisque la table est neuve). Additive
et non destructive : aucune modification des migrations 0001-0015, aucune donnée existante touchée.

Pourquoi une nouvelle table plutôt qu'étendre `notifications` : même raison que
`fee_overdue_email_reminders` (migration 0014) — `notifications.recipient_user_id` est NOT NULL,
un tuteur sans compte utilisateur (`Guardian.user_id IS NULL`) n'a structurellement aucun user_id
à y placer. Voir app/modules/attendance/models.py::AttendanceAbsenceEmailReminder.

RLS : policy générique `{table}_tenant_isolation` basée sur `organization_id`, exactement le même
motif que `fee_overdue_email_reminders` (migration 0014) — cette table n'est jamais lue via une
API utilisateur, uniquement par attendance/service.py sous le contexte tenant de la requête en
cours (ou réappliqué explicitement après un commit intermédiaire, voir
send_absence_reminder_emails).

Revision ID: 0016
Revises: 0015
Create Date: 2026-09-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attendance_absence_email_reminders",
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
            "student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "guardian_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("guardians.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "attendance_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attendance_records.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("absence_date", sa.Date(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("transport_status", sa.String(32), nullable=False, server_default="ATTEMPTED"),
        sa.Column("transport_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "student_id", "guardian_id", "absence_date", name="uq_attendance_absence_email_reminder"
        ),
    )
    op.create_index(
        "ix_attendance_absence_email_reminders_school_id", "attendance_absence_email_reminders", ["school_id"]
    )
    op.create_index(
        "ix_attendance_absence_email_reminders_organization_id",
        "attendance_absence_email_reminders",
        ["organization_id"],
    )
    op.create_index(
        "ix_attendance_absence_email_reminders_student_id", "attendance_absence_email_reminders", ["student_id"]
    )
    op.create_index(
        "ix_attendance_absence_email_reminders_guardian_id", "attendance_absence_email_reminders", ["guardian_id"]
    )
    op.create_index(
        "ix_attendance_absence_email_reminders_attendance_id",
        "attendance_absence_email_reminders",
        ["attendance_id"],
    )

    op.execute("ALTER TABLE attendance_absence_email_reminders ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE attendance_absence_email_reminders FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY attendance_absence_email_reminders_tenant_isolation ON attendance_absence_email_reminders
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
        "DROP POLICY IF EXISTS attendance_absence_email_reminders_tenant_isolation ON attendance_absence_email_reminders"
    )
    op.drop_table("attendance_absence_email_reminders")
