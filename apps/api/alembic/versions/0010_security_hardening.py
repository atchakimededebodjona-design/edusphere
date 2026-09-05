"""security hardening (Phase 20 — RLS organizations + StudentFee.updated_by)

Deux changements additifs, sans rapport l'un à l'autre fonctionnellement mais regroupés dans une
seule migration comme demandé :

1. `organizations` n'avait aucune policy RLS depuis la Phase 1 (gap MEDIUM documenté,
   `PILOT_READINESS.md`) — seul le contrôle applicatif (`ensure_permission`) protégeait cette
   table. Ajoute la même policy que toutes les autres tables tenant-scopées, avec `id` comme clé
   (cette table EST la racine tenant, elle n'a pas de colonne `organization_id` séparée).
2. `student_fees.updated_by` (Phase 19 → durci Phase 20) : un ajustement manuel du montant dû
   n'était pas attribuable à un utilisateur précis — voir docs/phases/PHASE_20_DISCOVERY.md §17.

Additive et non destructive. Aucune modification des migrations 0001-0009.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-06

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- 1. RLS sur organizations ---------------------------------------------------------
    # Motif identique à toutes les autres policies (`{table}_tenant_isolation`), à la seule
    # différence que la colonne de comparaison est `id` (la ligne EST l'organisation) et non
    # `organization_id` (qui n'existe pas sur cette table).
    op.execute("ALTER TABLE organizations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY organizations_tenant_isolation ON organizations
        USING (
            current_setting('app.is_platform_wide', true) = 'true'
            OR (
                COALESCE(current_setting('app.tenant_org_ids', true), '') <> ''
                AND id = ANY(
                    string_to_array(current_setting('app.tenant_org_ids', true), ',')::uuid[]
                )
            )
        )
        """
    )

    # --- 2. StudentFee.updated_by ----------------------------------------------------------
    op.add_column(
        "student_fees",
        sa.Column(
            "updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("student_fees", "updated_by")

    op.execute("DROP POLICY IF EXISTS organizations_tenant_isolation ON organizations")
    op.execute("ALTER TABLE organizations NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE organizations DISABLE ROW LEVEL SECURITY")
