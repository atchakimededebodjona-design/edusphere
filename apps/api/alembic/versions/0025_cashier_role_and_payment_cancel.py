"""cashier role and payment cancel (caisse scolaire, lot 1)

Strictement additive : aucune table ni colonne, aucune migration précédente modifiée.

1. Nouveau rôle système `CAISSIER` (« Caissier ») — rôle scolaire scopé à une école, représentant
   l'administration pour l'encaissement en espèces. Inséré via `op.bulk_insert` (même motif que
   0002/0023), depuis `rbac/seed.py::CASHIER_ROLE_NAMES` (dict dédié : `ROLE_NAMES`, importé par
   0002, n'est jamais modifié).
2. Nouvelle permission `payments.cancel` (« Annuler un paiement ») : l'annulation est désormais
   distincte de l'enregistrement. `POST /payments/{id}/cancel` l'exige (fees/router.py).
3. Attributions (`CASHIER_ROLE_PERMISSIONS`) :
   - CAISSIER : fees.read, payments.read, payments.manage (jamais fees.manage, payments.cancel,
     audit.read) ;
   - payments.cancel : SUPER_ADMIN, SCHOOL_ADMIN, DIRECTOR, ACCOUNTANT (rôles qui annulaient déjà
     via payments.manage — aucun pouvoir perdu).
4. Description de `payments.manage` mise à jour : « Enregistrer des paiements ».

Toutes les permissions existantes sont conservées.

Downgrade (ordre inverse) : description d'origine restaurée ; attributions et permission
`payments.cancel` supprimées ; attributions du CAISSIER puis le rôle supprimés (les éventuelles
UserRole CAISSIER disparaissent avec le rôle, ON DELETE CASCADE de 0002 — inévitable pour retirer le
rôle, aucune autre donnée touchée).

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-13

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.modules.rbac.seed import (
    CASHIER_PERMISSIONS,
    CASHIER_ROLE_NAMES,
    CASHIER_ROLE_PERMISSIONS,
    PAYMENTS_MANAGE_DESCRIPTION,
    PAYMENTS_MANAGE_PREVIOUS_DESCRIPTION,
)

revision: str = "0025"
down_revision: Union[str, None] = "0024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _sql_list(values: list[str]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def upgrade() -> None:
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
            {"id": uuid.uuid4(), "code": code, "name": name, "is_system_role": True}
            for code, name in CASHIER_ROLE_NAMES.items()
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
        [{"id": uuid.uuid4(), "code": code, "description": description} for code, description in CASHIER_PERMISSIONS.items()],
    )

    pairs = [
        f"('{role_code}', '{perm_code}')"
        for role_code, perm_codes in CASHIER_ROLE_PERMISSIONS.items()
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

    op.execute(
        sa.text("UPDATE permissions SET description = :description WHERE code = 'payments.manage'").bindparams(
            description=PAYMENTS_MANAGE_DESCRIPTION
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("UPDATE permissions SET description = :description WHERE code = 'payments.manage'").bindparams(
            description=PAYMENTS_MANAGE_PREVIOUS_DESCRIPTION
        )
    )

    new_permission_codes = _sql_list(list(CASHIER_PERMISSIONS))
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE permission_id IN (SELECT id FROM permissions WHERE code IN ({new_permission_codes}))
        """
    )
    op.execute(f"DELETE FROM permissions WHERE code IN ({new_permission_codes})")

    new_role_codes = _sql_list(list(CASHIER_ROLE_NAMES))
    op.execute(
        f"""
        DELETE FROM role_permissions
        WHERE role_id IN (SELECT id FROM roles WHERE code IN ({new_role_codes}))
        """
    )
    op.execute(f"DELETE FROM roles WHERE code IN ({new_role_codes})")
