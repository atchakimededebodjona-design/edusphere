"""fees (Phase 19 — School Fees & Billing)

5 tables volontairement (pas 7) : pas d'`Invoice` séparée (student_fees sert de ligne de dette
ET de mini-facture), pas de `Receipt` séparée (ses champs vivent sur payments, toujours 1:1) —
voir docs/phases/PHASE_19_DISCOVERY.md §14. Additive et non destructive : aucune modification des
migrations 0001-0008.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-05

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import PHASE19_PERMISSIONS, PHASE19_ROLE_PERMISSIONS

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_WITH_RLS = ["fee_categories", "fee_schedules", "student_fees", "payments", "payment_allocations"]


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
        "fee_categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "name", name="uq_fee_category_school_name"),
    )
    op.create_index("ix_fee_categories_school_id", "fee_categories", ["school_id"])
    op.create_index("ix_fee_categories_organization_id", "fee_categories", ["organization_id"])

    op.create_table(
        "fee_schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "fee_category_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fee_categories.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "academic_year_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("academic_years.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column(
            "scope_class_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("classes.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column(
            "scope_education_level_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("education_levels.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("is_optional", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_fee_schedule_amount_positive"),
        sa.CheckConstraint(
            "(scope_type = 'SCHOOL' AND scope_class_id IS NULL AND scope_education_level_id IS NULL) OR "
            "(scope_type = 'CLASS' AND scope_class_id IS NOT NULL AND scope_education_level_id IS NULL) OR "
            "(scope_type = 'LEVEL' AND scope_education_level_id IS NOT NULL AND scope_class_id IS NULL)",
            name="ck_fee_schedule_scope_consistency",
        ),
    )
    op.create_index("ix_fee_schedules_school_id", "fee_schedules", ["school_id"])
    op.create_index("ix_fee_schedules_organization_id", "fee_schedules", ["organization_id"])
    op.create_index("ix_fee_schedules_fee_category_id", "fee_schedules", ["fee_category_id"])
    op.create_index("ix_fee_schedules_academic_year_id", "fee_schedules", ["academic_year_id"])
    op.create_index("ix_fee_schedules_scope_class_id", "fee_schedules", ["scope_class_id"])
    op.create_index("ix_fee_schedules_scope_education_level_id", "fee_schedules", ["scope_education_level_id"])

    op.create_table(
        "student_fees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "fee_schedule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("fee_schedules.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount_due", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("student_id", "fee_schedule_id", name="uq_student_fee"),
        sa.CheckConstraint("amount_due > 0", name="ck_student_fee_amount_positive"),
    )
    op.create_index("ix_student_fees_school_id", "student_fees", ["school_id"])
    op.create_index("ix_student_fees_organization_id", "student_fees", ["organization_id"])
    op.create_index("ix_student_fees_student_id", "student_fees", ["student_id"])
    op.create_index("ix_student_fees_fee_schedule_id", "student_fees", ["fee_schedule_id"])

    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "student_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("students.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("paid_at", sa.Date, nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("payer_name", sa.String(255), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column(
            "recorded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="COMPLETED"),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "cancelled_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("cancellation_reason", sa.String(500), nullable=True),
        sa.Column("receipt_number", sa.String(32), nullable=False),
        sa.Column("pdf_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("school_id", "idempotency_key", name="uq_payment_idempotency"),
        sa.UniqueConstraint("school_id", "receipt_number", name="uq_payment_receipt_number"),
        sa.CheckConstraint("amount > 0", name="ck_payment_amount_positive"),
    )
    op.create_index("ix_payments_school_id", "payments", ["school_id"])
    op.create_index("ix_payments_organization_id", "payments", ["organization_id"])
    op.create_index("ix_payments_student_id", "payments", ["student_id"])

    op.create_table(
        "payment_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_org_scoped_columns(),
        sa.Column(
            "payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "student_fee_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("student_fees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("payment_id", "student_fee_id", name="uq_payment_allocation"),
        sa.CheckConstraint("amount > 0", name="ck_payment_allocation_amount_positive"),
    )
    op.create_index("ix_payment_allocations_school_id", "payment_allocations", ["school_id"])
    op.create_index("ix_payment_allocations_organization_id", "payment_allocations", ["organization_id"])
    op.create_index("ix_payment_allocations_payment_id", "payment_allocations", ["payment_id"])
    op.create_index("ix_payment_allocations_student_fee_id", "payment_allocations", ["student_fee_id"])

    # --- Seed RBAC ------------------------------------------------------------
    permission_ids: dict[str, uuid.UUID] = {code: uuid.uuid4() for code in PHASE19_PERMISSIONS}

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
            for code, description in PHASE19_PERMISSIONS.items()
        ],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in PHASE19_ROLE_PERMISSIONS.items()
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

    permission_codes_sql = ", ".join(f"'{code}'" for code in PHASE19_PERMISSIONS)
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({permission_codes_sql}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({permission_codes_sql})")

    op.drop_table("payment_allocations")
    op.drop_table("payments")
    op.drop_table("student_fees")
    op.drop_table("fee_schedules")
    op.drop_table("fee_categories")
