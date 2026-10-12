"""user_roles unique scopes (P1-1 — doublons concurrents d'attribution de rôle)

Garantit EN BASE qu'une même attribution de rôle n'existe qu'une fois, quelle que soit la portée.
Jusqu'ici, seule une vérification applicative SELECT-puis-INSERT
(`users/service.py::create_or_attach_user`) l'empêchait : deux requêtes concurrentes pouvaient
créer deux lignes identiques (constaté lors de l'audit PR #21).

PostgreSQL considère deux NULL comme distincts dans un index UNIQUE : un seul index
`UNIQUE(user_id, role_id, organization_id, school_id)` ne protégerait PAS les rôles globaux ni les
rôles org-wide. D'où trois index UNIQUE PARTIELS, un par portée :

- `uq_user_roles_global` : (user_id, role_id) WHERE organization_id IS NULL AND school_id IS NULL
- `uq_user_roles_org`    : (user_id, role_id, organization_id)
                           WHERE organization_id IS NOT NULL AND school_id IS NULL
- `uq_user_roles_school` : (user_id, role_id, school_id) WHERE school_id IS NOT NULL

Défensive : AVANT de créer les index, la migration compte les doublons historiques pour chacune
des trois portées (mêmes prédicats que les index). S'il en existe, elle ÉCHOUE avec un message
explicite (nombre de groupes par portée + requête de diagnostic) — elle ne supprime JAMAIS de
données. Le nettoyage, s'il est un jour nécessaire, est une décision opérateur explicite.

Strictement additive : aucune table, colonne ni donnée modifiée ; 0001-0023 inchangées.
Downgrade : suppression exacte de ces trois index.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-11

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (nom d'index, colonnes, prédicat) — source unique pour la détection ET la création.
SCOPES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("uq_user_roles_global", ("user_id", "role_id"), "organization_id IS NULL AND school_id IS NULL"),
    (
        "uq_user_roles_org",
        ("user_id", "role_id", "organization_id"),
        "organization_id IS NOT NULL AND school_id IS NULL",
    ),
    ("uq_user_roles_school", ("user_id", "role_id", "school_id"), "school_id IS NOT NULL"),
)


def _duplicate_groups(columns: tuple[str, ...], predicate: str) -> int:
    cols = ", ".join(columns)
    query = sa.text(
        f"SELECT count(*) FROM (SELECT 1 FROM user_roles WHERE {predicate} "
        f"GROUP BY {cols} HAVING count(*) > 1) AS duplicates"
    )
    return int(op.get_bind().execute(query).scalar_one())


def upgrade() -> None:
    found = {name: _duplicate_groups(columns, predicate) for name, columns, predicate in SCOPES}
    if any(found.values()):
        details = ", ".join(f"{name}: {count} groupe(s)" for name, count in found.items() if count)
        raise RuntimeError(
            "Migration 0024 interrompue : doublons historiques dans user_roles "
            f"({details}). Aucune donnée n'a été modifiée. Diagnostic, par exemple : "
            "SELECT user_id, role_id, organization_id, school_id, count(*) FROM user_roles "
            "GROUP BY 1, 2, 3, 4 HAVING count(*) > 1; — nettoyer explicitement puis relancer."
        )

    for name, columns, predicate in SCOPES:
        op.create_index(name, "user_roles", list(columns), unique=True, postgresql_where=sa.text(predicate))


def downgrade() -> None:
    for name, _columns, _predicate in reversed(SCOPES):
        op.drop_index(name, table_name="user_roles")
