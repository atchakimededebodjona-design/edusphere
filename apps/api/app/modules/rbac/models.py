import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Rôles définis par le cahier des charges (§6). Catalogue fixe pour la Phase 1.
#
# PR #17 — `PLATFORM_ROLE_CODES` est la SEULE source de vérité de « rôle opérateur plateforme de
# confiance » : c'est ce code de rôle (jamais la simple nullité de `user_roles.organization_id`)
# qui fait basculer `app.is_platform_wide = 'true'` dans `core/tenancy.py::apply_tenant_context`
# (bypass RLS de toutes les tables tenant). PARTNER_ADMIN n'en fait volontairement PAS partie :
# un partenaire commercial est externe à l'entreprise et ne doit jamais obtenir de visibilité RLS
# implicite sur une organisation/école (voir docstring de UserRole ci-dessous).
PLATFORM_ROLE_CODES = {"SUPER_ADMIN", "PLATFORM_SUPPORT", "PLATFORM_OWNER"}
# Rôles non scolaires (jamais attribuables via les endpoints scopés école de users/service.py) :
# les rôles plateforme ci-dessus + PARTNER_ADMIN.
NON_SCHOOL_ROLE_CODES = PLATFORM_ROLE_CODES | {"PARTNER_ADMIN"}
# Rôles globaux ISOLÉS (PR #17) : un compte qui en détient un ne reçoit JAMAIS de rôle scolaire
# (ni à la création, ni par rattachement d'un email existant — users/service.py), et l'outil
# opérateur de promotion refuse un compte déjà rattaché à une école (platform/owner.py). Les rôles
# hérités SUPER_ADMIN/PLATFORM_SUPPORT n'y figurent pas : comportement historique inchangé.
ISOLATED_GLOBAL_ROLE_CODES = {"PLATFORM_OWNER", "PARTNER_ADMIN"}
ALL_ROLE_CODES = [
    "SUPER_ADMIN",
    "PLATFORM_SUPPORT",
    "PLATFORM_OWNER",
    "PARTNER_ADMIN",
    "SCHOOL_ADMIN",
    "DIRECTOR",
    "ACCOUNTANT",
    "TEACHER",
    "STAFF",
    "PARENT",
    "STUDENT",
]


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_system_role: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class UserRole(Base):
    """Attribution d'un rôle à un utilisateur, scopée organisation et/ou école.

    organization_id = NULL et school_id = NULL : rôle non rattaché à un tenant. Deux familles :
    - rôles plateforme (SUPER_ADMIN, PLATFORM_SUPPORT, PLATFORM_OWNER — voir PLATFORM_ROLE_CODES) :
      seuls ces trois codes rendent la session RLS « platform-wide » (`app.is_platform_wide`) ;
    - PARTNER_ADMIN (PR #17) : également global (un partenaire n'appartient à aucun tenant), mais
      délibérément PAS platform-wide — son contexte RLS reste `is_platform_wide = false` avec
      `tenant_org_ids` vide, donc zéro ligne visible par défaut sur toute table tenant. Ses
      lectures passent exclusivement par les endpoints `/partner/*`, filtrés explicitement par
      son propre `partners.id` (voir modules/partners/service.py).
    Le calcul RLS se fait sur le CODE du rôle, jamais sur la seule nullité d'organization_id (voir
    core/tenancy.py::apply_tenant_context). Un rôle scopé à une école porte toujours aussi
    l'organization_id de cette école (dénormalisé), pour simplifier le calcul du contexte RLS.
    """

    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    school_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
