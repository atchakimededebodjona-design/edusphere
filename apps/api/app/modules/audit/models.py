import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# PR #14 (journal d'audit administratif) — voir AUDIT EDULINKAGE §13. Table purement additive,
# écrite UNIQUEMENT par `audit/service.py::record_audit_event`, jamais exposée en écriture via
# l'API (seul GET /audit-logs existe, voir router.py) : un client ne peut donc jamais forger un
# événement pour une autre école, seul le code serveur déjà authentifié/autorisé y écrit, avec le
# school_id/organization_id de la ressource métier déjà validée par l'appelant (jamais un
# school_id brut de payload).
#
# `action`/`entity_type` sont de simples `String` non contraints par un CHECK — même convention
# que `notifications.type`/`student_fees.status`/`payments.status` dans ce dépôt (voir
# fees/models.py) : les valeurs documentées vivent dans `audit/service.py`, pas dans une
# contrainte base de données ni un `Literal` Pydantic, pour ne jamais bloquer l'insertion d'un
# futur type d'événement avant une migration dédiée.


class AuditLog(Base):
    """Une ligne = un événement administratif sensible déjà survenu (jamais une tentative
    échouée — voir `record_audit_event`). Ne stocke jamais de mot de passe, hash, jeton, secret,
    contenu complet de note/bulletin ni donnée bancaire : uniquement ce qui est strictement utile
    pour répondre à "qui a fait quoi, quand, sur quoi" (voir `summary`/`audit_metadata`)."""

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL (jamais CASCADE) : la suppression d'un compte ne doit jamais faire disparaître la
    # trace de ce qu'il a fait — voir test "actor supprimé => audit conservé avec actor_user_id
    # NULL". L'identité de l'acteur au moment de l'action est de toute façon préservée dans
    # `audit_metadata.actor_email` (immuable, jamais mise à jour après coup).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    # Nommé `audit_metadata` côté Python uniquement : `metadata` est un attribut réservé par
    # `DeclarativeBase` (la collection de métadonnées SQLAlchemy elle-même), le déclarer tel quel
    # écraserait cet attribut de classe. La colonne SQL reste bien nommée `metadata` (voir
    # `mapped_column("metadata", ...)` ci-dessous et la migration 0020), conformément à la
    # spécification du modèle.
    audit_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
