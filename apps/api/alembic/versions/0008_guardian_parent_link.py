"""guardian parent link (Phase 7 — extension mobile Parent)

Ajoute uniquement guardians.user_id (nullable, FK users.id ON DELETE SET NULL) + index + une
contrainte d'unicité partielle (school_id, user_id) WHERE user_id IS NOT NULL — empêche qu'un
même compte soit lié deux fois à des tuteurs différents dans la même école, sans empêcher un
même compte d'être lié à des Guardian dans des écoles différentes (fratrie répartie).

Additive et non destructive. Aucune modification des migrations 0001-0007. Aucune nouvelle
permission RBAC (voir app/modules/parent/ — l'accès parent est contrôlé exclusivement par ce
lien, pas par le système de permissions org/école existant).

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-03

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "guardians",
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )
    op.create_index("ix_guardians_user_id", "guardians", ["user_id"])
    op.execute(
        """
        CREATE UNIQUE INDEX uq_guardian_school_user
        ON guardians (school_id, user_id)
        WHERE user_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_guardian_school_user")
    op.drop_index("ix_guardians_user_id", table_name="guardians")
    op.drop_column("guardians", "user_id")
