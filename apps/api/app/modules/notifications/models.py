import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Phase 21 (Communications & Notifications). Un seul modèle, volontairement minimal — pas
# d'`Announcement` séparé (voir PHASE_21_DISCOVERY.md §18/§21) : une annonce scolaire EST
# plusieurs lignes `Notification`, une par destinataire, créées en une fois. Pas de colonne
# `channel`/`status` (queued/sent/failed) : aucune queue, aucun retry n'existe nulle part dans ce
# projet pour justifier un tel état — une notification in-app est délivrée au moment où la ligne
# existe (voir Discovery §19).

NOTIFICATION_TYPES = ("ANNOUNCEMENT", "REPORT_CARD_PUBLISHED", "PAYMENT_RECORDED", "STUDENT_ABSENT", "FEE_OVERDUE")


class Notification(Base):
    """Table strictement privée par destinataire — contrairement à toutes les autres tables
    tenant-scopées de ce projet, la policy RLS n'est PAS basée sur l'organisation mais sur
    `recipient_user_id` (voir migration 0011) : un administrateur de la même école ne doit
    jamais pouvoir lire la notification d'un autre utilisateur, ce que la policy générique
    `{table}_tenant_isolation` (basée sur `app.tenant_org_ids`) ne garantirait pas à elle seule."""

    __tablename__ = "notifications"
    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_user_id", "created_at"),
        Index("ix_notifications_recipient_read", "recipient_user_id", "read_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Sprint 1.2 (rappels de retard de paiement) — lien optionnel vers la StudentFee à l'origine
    # d'une notification FEE_OVERDUE. Nullable : aucun des 4 types de notification précédents n'a
    # de référence structurelle de ce genre (voir Discovery — texte seul, jamais fiable pour
    # dédupliquer). Base de l'idempotence : un seul rappel par (student_fee_id, recipient_user_id),
    # garanti par l'index unique partiel `uq_notifications_fee_overdue_recipient` (migration 0013),
    # pas seulement par le contrôle applicatif dans fees/overdue_reminders.py.
    student_fee_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("student_fees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
