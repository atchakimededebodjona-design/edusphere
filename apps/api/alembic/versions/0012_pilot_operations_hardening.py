"""pilot operations & data integrity hardening (Phase 22)

Ajoute une policy RLS sur les deux dernières tables sensibles qui n'en avaient aucune :
`user_sessions` et `password_reset_tokens` (gap identifié dans PHASE_22_DISCOVERY.md — protection
uniquement applicative jusqu'ici, contrairement à toutes les autres tables tenant/utilisateur-
scopées de ce projet).

Ni l'une ni l'autre n'a de colonne `organization_id`/`school_id` (ce sont des tables globales,
scopées par utilisateur, pas par tenant) : la policy compare `user_id` à
`app.current_user_id`, motif déjà utilisé par `notifications_recipient_isolation` (migration 0011)
pour `recipient_user_id`.

Une seule policy par table (même forme que `user_sessions_self_isolation` et
`notifications_recipient_isolation` de la migration 0011) : `user_id = app.current_user_id` ou
contexte plateforme. Plusieurs points d'écriture légitimes créent un token/une session pour un
utilisateur AUTRE que l'appelant courant (auto-inscription anonyme, refresh de token, invitation
d'un nouvel utilisateur par un admin — `users/service.py::create_or_attach_user`) : chacun élargit
explicitement le contexte via `set_platform_wide_context` avant l'écriture (voir
`auth/service.py::_issue_tokens`/`_get_active_session`/`request_password_reset`/`reset_password`
et `users/service.py::create_or_attach_user`, qui restaure ensuite le contexte tenant normal de
l'admin appelant avant ses lectures suivantes, pour ne pas dé-filtrer
`tests/test_users.py::test_create_with_existing_email_attaches_role_without_duplicate`).

Remarque technique qui a guidé ce choix (plutôt qu'une policy INSERT séparée, inconditionnelle,
qui semblait plus simple au premier abord) : un INSERT via SQLAlchemy ORM déclenche un `RETURNING`
implicite pour récupérer les colonnes à valeur par défaut serveur (ex. `created_at`) — Postgres
exige alors que la ligne insérée soit également visible par la policy de SELECT pour pouvoir la
retourner, pas seulement autorisée par le WITH CHECK de l'INSERT. Une policy INSERT permissive
séparée ne suffit donc pas : il faut que le contexte de la transaction entière rende la ligne
visible, d'où le choix d'élargir explicitement via `set_platform_wide_context` plutôt que
d'assouplir uniquement l'INSERT.

Additive et non destructive. Aucune modification des migrations 0001-0011.

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-06

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- user_sessions -----------------------------------------------------------------------
    op.execute("ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_sessions FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY user_sessions_self_isolation ON user_sessions
        USING (
            current_setting('app.is_platform_wide', true) = 'true'
            OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )
        """
    )

    # --- password_reset_tokens ----------------------------------------------------------------
    op.execute("ALTER TABLE password_reset_tokens ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE password_reset_tokens FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY password_reset_tokens_self_isolation ON password_reset_tokens
        USING (
            current_setting('app.is_platform_wide', true) = 'true'
            OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS password_reset_tokens_self_isolation ON password_reset_tokens")
    op.execute("ALTER TABLE password_reset_tokens NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE password_reset_tokens DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS user_sessions_self_isolation ON user_sessions")
    op.execute("ALTER TABLE user_sessions NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE user_sessions DISABLE ROW LEVEL SECURITY")
