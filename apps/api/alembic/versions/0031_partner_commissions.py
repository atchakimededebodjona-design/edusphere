"""partner commissions (décisions du 2026-11-15) + taux de TVA figé sur les factures d'abonnement

Strictement additive : aucune migration précédente modifiée, aucune donnée existante réécrite (seules
les DESCRIPTIONS de deux permissions réservées par 0023 sont mises à jour, les anciennes étant
restaurées au downgrade — même motif que 0027 pour `platform.subscriptions.read`).

1. `partners` : `commission_rate` (NUMERIC(5,2), NOT NULL, défaut 20, CHECK 0..100),
   `commission_rate_updated_at`, `commission_rate_updated_by` (traçabilité du taux, pas d'école donc
   pas d'audit_logs). Les partenaires existants reçoivent 20.
2. `subscription_invoices.vat_rate` (NUMERIC(5,2), NULL, CHECK 0..100) : taux de TVA figé à
   l'émission. NULL pour les factures existantes (aucune TVA enregistrée).
3. Table `partner_commissions` (voir app/modules/commissions/models.py, contraintes identiques) :
   une commission par facture payée (UNIQUE invoice_id et payment_id). RLS ENABLE + FORCE,
   policy « plateforme seulement » (motif `partners_platform_only`) : aucun compte d'école ne la lit.
4. Permission `platform.commissions.manage` (SUPER_ADMIN, PLATFORM_OWNER) ; descriptions de
   `platform.commissions.read` et `partner.commissions.read` (réservées en 0023) mises à jour.

Downgrade (ordre inverse) : permissions et descriptions, policy et table, colonnes. Les commissions
éventuelles sont perdues (inévitable pour retirer la table) ; les paiements et factures restent.

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-15
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import (
    COMMISSION_DESCRIPTIONS,
    COMMISSION_PLATFORM_PERMISSIONS,
    COMMISSION_PLATFORM_ROLE_PERMISSIONS,
)

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PLATFORM_WIDE = "current_setting('app.is_platform_wide', true) = 'true'"


def _uuid(name: str, target: str, ondelete: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey(target, ondelete=ondelete), nullable=nullable)


def upgrade() -> None:
    # --- 1. Taux de commission par partenaire --------------------------------------------------------
    op.add_column("partners", sa.Column("commission_rate", sa.Numeric(5, 2), nullable=False, server_default="20"))
    op.add_column("partners", sa.Column("commission_rate_updated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("partners", _uuid("commission_rate_updated_by", "users.id", "SET NULL", nullable=True))
    op.create_check_constraint(
        "ck_partners_commission_rate", "partners", "commission_rate >= 0 AND commission_rate <= 100"
    )

    # --- 2. Taux de TVA figé sur les factures d'abonnement ---------------------------------------------
    op.add_column("subscription_invoices", sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True))
    op.create_check_constraint(
        "ck_subscription_invoice_vat_rate", "subscription_invoices", "vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)"
    )

    # --- 3. Commissions ---------------------------------------------------------------------------------
    op.create_table(
        "partner_commissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        _uuid("partner_id", "partners.id", "RESTRICT"),
        _uuid("school_id", "schools.id", "RESTRICT"),
        _uuid("organization_id", "organizations.id", "RESTRICT"),
        _uuid("invoice_id", "subscription_invoices.id", "RESTRICT"),
        _uuid("payment_id", "subscription_payments.id", "RESTRICT"),
        sa.Column("base_amount_excl_vat", sa.Numeric(12, 2), nullable=False),
        sa.Column("rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="XOF"),
        sa.Column("status", sa.String(16), nullable=False, server_default="DUE"),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("paid_by", "users.id", "RESTRICT", nullable=True),
        sa.Column("settlement_method", sa.String(16), nullable=True),
        sa.Column("settlement_reference", sa.String(255), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        _uuid("cancelled_by", "users.id", "RESTRICT", nullable=True),
        sa.Column("cancel_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('DUE', 'PAID', 'CANCELLED')", name="ck_partner_commission_status"),
        sa.CheckConstraint("currency = 'XOF'", name="ck_partner_commission_currency"),
        sa.CheckConstraint("rate >= 0 AND rate <= 100", name="ck_partner_commission_rate"),
        sa.CheckConstraint("base_amount_excl_vat >= 0", name="ck_partner_commission_base"),
        sa.CheckConstraint("amount >= 0 AND amount = trunc(amount)", name="ck_partner_commission_amount_whole"),
        sa.CheckConstraint(
            "settlement_method IS NULL OR settlement_method IN ('MOBILE_MONEY', 'BANK_TRANSFER', 'CASH', 'OTHER')",
            name="ck_partner_commission_settlement_method",
        ),
        sa.CheckConstraint(
            "(status = 'PAID') = (paid_at IS NOT NULL) AND (status <> 'PAID' OR (paid_by IS NOT NULL "
            "AND settlement_method IS NOT NULL AND settlement_reference IS NOT NULL "
            "AND length(btrim(settlement_reference)) > 0))",
            name="ck_partner_commission_paid_traced",
        ),
        sa.CheckConstraint(
            "(status = 'CANCELLED') = (cancelled_at IS NOT NULL) AND (status <> 'CANCELLED' OR "
            "(cancelled_by IS NOT NULL AND cancel_reason IS NOT NULL AND length(btrim(cancel_reason)) > 0))",
            name="ck_partner_commission_cancel_traced",
        ),
        sa.UniqueConstraint("invoice_id", name="uq_partner_commissions_invoice"),
        sa.UniqueConstraint("payment_id", name="uq_partner_commissions_payment"),
    )
    op.create_index("ix_partner_commissions_partner_status", "partner_commissions", ["partner_id", "status"])
    op.create_index("ix_partner_commissions_created", "partner_commissions", ["created_at"])
    op.execute("ALTER TABLE partner_commissions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_commissions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY partner_commissions_platform_only ON partner_commissions "
        f"USING ({_PLATFORM_WIDE}) WITH CHECK ({_PLATFORM_WIDE})"
    )

    # --- 4. Permissions ---------------------------------------------------------------------------------
    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [{"id": uuid.uuid4(), "code": code, "description": text} for code, text in COMMISSION_PLATFORM_PERMISSIONS.items()],
    )
    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in COMMISSION_PLATFORM_ROLE_PERMISSIONS.items()
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
    for code, (description, _previous) in COMMISSION_DESCRIPTIONS.items():
        op.execute(
            sa.text("UPDATE permissions SET description = :description WHERE code = :code").bindparams(
                description=description, code=code
            )
        )


def downgrade() -> None:
    for code, (_description, previous) in COMMISSION_DESCRIPTIONS.items():
        op.execute(
            sa.text("UPDATE permissions SET description = :description WHERE code = :code").bindparams(
                description=previous, code=code
            )
        )
    codes_sql = ", ".join(f"'{code}'" for code in COMMISSION_PLATFORM_PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({codes_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes_sql})")

    op.execute("DROP POLICY IF EXISTS partner_commissions_platform_only ON partner_commissions")
    op.drop_table("partner_commissions")

    op.drop_constraint("ck_subscription_invoice_vat_rate", "subscription_invoices", type_="check")
    op.drop_column("subscription_invoices", "vat_rate")

    op.drop_constraint("ck_partners_commission_rate", "partners", type_="check")
    op.drop_column("partners", "commission_rate_updated_by")
    op.drop_column("partners", "commission_rate_updated_at")
    op.drop_column("partners", "commission_rate")
