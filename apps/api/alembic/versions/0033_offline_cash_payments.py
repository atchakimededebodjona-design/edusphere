"""encaissements faits hors connexion (Phase 32, lot 3 : caisse sans internet)

Strictement additive : aucune migration précédente modifiée, aucune donnée existante réécrite.

Un caissier dont la caisse a été ouverte avec internet peut encaisser des espèces pendant une coupure :
l'appareil garde l'encaissement, remet au payeur un REÇU PROVISOIRE (`PROV-…`) et l'envoie au retour du
réseau. Le paiement reçoit alors, comme tout paiement, son numéro officiel (`RCPT-…`). Pour la
supervision et pour relier les deux reçus :

1. `payments.offline_collected_at` (TIMESTAMPTZ, NULL) : heure réelle de l'encaissement sur l'appareil
   (`created_at` reste l'heure d'arrivée au serveur).
2. `payments.provisional_receipt_number` (VARCHAR(32), NULL) : numéro du reçu provisoire remis au payeur,
   UNIQUE (school_id, provisional_receipt_number).
3. CHECK : les deux colonnes sont renseignées ensemble ou pas du tout.

NULL pour toutes les lignes existantes et pour tout encaissement fait avec internet (comportement
inchangé : PostgreSQL n'applique pas l'unicité aux NULL). Aucune policy RLS à modifier : la table garde
ses colonnes de tenant et ses policies existantes.

Downgrade : contraintes puis colonnes (les mentions « hors connexion » sont perdues, les paiements
restent).

Revision ID: 0033
Revises: 0032
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("offline_collected_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("payments", sa.Column("provisional_receipt_number", sa.String(32), nullable=True))
    op.create_unique_constraint(
        "uq_payment_provisional_receipt_number", "payments", ["school_id", "provisional_receipt_number"]
    )
    op.create_check_constraint(
        "ck_payment_offline_fields_together",
        "payments",
        "(offline_collected_at IS NULL) = (provisional_receipt_number IS NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_payment_offline_fields_together", "payments", type_="check")
    op.drop_constraint("uq_payment_provisional_receipt_number", "payments", type_="unique")
    op.drop_column("payments", "provisional_receipt_number")
    op.drop_column("payments", "offline_collected_at")
