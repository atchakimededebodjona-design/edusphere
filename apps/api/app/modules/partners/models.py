import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# PR #17 (Platform Owner & Partner isolation) — voir migration 0023.
#
# Valeurs documentées (même convention que `audit_logs.action`/`student_fees.status` dans ce
# dépôt : simples `String`, pas de CHECK ni de `Literal` Pydantic côté base).
PARTNER_STATUS_ACTIVE = "ACTIVE"
PARTNER_STATUS_SUSPENDED = "SUSPENDED"

ENROLLMENT_STATUS_ACTIVE = "ACTIVE"

ACQUISITION_SOURCE_PLATFORM_OWNER = "PLATFORM_OWNER"
ACQUISITION_SOURCE_PARTNER = "PARTNER"


class Partner(Base):
    """Partenaire commercial (externe à l'entreprise) — un enregistrement par compte utilisateur.

    Pas d'`organization_id` : un partenaire n'appartient à aucun tenant. RLS : policy
    `partners_platform_only` (lecture/écriture uniquement en contexte platform-wide). Un
    PARTNER_ADMIN lisant SA propre ligne passe donc par `set_platform_wide_context` + un filtre
    explicite `user_id = <utilisateur authentifié>` (voir partners/service.py::get_own_partner).
    """

    __tablename__ = "partners"
    __table_args__ = (UniqueConstraint("user_id", name="uq_partners_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=PARTNER_STATUS_ACTIVE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class PartnerSchoolEnrollment(Base):
    """Source d'acquisition d'une école sur la plateforme — exactement une ligne par école
    (`UNIQUE(school_id)`) : une école n'est jamais inscrite deux fois, ni par deux sources.

    - `partner_id` NULL + `acquisition_source = "PLATFORM_OWNER"` + `commission_eligible = false` :
      école inscrite directement par le propriétaire de la plateforme (POST /platform/organizations).
    - `partner_id` renseigné + `acquisition_source = "PARTNER"` + `commission_eligible = true` :
      école inscrite via un partenaire (POST /partner/schools), `partner_id` toujours dérivé côté
      serveur du compte appelant, jamais fourni par le client.

    `commission_eligible` n'est qu'un drapeau : AUCUN montant de commission n'est calculé ni
    stocké dans cette PR (moteur financier différé à la PR #18).

    RLS : policy générique `{table}_tenant_isolation` (organization_id), comme toute table tenant.
    """

    __tablename__ = "partner_school_enrollments"
    __table_args__ = (UniqueConstraint("school_id", name="uq_partner_school_enrollments_school_id"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False
    )
    enrolled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=ENROLLMENT_STATUS_ACTIVE)
    acquisition_source: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    commission_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
