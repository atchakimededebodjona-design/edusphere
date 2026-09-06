import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

NotificationType = Literal["ANNOUNCEMENT", "REPORT_CARD_PUBLISHED", "PAYMENT_RECORDED"]


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    type: NotificationType
    title: str
    body: str
    created_at: datetime
    read_at: datetime | None


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    # Curseur à repasser en `before` pour la page suivante (plus ancien que le dernier élément
    # retourné) — `None` s'il n'y a plus rien à charger. Pas de convention de pagination
    # préexistante dans ce dépôt (confirmé par la Discovery Phase 19/21) : premier choix, par
    # keyset sur `created_at` plutôt que par offset, pour rester correct même si de nouvelles
    # notifications arrivent entre deux pages.
    next_before: datetime | None


class UnreadCountOut(BaseModel):
    count: int


AnnouncementTargetType = Literal["SCHOOL", "CLASS"]


class AnnouncementCreate(BaseModel):
    school_id: uuid.UUID
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=2000)
    target_type: AnnouncementTargetType
    class_ids: list[uuid.UUID] | None = None


class AnnouncementResult(BaseModel):
    recipient_count: int


class AnnouncementHistoryEntry(BaseModel):
    """Phase 22 — une ligne = une annonce déjà envoyée (regroupement de ses `Notification`
    destinataires). La cible (SCHOOL/CLASS) n'est pas persistée par le modèle `Notification`
    (voir service.py::create_announcement) : volontairement absente ici plutôt qu'inventée."""

    title: str
    body: str
    type: NotificationType
    created_at: datetime
    recipient_count: int


class AnnouncementHistoryOut(BaseModel):
    items: list[AnnouncementHistoryEntry]
    next_before: datetime | None
