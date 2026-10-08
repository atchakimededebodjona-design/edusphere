"""audit log (PR #14 — journal d'audit administratif)

Ajoute une nouvelle table `audit_logs`, écrite UNIQUEMENT par
`app/modules/audit/service.py::record_audit_event`, appelée dans la MÊME transaction que chacune
des actions administratives sensibles suivantes (jamais en dry_run) :

- annulation de paiement (fees/service.py::cancel_payment)
- ajustement manuel de amount_due d'un StudentFee (fees/router.py::update_student_fee)
- changement de rôle / activation-désactivation d'un utilisateur (users/service.py::update_user_in_school)
- publication d'un bulletin (report_cards/router.py::publish_report_card)
- confirmation réelle d'une promotion/sortie en masse (students/service.py::bulk_promote_students)
- confirmation réelle d'une affectation en masse (students/service.py::bulk_assign_students_to_class)

RLS : policy générique `{table}_tenant_isolation` basée sur `organization_id`, même motif que
toutes les tables tenant existantes (voir migration 0019 pour le même schéma de policy).

Nouvelle permission `audit.read` (catalogue RBAC, voir rbac/seed.py::AUDIT_PERMISSIONS) — accordée
uniquement à SUPER_ADMIN/PLATFORM_SUPPORT/SCHOOL_ADMIN/DIRECTOR, jamais à TEACHER/STAFF/ACCOUNTANT.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-08

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import AUDIT_PERMISSIONS, AUDIT_ROLE_PERMISSIONS

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
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
            "actor_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.String(500), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_logs_school_id", "audit_logs", ["school_id"])
    op.create_index("ix_audit_logs_organization_id", "audit_logs", ["organization_id"])
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_school_id_created_at", "audit_logs", ["school_id", "created_at"])
    op.create_index("ix_audit_logs_action_created_at", "audit_logs", ["action", "created_at"])

    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_logs_tenant_isolation ON audit_logs
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

    # --- Seed RBAC (même motif que migration 0009_fees.py) ---------------------------------
    permission_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in AUDIT_PERMISSIONS}

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
            for code, description in AUDIT_PERMISSIONS.items()
        ],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in AUDIT_ROLE_PERMISSIONS.items()
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


def downgrade() -> None:
    permission_codes_sql = ", ".join(f"'{code}'" for code in AUDIT_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({permission_codes_sql}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({permission_codes_sql})")

    op.execute("DROP POLICY IF EXISTS audit_logs_tenant_isolation ON audit_logs")
    op.drop_table("audit_logs")
