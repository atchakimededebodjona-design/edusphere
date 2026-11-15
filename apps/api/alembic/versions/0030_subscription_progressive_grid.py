"""subscription progressive grid (Phase 29 — grille complète validée le 2026-11-09)

Met en œuvre la grille tarifaire complète :
- la tranche 501 à 1 000 élèves est scindée en 501 à 750 (tranche 3) et 751 à 1 000 (tranche 4) ;
- au-delà de 1 000 élèves, une ligne FACULTATIVE de palier (tranche 5) porte le supplément PAR
  palier de 250 élèves commencé. Sans palier, la facture passe en devis, comme au lot A.

Les bornes restent fixées dans le code (`subscriptions/pricing.py`). Cette migration ne fait
qu'élargir la contrainte `ck_subscription_price_line_tier` de 0..3 à 0..5. C'est un assouplissement :
aucune donnée n'est réécrite, aucune ligne existante ne devient invalide, aucune autre table n'est
touchée. Les factures déjà émises gardent leurs montants figés.

Downgrade : remet 0..3, mais refuse de s'exécuter (sans rien supprimer) s'il existe des lignes de
tranche 4 ou de palier — même motif que 0024 : supprimer des prix est une décision humaine.

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-15
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "subscription_price_lines"
_CONSTRAINT = "ck_subscription_price_line_tier"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, "tier BETWEEN 0 AND 5")


def downgrade() -> None:
    count = op.get_bind().execute(sa.text(f"SELECT count(*) FROM {_TABLE} WHERE tier > 3")).scalar_one()
    if count:
        raise RuntimeError(
            f"Downgrade 0030 interrompu : {count} ligne(s) de grille de tranche 4 ou de palier existent. "
            "Aucune donnée n'a été modifiée. Archiver ou supprimer ces grilles est une décision explicite, hors migration."
        )
    op.drop_constraint(_CONSTRAINT, _TABLE, type_="check")
    op.create_check_constraint(_CONSTRAINT, _TABLE, "tier BETWEEN 0 AND 3")
