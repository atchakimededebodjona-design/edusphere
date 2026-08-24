"""auth + multi-tenancy

Phase 1 : users, organizations, schools, RBAC (roles/permissions), sessions,
password reset tokens. Active PostgreSQL Row Level Security sur `schools` et
`user_roles`, et crée un rôle Postgres applicatif non-superutilisateur
(`edusphere_app`) sans lequel RLS n'aurait aucun effet (un superutilisateur
contourne toujours RLS — le rôle `edusphere` de la Phase 0 est superutilisateur
car créé via POSTGRES_USER de l'image Docker officielle).

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-24

"""

import os
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import PERMISSIONS, ROLE_NAMES, ROLE_PERMISSIONS

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Tables ---------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False, unique=True),
        sa.Column("country_code", sa.String(2), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Africa/Lome"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("is_platform_admin", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "schools",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Africa/Lome"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("organization_id", "slug", name="uq_school_org_slug"),
    )
    op.create_index("ix_schools_organization_id", "schools", ["organization_id"])

    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("is_system_role", sa.Boolean, nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_roles_code", "roles", ["code"])

    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "user_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_user_roles_user_id", "user_roles", ["user_id"])
    op.create_index("ix_user_roles_organization_id", "user_roles", ["organization_id"])
    op.create_index("ix_user_roles_school_id", "user_roles", ["school_id"])

    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("refresh_token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("device_id", sa.String(255), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])

    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])

    # --- Seed RBAC (rôles + permissions + mapping) -----------------------
    role_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in ROLE_NAMES}
    permission_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in PERMISSIONS}

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
            {"id": role_ids[code], "code": code, "name": name, "is_system_role": True}
            for code, name in ROLE_NAMES.items()
        ],
    )

    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [
            {"id": permission_ids[code], "code": code, "description": description}
            for code, description in PERMISSIONS.items()
        ],
    )

    role_permissions_table = sa.table(
        "role_permissions",
        sa.column("role_id", postgresql.UUID(as_uuid=True)),
        sa.column("permission_id", postgresql.UUID(as_uuid=True)),
    )
    role_permission_rows = [
        {"role_id": role_ids[role_code], "permission_id": permission_ids[perm_code]}
        for role_code, perm_codes in ROLE_PERMISSIONS.items()
        for perm_code in perm_codes
    ]
    if role_permission_rows:
        op.bulk_insert(role_permissions_table, role_permission_rows)

    # --- Rôle Postgres applicatif non-superutilisateur --------------------
    # Sans ce rôle dédié, l'API se connecterait avec le rôle superutilisateur `edusphere`
    # (créé via POSTGRES_USER par l'image Docker officielle de Postgres), qui contourne
    # TOUJOURS Row Level Security. RLS ne peut avoir d'effet réel que sur un rôle non
    # superutilisateur et sans l'attribut BYPASSRLS.
    app_db_password = os.environ.get("APP_DB_PASSWORD", "changeme_app_role_local_only")
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'edusphere_app') THEN
                    CREATE ROLE edusphere_app LOGIN;
                END IF;
            END
            $$;
            """
        )
    )
    # ALTER ROLE n'accepte pas les paramètres liés ($1) pour la clause PASSWORD ; le mot de
    # passe vient d'une variable d'environnement contrôlée par nous (APP_DB_PASSWORD), pas
    # d'une entrée utilisateur — on l'échappe simplement (guillemets simples doublés).
    escaped_password = app_db_password.replace("'", "''")
    op.execute(
        f"ALTER ROLE edusphere_app WITH LOGIN PASSWORD '{escaped_password}' "
        "NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION"
    )
    op.execute("GRANT CONNECT ON DATABASE edusphere TO edusphere_app")
    op.execute("GRANT USAGE ON SCHEMA public TO edusphere_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO edusphere_app")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO edusphere_app"
    )

    # --- Row Level Security -----------------------------------------------
    op.execute("ALTER TABLE schools ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schools FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY schools_tenant_isolation ON schools
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

    op.execute("ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_roles FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY user_roles_tenant_isolation ON user_roles
        USING (
            current_setting('app.is_platform_wide', true) = 'true'
            OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
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
    op.execute("DROP POLICY IF EXISTS user_roles_tenant_isolation ON user_roles")
    op.execute("ALTER TABLE user_roles NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_roles DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS schools_tenant_isolation ON schools")
    op.execute("ALTER TABLE schools NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schools DISABLE ROW LEVEL SECURITY")

    op.execute("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM edusphere_app")
    op.execute("REVOKE ALL PRIVILEGES ON SCHEMA public FROM edusphere_app")
    op.execute("REVOKE CONNECT ON DATABASE edusphere FROM edusphere_app")
    op.execute("DROP ROLE IF EXISTS edusphere_app")

    op.drop_table("password_reset_tokens")
    op.drop_table("user_sessions")
    op.drop_table("user_roles")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("schools")
    op.drop_table("users")
    op.drop_table("organizations")
