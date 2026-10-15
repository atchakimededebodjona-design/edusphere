"""cash register sessions (caisse scolaire, lot 3)

Strictement additive : aucune migration précédente modifiée, aucune donnée existante réécrite.

1. Tables `cash_sessions`, `cash_movements`, `cash_counts`, `cash_count_lines` (school_id +
   organization_id sur chacune, RLS `{table}_tenant_isolation` identique aux tables tenant
   existantes — migration 0009/0020). Les droits du rôle applicatif `edusphere_app` viennent des
   privilèges par défaut posés par 0002 (ALTER DEFAULT PRIVILEGES).
2. `payments.cash_session_id` (nullable, FK RESTRICT) : NULL pour tout paiement historique.
3. Index déterminés par les requêtes réelles (cash/service.py, cashier/router.py) :
   - `uq_cash_sessions_open_per_cashier` UNIQUE (school_id, cashier_user_id) WHERE status = 'OPEN'
     -> une seule session OPEN par caissier et par école (garantie même en concurrence) ET
        recherche de "ma session ouverte" (paiement, écran Ma caisse) ;
   - `ix_cash_sessions_school_status_opened` (school_id, status, opened_at) -> supervision,
     rapports (filtre école + statut éventuel + plage de dates sur opened_at) ;
   - `ix_payments_school_cash_session` (school_id, cash_session_id) WHERE cash_session_id IS NOT NULL
     -> agrégats/listes de paiements d'une session (partiel : les paiements historiques n'y sont pas) ;
   - `ix_payments_school_recorded_by_paid_at` (school_id, recorded_by, paid_at) -> journal du
     jour du caissier (GET /cashier/payments) ;
   - `ix_payments_school_paid_at` (school_id, paid_at) -> rapport par méthode sur une période ;
   - `ix_cash_movements_session_created` (cash_session_id, created_at) -> agrégats et liste ;
   - `ix_cash_counts_session_counted` (cash_session_id, counted_at) -> dernier comptage ;
   - `ix_cash_count_lines_count` (cash_count_id) -> lignes d'un comptage.
   Pas d'index séparé sur organization_id (aucune requête ne filtre l'organisation seule).
4. Permissions `cash.register.read|manage|review` (rbac/seed.py::CASH_REGISTER_*), aucune
   permission existante retirée.

Downgrade (ordre inverse) : permissions, puis index et colonne `payments.cash_session_id` (supprimée
AVANT les tables, donc aucune FK ne bloque), puis policies et tables. Les sessions/mouvements/
comptages éventuels sont perdus (inévitable pour retirer ces tables) ; les paiements, eux, restent
intacts (seul leur rattachement à une session disparaît).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-14

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import CASH_REGISTER_PERMISSIONS, CASH_REGISTER_ROLE_PERMISSIONS

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES_WITH_RLS = ["cash_sessions", "cash_movements", "cash_counts", "cash_count_lines"]


def _tenant_columns() -> list[sa.Column]:
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


def _user_fk(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(
        name, postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=nullable
    )


def upgrade() -> None:
    op.create_table(
        "cash_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        *_tenant_columns(),
        _user_fk("cashier_user_id"),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        _user_fk("opened_by"),
        sa.Column("opening_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        _user_fk("closed_by", nullable=True),
        sa.Column("expected_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("counted_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("variance_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("variance_reason", sa.String(32), nullable=True),
        sa.Column("variance_note", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_cash_session_status"),
        sa.CheckConstraint("opening_amount >= 0", name="ck_cash_session_opening_non_negative"),
        sa.CheckConstraint(
            "status = 'OPEN' OR (closed_at IS NOT NULL AND closed_by IS NOT NULL AND expected_amount IS NOT NULL "
            "AND counted_amount IS NOT NULL AND variance_amount IS NOT NULL)",
            name="ck_cash_session_closed_complete",
        ),
        sa.CheckConstraint(
            "variance_amount IS NULL OR variance_amount = counted_amount - expected_amount",
            name="ck_cash_session_variance_formula",
        ),
        sa.CheckConstraint(
            "variance_amount IS NULL OR variance_amount = 0 OR (variance_reason IS NOT NULL AND variance_note IS NOT NULL)",
            name="ck_cash_session_variance_justified",
        ),
    )
    op.create_index(
        "uq_cash_sessions_open_per_cashier",
        "cash_sessions",
        ["school_id", "cashier_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'OPEN'"),
    )
    op.create_index("ix_cash_sessions_school_status_opened", "cash_sessions", ["school_id", "status", "opened_at"])

    op.create_table(
        "cash_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cash_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cash_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_tenant_columns(),
        sa.Column("type", sa.String(16), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("reference", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        _user_fk("created_by"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_cash_movement_amount_positive"),
        sa.CheckConstraint("type IN ('CASH_IN', 'CASH_OUT', 'BANK_DEPOSIT', 'OTHER')", name="ck_cash_movement_type"),
        sa.CheckConstraint(
            "(type = 'CASH_IN' AND direction = 'IN') OR (type IN ('CASH_OUT', 'BANK_DEPOSIT') AND direction = 'OUT') "
            "OR (type = 'OTHER' AND direction IN ('IN', 'OUT'))",
            name="ck_cash_movement_direction",
        ),
        sa.CheckConstraint("length(btrim(reason)) > 0", name="ck_cash_movement_reason_present"),
        sa.UniqueConstraint("cash_session_id", "idempotency_key", name="uq_cash_movement_idempotency"),
    )
    op.create_index("ix_cash_movements_session_created", "cash_movements", ["cash_session_id", "created_at"])

    op.create_table(
        "cash_counts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cash_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cash_sessions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        *_tenant_columns(),
        _user_fk("counted_by"),
        sa.Column("counted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.CheckConstraint("total_amount >= 0", name="ck_cash_count_total_non_negative"),
    )
    op.create_index("ix_cash_counts_session_counted", "cash_counts", ["cash_session_id", "counted_at"])

    op.create_table(
        "cash_count_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "cash_count_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cash_counts.id", ondelete="CASCADE"), nullable=False
        ),
        *_tenant_columns(),
        sa.Column("denomination", sa.Numeric(12, 2), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.UniqueConstraint("cash_count_id", "denomination", name="uq_cash_count_line_denomination"),
        sa.CheckConstraint("denomination > 0", name="ck_cash_count_line_denomination_positive"),
        sa.CheckConstraint("quantity >= 0", name="ck_cash_count_line_quantity_non_negative"),
        sa.CheckConstraint("line_total = denomination * quantity", name="ck_cash_count_line_total"),
    )
    op.create_index("ix_cash_count_lines_count", "cash_count_lines", ["cash_count_id"])

    op.add_column(
        "payments",
        sa.Column(
            "cash_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cash_sessions.id", ondelete="RESTRICT", name="fk_payments_cash_session_id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_payments_school_cash_session",
        "payments",
        ["school_id", "cash_session_id"],
        postgresql_where=sa.text("cash_session_id IS NOT NULL"),
    )
    op.create_index("ix_payments_school_recorded_by_paid_at", "payments", ["school_id", "recorded_by", "paid_at"])
    op.create_index("ix_payments_school_paid_at", "payments", ["school_id", "paid_at"])

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

    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [
            {"id": uuid.uuid4(), "code": code, "description": description}
            for code, description in CASH_REGISTER_PERMISSIONS.items()
        ],
    )
    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in CASH_REGISTER_ROLE_PERMISSIONS.items()
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
    codes_sql = ", ".join(f"'{code}'" for code in CASH_REGISTER_PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({codes_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes_sql})")

    op.drop_index("ix_payments_school_paid_at", table_name="payments")
    op.drop_index("ix_payments_school_recorded_by_paid_at", table_name="payments")
    op.drop_index("ix_payments_school_cash_session", table_name="payments")
    op.drop_column("payments", "cash_session_id")

    for table in reversed(TABLES_WITH_RLS):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
    op.drop_table("cash_count_lines")
    op.drop_table("cash_counts")
    op.drop_table("cash_movements")
    op.drop_table("cash_sessions")
