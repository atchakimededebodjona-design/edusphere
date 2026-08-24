"""academics (Phase 2 — administration scolaire)

Années scolaires, périodes, niveaux, matières, salles, classes, association
classe<->matière, affectations enseignants. Toutes les tables portent
organization_id (dénormalisé depuis school_id, même mécanisme RLS que
user_roles en Phase 1). RLS activée et forcée sur les 8 tables.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-24

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import PHASE2_PERMISSIONS, PHASE2_ROLE_PERMISSIONS

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_WITH_RLS = [
    "academic_years",
    "academic_terms",
    "education_levels",
    "subjects",
    "rooms",
    "classes",
    "class_subjects",
    "teacher_assignments",
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
    # --- Tables ---------------------------------------------------------
    op.create_table(
        "academic_years",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_academic_year_school_name"),
    )
    op.create_index("ix_academic_years_school_id", "academic_years", ["school_id"])
    op.create_index("ix_academic_years_organization_id", "academic_years", ["organization_id"])

    op.create_table(
        "academic_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "academic_year_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_years.id", ondelete="CASCADE"),
            nullable=False,
        ),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("start_date", sa.Date, nullable=False),
        sa.Column("end_date", sa.Date, nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_academic_terms_academic_year_id", "academic_terms", ["academic_year_id"])
    op.create_index("ix_academic_terms_school_id", "academic_terms", ["school_id"])
    op.create_index("ix_academic_terms_organization_id", "academic_terms", ["organization_id"])

    op.create_table(
        "education_levels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("order_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_education_level_school_name"),
    )
    op.create_index("ix_education_levels_school_id", "education_levels", ["school_id"])
    op.create_index("ix_education_levels_organization_id", "education_levels", ["organization_id"])

    op.create_table(
        "subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("code", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_subject_school_name"),
    )
    op.create_index("ix_subjects_school_id", "subjects", ["school_id"])
    op.create_index("ix_subjects_organization_id", "subjects", ["organization_id"])

    op.create_table(
        "rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_room_school_name"),
    )
    op.create_index("ix_rooms_school_id", "rooms", ["school_id"])
    op.create_index("ix_rooms_organization_id", "rooms", ["organization_id"])

    op.create_table(
        "classes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "academic_year_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_years.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "education_level_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("education_levels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("capacity", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("academic_year_id", "education_level_id", "name", name="uq_class_year_level_name"),
    )
    op.create_index("ix_classes_school_id", "classes", ["school_id"])
    op.create_index("ix_classes_organization_id", "classes", ["organization_id"])
    op.create_index("ix_classes_academic_year_id", "classes", ["academic_year_id"])
    op.create_index("ix_classes_education_level_id", "classes", ["education_level_id"])

    op.create_table(
        "class_subjects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "class_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "subject_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("coefficient", sa.Numeric(4, 2), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("class_id", "subject_id", name="uq_class_subject"),
    )
    op.create_index("ix_class_subjects_school_id", "class_subjects", ["school_id"])
    op.create_index("ix_class_subjects_organization_id", "class_subjects", ["organization_id"])
    op.create_index("ix_class_subjects_class_id", "class_subjects", ["class_id"])
    op.create_index("ix_class_subjects_subject_id", "class_subjects", ["subject_id"])

    op.create_table(
        "teacher_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "class_subject_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("class_subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "class_subject_id", name="uq_teacher_assignment"),
    )
    op.create_index("ix_teacher_assignments_school_id", "teacher_assignments", ["school_id"])
    op.create_index("ix_teacher_assignments_organization_id", "teacher_assignments", ["organization_id"])
    op.create_index("ix_teacher_assignments_user_id", "teacher_assignments", ["user_id"])
    op.create_index("ix_teacher_assignments_class_subject_id", "teacher_assignments", ["class_subject_id"])

    # --- Seed RBAC (nouvelles permissions + mapping) -----------------------
    permission_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in PHASE2_PERMISSIONS}

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
            for code, description in PHASE2_PERMISSIONS.items()
        ],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in PHASE2_ROLE_PERMISSIONS.items()
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
    # Grants : couvertes automatiquement par le "ALTER DEFAULT PRIVILEGES" posé en 0002 pour
    # edusphere_app (les nouvelles tables créées par le rôle superutilisateur en héritent).
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

    permission_codes_sql = ", ".join(f"'{code}'" for code in PHASE2_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({permission_codes_sql}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({permission_codes_sql})")

    op.drop_table("teacher_assignments")
    op.drop_table("class_subjects")
    op.drop_table("classes")
    op.drop_table("rooms")
    op.drop_table("subjects")
    op.drop_table("education_levels")
    op.drop_table("academic_terms")
    op.drop_table("academic_years")
