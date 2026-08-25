"""report_cards (Phase 5 — bulletins : templates, génération PDF, QR, publication)

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-25

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import PHASE5_PERMISSIONS, PHASE5_ROLE_PERMISSIONS

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_WITH_RLS = ["report_card_templates", "report_cards"]


def _org_scoped_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "school_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.add_column("schools", sa.Column("logo_path", sa.String(500), nullable=True))

    op.create_table(
        "report_card_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("html_content", sa.Text, nullable=False),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_report_card_template_school_name"),
    )
    op.create_index("ix_report_card_templates_school_id", "report_card_templates", ["school_id"])
    op.create_index("ix_report_card_templates_organization_id", "report_card_templates", ["organization_id"])

    op.create_table(
        "report_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "class_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "academic_term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("report_card_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("verification_code", sa.String(64), nullable=False, unique=True),
        sa.Column("pdf_path", sa.String(500), nullable=False),
        sa.Column("general_average", sa.Numeric(5, 2), nullable=True),
        sa.Column("general_rank", sa.Integer, nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "generated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "academic_term_id", name="uq_report_card_student_term"),
    )
    op.create_index("ix_report_cards_school_id", "report_cards", ["school_id"])
    op.create_index("ix_report_cards_organization_id", "report_cards", ["organization_id"])
    op.create_index("ix_report_cards_student_id", "report_cards", ["student_id"])
    op.create_index("ix_report_cards_class_id", "report_cards", ["class_id"])
    op.create_index("ix_report_cards_academic_term_id", "report_cards", ["academic_term_id"])
    op.create_index("ix_report_cards_verification_code", "report_cards", ["verification_code"])

    # --- Seed RBAC ------------------------------------------------------------
    permission_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in PHASE5_PERMISSIONS}

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
            for code, description in PHASE5_PERMISSIONS.items()
        ],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in PHASE5_ROLE_PERMISSIONS.items()
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

    # --- Row Level Security -------------------------------------------------
    for table in TABLES_WITH_RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
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
    for table in reversed(TABLES_WITH_RLS):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")

    permission_codes_sql = ", ".join(f"'{code}'" for code in PHASE5_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({permission_codes_sql}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({permission_codes_sql})")

    op.drop_table("report_cards")
    op.drop_table("report_card_templates")
    op.drop_column("schools", "logo_path")
