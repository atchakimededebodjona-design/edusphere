"""grades (Phase 4 — académique : évaluations, notes, moyennes, classement)

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-24

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import PHASE4_PERMISSIONS, PHASE4_ROLE_PERMISSIONS

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_WITH_RLS = [
    "assessment_types",
    "assessments",
    "assessment_results",
    "student_subject_averages",
    "student_term_averages",
]


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
    op.create_table(
        "assessment_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_assessment_type_school_name"),
    )
    op.create_index("ix_assessment_types_school_id", "assessment_types", ["school_id"])
    op.create_index("ix_assessment_types_organization_id", "assessment_types", ["organization_id"])

    op.create_table(
        "assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "class_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "academic_term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assessment_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("max_score", sa.Numeric(5, 2), nullable=False, server_default="20"),
        sa.Column("weight", sa.Numeric(4, 2), nullable=False, server_default="1"),
        sa.Column("assessment_date", sa.Date, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_assessments_school_id", "assessments", ["school_id"])
    op.create_index("ix_assessments_organization_id", "assessments", ["organization_id"])
    op.create_index("ix_assessments_class_subject_id", "assessments", ["class_subject_id"])
    op.create_index("ix_assessments_academic_term_id", "assessments", ["academic_term_id"])
    op.create_index("ix_assessments_assessment_type_id", "assessments", ["assessment_type_id"])

    op.create_table(
        "assessment_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "assessment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("assessments.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column("is_absent", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("assessment_id", "student_id", name="uq_assessment_result"),
    )
    op.create_index("ix_assessment_results_school_id", "assessment_results", ["school_id"])
    op.create_index("ix_assessment_results_organization_id", "assessment_results", ["organization_id"])
    op.create_index("ix_assessment_results_assessment_id", "assessment_results", ["assessment_id"])
    op.create_index("ix_assessment_results_student_id", "assessment_results", ["student_id"])

    op.create_table(
        "student_subject_averages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "class_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "academic_term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("average", sa.Numeric(5, 2), nullable=True),
        sa.Column("rank", sa.Integer, nullable=True),
        sa.Column("appreciation", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "class_subject_id", "academic_term_id", name="uq_student_subject_average"),
    )
    op.create_index("ix_student_subject_averages_school_id", "student_subject_averages", ["school_id"])
    op.create_index("ix_student_subject_averages_organization_id", "student_subject_averages", ["organization_id"])
    op.create_index("ix_student_subject_averages_student_id", "student_subject_averages", ["student_id"])
    op.create_index("ix_student_subject_averages_class_subject_id", "student_subject_averages", ["class_subject_id"])
    op.create_index("ix_student_subject_averages_academic_term_id", "student_subject_averages", ["academic_term_id"])

    op.create_table(
        "student_term_averages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "academic_term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("average", sa.Numeric(5, 2), nullable=True),
        sa.Column("rank", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "academic_term_id", name="uq_student_term_average"),
    )
    op.create_index("ix_student_term_averages_school_id", "student_term_averages", ["school_id"])
    op.create_index("ix_student_term_averages_organization_id", "student_term_averages", ["organization_id"])
    op.create_index("ix_student_term_averages_student_id", "student_term_averages", ["student_id"])
    op.create_index("ix_student_term_averages_academic_term_id", "student_term_averages", ["academic_term_id"])

    # --- Seed RBAC ------------------------------------------------------------
    permission_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in PHASE4_PERMISSIONS}

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
            for code, description in PHASE4_PERMISSIONS.items()
        ],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in PHASE4_ROLE_PERMISSIONS.items()
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

    permission_codes_sql = ", ".join(f"'{code}'" for code in PHASE4_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({permission_codes_sql}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({permission_codes_sql})")

    op.drop_table("student_term_averages")
    op.drop_table("student_subject_averages")
    op.drop_table("assessment_results")
    op.drop_table("assessments")
    op.drop_table("assessment_types")
