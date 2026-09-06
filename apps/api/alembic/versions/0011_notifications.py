"""notifications (Phase 21 — Communications & Notifications)

Un seul modèle `Notification` (pas d'`Announcement` séparé — voir
docs/phases/PHASE_21_DISCOVERY.md §18/§21). Additive et non destructive : aucune modification des
migrations 0001-0010.

Policy RLS DÉLIBÉRÉMENT DIFFÉRENTE du motif générique `{table}_tenant_isolation` utilisé par
toutes les autres tables (basé sur `app.tenant_org_ids`, donc sur l'appartenance à l'organisation).
`notifications` est strictement privée par destinataire : la policy restreint la lecture à
`recipient_user_id = current_user_id` (ou contexte plateforme), jamais à l'appartenance
organisationnelle seule — un administrateur de la même école ne doit jamais pouvoir lire la
notification d'un autre utilisateur via une policy basée sur l'organisation. Voir
`app/modules/notifications/models.py` et `app/modules/notifications/service.py::
create_notifications` pour le détail du contexte d'écriture (élargi via
`set_platform_wide_context`, motif déjà utilisé par `auth/service.py::register`).

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-06

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import PHASE21_PERMISSIONS, PHASE21_ROLE_PERMISSIONS

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notifications",
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
            "recipient_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notifications_school_id", "notifications", ["school_id"])
    op.create_index("ix_notifications_organization_id", "notifications", ["organization_id"])
    op.create_index("ix_notifications_recipient_user_id", "notifications", ["recipient_user_id"])
    op.create_index("ix_notifications_recipient_created", "notifications", ["recipient_user_id", "created_at"])
    op.create_index("ix_notifications_recipient_read", "notifications", ["recipient_user_id", "read_at"])

    # --- Seed RBAC ------------------------------------------------------------
    permission_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in PHASE21_PERMISSIONS}

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
            for code, description in PHASE21_PERMISSIONS.items()
        ],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in PHASE21_ROLE_PERMISSIONS.items()
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

    # --- Row Level Security — policy spécifique par destinataire, PAS le motif générique -------
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY notifications_recipient_isolation ON notifications
        USING (
            current_setting('app.is_platform_wide', true) = 'true'
            OR recipient_user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS notifications_recipient_isolation ON notifications")

    permission_codes_sql = ", ".join(f"'{code}'" for code in PHASE21_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({permission_codes_sql}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({permission_codes_sql})")

    op.drop_table("notifications")
