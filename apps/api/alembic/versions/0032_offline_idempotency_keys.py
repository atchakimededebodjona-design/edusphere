"""clés d'idempotence des séances d'appel et des évaluations (Phase 32, lot 2 : saisie hors connexion)

Strictement additive : aucune migration précédente modifiée, aucune donnée existante réécrite.

Une saisie faite hors connexion est renvoyée automatiquement au retour du réseau, parfois plusieurs
fois (coupure pendant l'envoi : on ne sait pas si le serveur l'a reçue). Les présences et les notes
sont déjà mises à jour élève par élève (`uq_attendance_record`, `uq_assessment_result`) ; seules la
création d'une séance d'appel et celle d'une évaluation produisaient des doublons. Même mécanisme que
les paiements (`uq_payment_idempotency`, migration 0009) :

1. `attendance_sessions.idempotency_key` (VARCHAR(128), NULL) + UNIQUE (school_id, idempotency_key).
2. `assessments.idempotency_key` (VARCHAR(128), NULL) + UNIQUE (school_id, idempotency_key).

NULL pour toutes les lignes existantes et pour toute création sans clé (comportement inchangé :
PostgreSQL n'applique pas l'unicité aux NULL). Aucune policy RLS à modifier : les deux tables gardent
leurs colonnes de tenant et leurs policies existantes.

Downgrade : contraintes puis colonnes (les clés éventuelles sont perdues, les lignes restent).

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attendance_sessions", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_unique_constraint(
        "uq_attendance_session_idempotency", "attendance_sessions", ["school_id", "idempotency_key"]
    )
    op.add_column("assessments", sa.Column("idempotency_key", sa.String(128), nullable=True))
    op.create_unique_constraint("uq_assessment_idempotency", "assessments", ["school_id", "idempotency_key"])


def downgrade() -> None:
    op.drop_constraint("uq_assessment_idempotency", "assessments", type_="unique")
    op.drop_column("assessments", "idempotency_key")
    op.drop_constraint("uq_attendance_session_idempotency", "attendance_sessions", type_="unique")
    op.drop_column("attendance_sessions", "idempotency_key")
