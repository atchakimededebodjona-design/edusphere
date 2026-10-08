"""student exit (sortie de l'établissement)

Ajoute une nouvelle table `student_exits`, utilisée par la réinscription/promotion en masse
(students/service.py::bulk_promote_students) pour déclarer explicitement qu'un élève d'une classe
SOURCE sans correspondance dans le mapping (ex. une classe terminale comme CM2 dans une école qui
s'arrête là) sort de l'établissement, plutôt que d'être silencieusement compté comme "oublié".

exit_type : GRADUATED (fin de cycle) / TRANSFERRED (transfert) / WITHDRAWN (retrait) / OTHER.
UNIQUE(student_id, academic_year_id) : une seule sortie par élève et par année scolaire — l'année
ici est celle de la DERNIÈRE inscription active de l'élève (l'année SOURCE de la promotion), jamais
modifiée ni supprimée par cette table (additive, aucune autre table touchée).

RLS : policy générique `{table}_tenant_isolation` basée sur `organization_id`, même motif que
toutes les tables tenant existantes (voir migration 0016 pour le même schéma de policy).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "student_exits",
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
            "academic_year_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_years.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("exit_type", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("exit_date", sa.Date(), nullable=False),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("student_id", "academic_year_id", name="uq_student_exit_year"),
    )
    op.create_index("ix_student_exits_school_id", "student_exits", ["school_id"])
    op.create_index("ix_student_exits_organization_id", "student_exits", ["organization_id"])
    op.create_index("ix_student_exits_student_id", "student_exits", ["student_id"])
    op.create_index("ix_student_exits_academic_year_id", "student_exits", ["academic_year_id"])

    op.execute("ALTER TABLE student_exits ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE student_exits FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY student_exits_tenant_isolation ON student_exits
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
    op.execute("DROP POLICY IF EXISTS student_exits_tenant_isolation ON student_exits")
    op.drop_table("student_exits")
