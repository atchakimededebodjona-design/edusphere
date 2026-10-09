"""platform owner & partners (PR #17 — Platform Owner & Partner isolation)

Strictement additive : ne modifie AUCUNE migration ni table précédente (0001-0022 inchangées).

1. Nouveau rôle `PLATFORM_OWNER` (ligne `roles`, même motif `op.bulk_insert` que la migration
   0002). Rôle plateforme de confiance : il fait partie de `PLATFORM_ROLE_CODES`
   (modules/rbac/models.py), donc rend la session RLS platform-wide — mais ne reçoit AUCUNE
   permission du domaine scolaire, uniquement les permissions `platform.*` ci-dessous. Aucune
   attribution de ce rôle à un compte réel n'est faite ici : c'est une opération hors bande.
   Déclaré dans `PR17_ROLE_NAMES` (pas `ROLE_NAMES`, importé tel quel par 0002 — voir
   rbac/seed.py).

2. Nouvelles permissions (rbac/seed.py) et leurs attributions :
   - `PR17_PLATFORM_PERMISSIONS` (`platform.*`) -> SUPER_ADMIN, PLATFORM_OWNER ;
   - `PR17_PARTNER_PERMISSIONS` (`partner.*`) -> SUPER_ADMIN, PARTNER_ADMIN (rôle déjà existant
     depuis 0002, jusqu'ici sans aucune permission).
   `platform.subscriptions.read`, `platform.commissions.read`, `partner.commissions.read` sont
   réservés à la PR #18 (moteur financier de commissions) : aucun endpoint/table/logique ici.

3. Table `partners` : un partenaire commercial par compte utilisateur (`UNIQUE(user_id)`). Pas
   d'`organization_id` (un partenaire n'appartient à aucun tenant) : pas de policy générique
   `{table}_tenant_isolation`, mais RLS ENABLE+FORCE avec une policy `partners_platform_only`
   restreinte au contexte platform-wide. Un PARTNER_ADMIN (jamais platform-wide, voir
   core/tenancy.py) qui lit SA ligne passe donc par `set_platform_wide_context` + un filtre
   explicite `user_id = <utilisateur authentifié>` (partners/service.py::get_own_partner).

4. Table `partner_school_enrollments` : source d'acquisition de chaque école.
   - `partner_id` nullable : NULL = école inscrite directement par le Platform Owner ;
   - `school_id` UNIQUE : une école n'est inscrite qu'une seule fois, par une seule source
     (garanti EN BASE, voir tests/test_partners.py — inscriptions concurrentes) ;
   - `acquisition_source` : "PLATFORM_OWNER" ou "PARTNER" ;
   - `commission_eligible` : true uniquement pour une inscription "PARTNER" — simple drapeau,
     AUCUN montant n'est calculé ni stocké (PR #18).
   RLS : policy générique `{table}_tenant_isolation` basée sur `organization_id`, identique à
   toutes les tables tenant existantes (voir migration 0022), par cohérence/défense en
   profondeur. Un partenaire ayant toujours un `tenant_org_ids` vide, ses lectures de ses propres
   lignes passent par `set_platform_wide_context` + un filtre explicite `partner_id`.

Grants : couverts automatiquement par le "ALTER DEFAULT PRIVILEGES" posé en 0002.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-09

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import (
    PR17_PARTNER_PERMISSIONS,
    PR17_PARTNER_ROLE_PERMISSIONS,
    PR17_PLATFORM_PERMISSIONS,
    PR17_PLATFORM_ROLE_PERMISSIONS,
    PR17_ROLE_NAMES,
)

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ALL_PERMISSIONS: dict[str, str] = {**PR17_PLATFORM_PERMISSIONS, **PR17_PARTNER_PERMISSIONS}


def upgrade() -> None:
    # --- 1. Rôle PLATFORM_OWNER (même motif que migration 0002) ------------------------------
    roles_table = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("is_system_role", sa.Boolean),
    )
    op.bulk_insert(
        roles_table,
        [
            {"id": uuid.uuid4(), "code": code, "name": name, "is_system_role": True}
            for code, name in PR17_ROLE_NAMES.items()
        ],
    )

    # --- 2. Permissions + attributions (même motif que migration 0020) -----------------------
    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [{"id": uuid.uuid4(), "code": code, "description": description} for code, description in _ALL_PERMISSIONS.items()],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for mapping in (PR17_PLATFORM_ROLE_PERMISSIONS, PR17_PARTNER_ROLE_PERMISSIONS)
        for role_code, perm_codes in mapping.items()
        for perm_code in perm_codes
    ]
    op.execute(
        f"""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT roles.id, permissions.id
        FROM (VALUES {", ".join(pairs)}) AS pairs(role_code, perm_code)
        JOIN roles ON roles.code = pairs.role_code
        JOIN permissions ON permissions.code = pairs.perm_code
        """
    )

    # --- 3. Table partners ---------------------------------------------------------------------
    op.create_table(
        "partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", name="uq_partners_user_id"),
    )

    op.execute("ALTER TABLE partners ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partners FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY partners_platform_only ON partners
        USING (current_setting('app.is_platform_wide', true) = 'true')
        """
    )

    # --- 4. Table partner_school_enrollments -----------------------------------------------------
    op.create_table(
        "partner_school_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "partner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("partners.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "enrolled_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("acquisition_source", sa.String(16), nullable=False),
        sa.Column("commission_eligible", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        # L'index implicite de cette contrainte UNIQUE couvre déjà school_id : pas d'index dédié.
        sa.UniqueConstraint("school_id", name="uq_partner_school_enrollments_school_id"),
    )
    op.create_index("ix_partner_school_enrollments_partner_id", "partner_school_enrollments", ["partner_id"])
    op.create_index("ix_partner_school_enrollments_organization_id", "partner_school_enrollments", ["organization_id"])
    op.create_index(
        "ix_partner_school_enrollments_acquisition_source", "partner_school_enrollments", ["acquisition_source"]
    )

    op.execute("ALTER TABLE partner_school_enrollments ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_school_enrollments FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY partner_school_enrollments_tenant_isolation ON partner_school_enrollments
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
    # Ordre inverse des dépendances : tables (enrollments -> partners), puis attributions et
    # permissions, puis le rôle (dont les user_roles/role_permissions éventuels partent en CASCADE).
    op.execute(
        "DROP POLICY IF EXISTS partner_school_enrollments_tenant_isolation ON partner_school_enrollments"
    )
    op.drop_index("ix_partner_school_enrollments_acquisition_source", table_name="partner_school_enrollments")
    op.drop_index("ix_partner_school_enrollments_organization_id", table_name="partner_school_enrollments")
    op.drop_index("ix_partner_school_enrollments_partner_id", table_name="partner_school_enrollments")
    op.drop_table("partner_school_enrollments")

    op.execute("DROP POLICY IF EXISTS partners_platform_only ON partners")
    op.drop_table("partners")

    permission_codes_sql = ", ".join(f"'{code}'" for code in _ALL_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({permission_codes_sql}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({permission_codes_sql})")

    role_codes_sql = ", ".join(f"'{code}'" for code in PR17_ROLE_NAMES)
    op.execute(f"DELETE FROM roles WHERE code IN ({role_codes_sql})")
