import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


class AuditLogOut(BaseModel):
    """Construit explicitement champ par champ par `audit/service.py::list_audit_logs` (jamais
    `model_validate(orm_obj)`) : `actor_email` n'est pas une colonne de `AuditLog`, elle est
    résolue par une jointure sur `users` (compte encore existant) ou, à défaut, relue depuis le
    cliché `audit_metadata.actor_email` pris au moment de l'action — jamais nulle sauf si aucune
    des deux sources n'a pu la fournir."""

    id: uuid.UUID
    school_id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    summary: str
    metadata: dict[str, Any] | None
    created_at: datetime


class AuditLogsOut(BaseModel):
    """Même forme de pagination que `fees/schemas.py::OverdueFeesOut` — convention déjà établie
    dans ce dépôt pour une liste paginée par page/page_size plutôt qu'un curseur."""

    items: list[AuditLogOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class AuditLogFilters(BaseModel):
    """Paramètres de filtrage optionnels de `GET /audit-logs` — regroupés ici pour éviter une
    signature de fonction à rallonge côté service, même motif que les payloads de `fees/schemas.py`."""

    date_from: date | None = None
    date_to: date | None = None
    actor_user_id: uuid.UUID | None = None
    action: str | None = None
    entity_type: str | None = None
    entity_id: uuid.UUID | None = None
