"""retrait des comptes par la plateforme : désactivation et suppression (2026-11-18)

Strictement additive : aucune migration précédente modifiée, aucune donnée existante réécrite.

Le propriétaire de la plateforme doit pouvoir retirer un compte de l'application :
- « Désactiver » (réversible) : `users.is_active` existe déjà ;
- « Supprimer » (définitif) : les données personnelles du compte sont effacées (nom, email,
  téléphone, mot de passe), ses rôles et ses sessions retirés. La ligne `users` reste, pour que
  l'historique (paiements, caisses, appels, notes, audit) garde sa référence : plusieurs tables
  la protègent d'ailleurs (`ondelete=RESTRICT`).

1. `users.deleted_at` (date de suppression, NULL tant que le compte existe) et `users.deleted_by`
   (compte qui l'a supprimé, SET NULL) : traçabilité, faute de journal d'audit hors école.
2. Permission `platform.accounts.manage` (SUPER_ADMIN, PLATFORM_OWNER).

Downgrade : permission, puis colonnes. Les comptes déjà supprimés restent effacés (désactivés).

Revision ID: 0035
Revises: 0034
Create Date: 2026-11-18
"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import ACCOUNTS_PLATFORM_PERMISSIONS, ACCOUNTS_PLATFORM_ROLE_PERMISSIONS

revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column(
            "deleted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_users_deleted_by"),
            nullable=True,
        ),
    )

    permissions_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("description", sa.String),
    )
    op.bulk_insert(
        permissions_table,
        [{"id": uuid.uuid4(), "code": code, "description": text} for code, text in ACCOUNTS_PLATFORM_PERMISSIONS.items()],
    )
    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in ACCOUNTS_PLATFORM_ROLE_PERMISSIONS.items()
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
    codes_sql = ", ".join(f"'{code}'" for code in ACCOUNTS_PLATFORM_PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({codes_sql}))"
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({codes_sql})")
    op.drop_constraint("fk_users_deleted_by", "users", type_="foreignkey")
    op.drop_column("users", "deleted_by")
    op.drop_column("users", "deleted_at")
