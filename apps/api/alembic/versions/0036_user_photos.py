"""photo d'identité des comptes (enseignants et personnel, 2026-11-19)

Strictement additive : aucune migration précédente modifiée, aucune donnée existante réécrite.

Les élèves ont déjà leur photo (`students.photo_path`, Phase 3). Les comptes n'en avaient pas :
1. `users.photo_path` (chemin dans le stockage, NULL sans photo). La photo se met par le compte
   lui-même (`/auth/me/photo`) ou par l'administration de son école (`/users/{id}/photo`).

Downgrade : suppression de la colonne (les fichiers restent dans le stockage, sans référence).

Revision ID: 0036
Revises: 0035
Create Date: 2026-11-19
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("photo_path", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "photo_path")
