"""appareils abonnés aux notifications téléphone (Web Push, 2026-11-17)

Strictement additive : aucune migration précédente modifiée, aucune donnée existante réécrite.

Une annonce doit pouvoir prévenir ses destinataires même quand EduLinkage est fermé sur leur
téléphone : chaque navigateur qui accepte les notifications enregistre ici son adresse d'envoi
(`endpoint`, fournie par le service de notification du navigateur : Google, Mozilla, Apple…) et ses
clés de chiffrement (`p256dh`, `auth`). Le serveur y envoie une notification chiffrée.

1. Table `push_devices` : `user_id` (cascade à la suppression du compte), `endpoint` UNIQUE (un
   navigateur = un seul compte à la fois), clés, `user_agent`, dates de création et de dernier envoi.
2. RLS : comme `user_sessions` (migration 0012) — un compte ne voit que ses propres appareils ;
   l'envoi aux destinataires passe par le contexte plateforme, après résolution des destinataires.

Les droits du rôle applicatif viennent des privilèges par défaut posés par la migration 0002.

Downgrade : suppression de la table (les abonnements sont perdus ; chacun réactivera).

Revision ID: 0034
Revises: 0033
Create Date: 2026-11-17
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "push_devices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(255), nullable=False),
        sa.Column("auth", sa.String(255), nullable=False),
        sa.Column("user_agent", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("endpoint", name="uq_push_devices_endpoint"),
    )
    op.execute("ALTER TABLE push_devices ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE push_devices FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY push_devices_self_isolation ON push_devices
        USING (
            current_setting('app.is_platform_wide', true) = 'true'
            OR user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS push_devices_self_isolation ON push_devices")
    op.drop_table("push_devices")
