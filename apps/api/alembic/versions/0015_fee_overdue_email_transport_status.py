"""fee overdue email transport status (Sprint 1.6 — visibilité tentative/succès/échec des
rappels de frais en retard par email)

Ajoute uniquement deux colonnes à `fee_overdue_email_reminders` (migration 0014, inchangée) :
`transport_status` et `transport_checked_at`. Additive et non destructive — aucune modification
des migrations 0001-0014.

Pourquoi : `sent_at` (migration 0014) est écrit à la création de la ligne, AVANT toute tentative
d'envoi réseau — il ne renseigne jamais sur le résultat réel du transport SMTP
(`send_email_best_effort` avale silencieusement toute exception, voir app/core/email.py). Sans
ces colonnes, le tableau de bord Sprint 1.4 (`GET /fees/overdue`) ne peut afficher qu'une simple
existence de ligne comme "EMAIL_SENT", ce qui devient trompeur dès qu'un vrai fournisseur SMTP
est activé (Sprint 1.5/1.6 Discovery). Voir app/modules/fees/models.py::FeeOverdueEmailReminder
et app/modules/fees/overdue_reminders.py pour l'utilisation.

`transport_status` : `String(32)` NOT NULL, défaut `'ATTEMPTED'` — appliqué automatiquement à
TOUTES les lignes déjà existantes (leur issue réelle n'a jamais été enregistrée et ne doit jamais
être supposée être un succès). Pas de contrainte CHECK ni d'index : même convention que
`notifications.type`/`student_fees.status`, déjà de simples chaînes non contraintes côté base
dans ce dépôt — validation faite côté Python (`Literal` dans les schémas Pydantic), pas en base.
Aucun index spéculatif ajouté : aucune requête existante ne filtre par `transport_status`.

`transport_checked_at` : `TIMESTAMPTZ` nullable — `NULL` signifie explicitement "l'issue réelle
n'a jamais été enregistrée" (jamais une valeur devinée).

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-12

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "fee_overdue_email_reminders",
        sa.Column("transport_status", sa.String(32), nullable=False, server_default="ATTEMPTED"),
    )
    op.add_column(
        "fee_overdue_email_reminders",
        sa.Column("transport_checked_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("fee_overdue_email_reminders", "transport_checked_at")
    op.drop_column("fee_overdue_email_reminders", "transport_status")
