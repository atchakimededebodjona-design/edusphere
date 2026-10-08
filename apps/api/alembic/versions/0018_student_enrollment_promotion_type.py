"""student enrollment promotion type

Ajoute une colonne nullable `promotion_type` à `student_enrollments`, renseignée uniquement par
la réinscription/promotion en masse (POST /api/v1/students/bulk-promotion — voir
students/service.py::bulk_promote_students) : PROMOTED (classe de niveau différent) ou REPEATED
(même niveau que la classe source, redoublement). TRANSFERRED reste une valeur valide de l'enum
applicatif pour cohérence avec le concept déjà existant (StudentEnrollment.status), mais n'est
jamais produite par cette fonctionnalité elle-même.

Nullable : toutes les inscriptions créées avant cette migration, ou via les autres points d'entrée
existants (inscription individuelle, affectation en masse — Sprint précédent), n'ont pas cette
notion et ne doivent jamais être recalculées rétroactivement ici.

Additive et non destructive : aucune ligne existante modifiée, aucune autre table touchée, RLS
déjà en place sur `student_enrollments` reste inchangée. Aucun index ajouté : ce champ n'est
jamais filtré en masse dans les requêtes actuelles (uniquement affiché/retourné).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student_enrollments", sa.Column("promotion_type", sa.String(32), nullable=True))


def downgrade() -> None:
    op.drop_column("student_enrollments", "promotion_type")
