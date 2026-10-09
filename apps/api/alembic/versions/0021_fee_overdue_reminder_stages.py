"""fee overdue reminder stages (PR #15 — cadence J0/J7/J30)

Fait évoluer le rappel de frais en retard, jusqu'ici à usage unique, vers une cadence à trois
paliers (J0/J7/J30, voir `app/modules/fees/models.py::REMINDER_STAGES`). Additive et non
destructive, aucune perte d'historique :

- `notifications.reminder_stage` (nullable — uniquement pertinent pour `type='FEE_OVERDUE'`,
  toujours NULL pour les 4 autres types). Les lignes FEE_OVERDUE déjà existantes sont back-fillées
  à 'J0' (c'est exactement ce qu'elles représentaient avant ce PR : LE rappel unique).
- `fee_overdue_email_reminders.reminder_stage` (NOT NULL, `server_default='J0'` — même motif,
  les lignes existantes back-fillées automatiquement par Postgres lors de l'ajout de la colonne).

  Conséquence côté job (`fees/overdue_reminders.py::_next_stage_to_send`, non modifiée par cette
  migration, seulement rendue cohérente par ce back-fill) pour un frais resté impayé dont le
  tuteur avait déjà reçu l'ancien rappel unique avant ce PR : ce back-fill à "J0" est lu par le
  job comme "J0 déjà envoyé" — jamais renvoyé une seconde fois. Si le frais reste impayé, "J7"
  devient éligible dès que le job tourne après `due_date + 7 jours` (ce seuil est très
  probablement déjà dépassé pour un frais déjà ancien), puis "J30" après `due_date + 30 jours` —
  un seul nouveau palier par exécution, jamais les deux à la fois (voir la règle de progression
  documentée dans `_next_stage_to_send`). Vérifié explicitement par
  `tests/test_fee_reminder_stages.py::test_pre_pr15_reminder_backfilled_to_j0_unblocks_j7_never_resends_j0`.
- Remplace les deux index/contraintes uniques d'idempotence existants (migration 0013 pour les
  notifications, migration 0009 pour les emails) par leurs équivalents incluant `reminder_stage` —
  jamais perdus, seulement élargis d'une colonne. Voir `fees/overdue_reminders.py` pour la
  garantie d'unicité EN BASE (jamais une simple vérification applicative) que ces index/contraintes
  matérialisent.
- Nouvel index `ix_student_fees_status_due_date` : soutient le filtre déjà existant de
  `_list_eligible_overdue_fees` (`status != 'CANCELLED' AND due_date < today`), interrogé plus
  souvent en pratique maintenant que trois paliers sont évalués à chaque exécution quotidienne.

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- notifications ---------------------------------------------------------------------
    op.add_column("notifications", sa.Column("reminder_stage", sa.String(8), nullable=True))
    op.execute("UPDATE notifications SET reminder_stage = 'J0' WHERE type = 'FEE_OVERDUE'")
    op.execute("DROP INDEX IF EXISTS uq_notifications_fee_overdue_recipient")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_notifications_fee_overdue_recipient_stage
        ON notifications (recipient_user_id, student_fee_id, reminder_stage)
        WHERE type = 'FEE_OVERDUE' AND student_fee_id IS NOT NULL AND reminder_stage IS NOT NULL
        """
    )

    # --- fee_overdue_email_reminders --------------------------------------------------------
    op.add_column(
        "fee_overdue_email_reminders",
        sa.Column("reminder_stage", sa.String(8), nullable=False, server_default="J0"),
    )
    op.drop_constraint("uq_fee_overdue_email_reminder", "fee_overdue_email_reminders", type_="unique")
    op.create_unique_constraint(
        "uq_fee_overdue_email_reminder_stage",
        "fee_overdue_email_reminders",
        ["student_fee_id", "guardian_id", "reminder_stage"],
    )

    # --- performance : filtre déjà existant de _list_eligible_overdue_fees ------------------
    op.create_index("ix_student_fees_status_due_date", "student_fees", ["status", "due_date"])


def downgrade() -> None:
    # AVERTISSEMENT : si des paliers J7/J30 ont déjà été générés en production (plusieurs lignes
    # pour un même (student_fee_id, guardian_id)), recréer la contrainte unique à 2 colonnes
    # ci-dessous échouera (violation immédiate) — ce downgrade n'est garanti réversible que tant
    # qu'aucun palier au-delà de J0 n'a encore été atteint par un job réel.
    op.drop_index("ix_student_fees_status_due_date", table_name="student_fees")

    op.drop_constraint("uq_fee_overdue_email_reminder_stage", "fee_overdue_email_reminders", type_="unique")
    op.create_unique_constraint(
        "uq_fee_overdue_email_reminder", "fee_overdue_email_reminders", ["student_fee_id", "guardian_id"]
    )
    op.drop_column("fee_overdue_email_reminders", "reminder_stage")

    op.execute("DROP INDEX IF EXISTS uq_notifications_fee_overdue_recipient_stage")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_notifications_fee_overdue_recipient
        ON notifications (recipient_user_id, student_fee_id)
        WHERE type = 'FEE_OVERDUE' AND student_fee_id IS NOT NULL
        """
    )
    op.drop_column("notifications", "reminder_stage")
