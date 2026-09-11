"""fee overdue reminders (Sprint 1.2 — rappels automatiques de frais impayés)

Ajoute uniquement `notifications.student_fee_id` (nullable, FK student_fees.id ON DELETE
SET NULL) + un index simple + un index unique PARTIEL sur (recipient_user_id, student_fee_id)
WHERE type = 'FEE_OVERDUE'.

Pourquoi cette colonne plutôt qu'une déduplication par texte : un job batch qui s'exécute
quotidiennement doit pouvoir déterminer de façon fiable si un tuteur a déjà reçu le rappel pour
CETTE `StudentFee` précise, sans dépendre du contenu du message (titre/corps), qui pourrait
changer (traduction, reformulation) sans que la règle métier ("un seul rappel par frais et par
destinataire") change. Voir app/modules/fees/overdue_reminders.py.

Pas de nouvelle colonne `type` ni de contrainte CHECK sur `notifications.type` : c'est déjà une
simple `String(32)` sans enum contraint côté base (voir migration 0011) — "FEE_OVERDUE" (11
caractères) y tient sans modification. Seul le `Literal` Python (notifications/schemas.py) et le
tuple `NOTIFICATION_TYPES` (notifications/models.py, documentation uniquement) sont étendus, dans
le code, pas dans cette migration.

L'index unique est PARTIEL (uniquement pour type = 'FEE_OVERDUE') : les 4 types de notification
précédents n'ont pas de `student_fee_id` et ne doivent pas être contraints par cette règle. Il
est nullable ailleurs (une notification STUDENT_ABSENT/PAYMENT_RECORDED/... ne renseigne jamais
ce champ) — cohérent avec `guardians.user_id`/`uq_guardian_school_user` (migration 0008), même
motif (colonne de lien optionnelle + contrainte partielle plutôt qu'une nouvelle table).

Additive et non destructive. Aucune modification des migrations 0001-0012.

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "notifications",
        sa.Column(
            "student_fee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("student_fees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_notifications_student_fee_id", "notifications", ["student_fee_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_notifications_fee_overdue_recipient
        ON notifications (recipient_user_id, student_fee_id)
        WHERE type = 'FEE_OVERDUE' AND student_fee_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_notifications_fee_overdue_recipient")
    op.drop_index("ix_notifications_student_fee_id", table_name="notifications")
    op.drop_column("notifications", "student_fee_id")
