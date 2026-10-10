import re
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.modules.auth.schemas import UserOut
from app.modules.organizations.schemas import OrganizationOut
from app.modules.schools.schemas import SchoolOut

SLUG_PATTERN = r"^[a-z0-9-]+$"
CURRENCY_PATTERN = r"^[A-Z]{3}$"
DEFAULT_TIMEZONE = "Africa/Lome"
DEFAULT_CURRENCY = "XOF"


def _validate_timezone(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z_]+(?:/[A-Za-z0-9_+-]+)+", value):
        raise ValueError("timezone must be an IANA name such as Africa/Lome")
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("timezone must be an IANA name such as Africa/Lome") from exc
    return value


class PlatformDashboardOut(BaseModel):
    organization_count: int
    school_count: int
    user_count: int
    student_count: int
    # PR #17
    partner_count: int
    enrollment_count: int


class PlatformOrganizationInput(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=SLUG_PATTERN)
    country_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Za-z]{2}$")
    timezone: str = Field(default=DEFAULT_TIMEZONE, max_length=64)
    currency: str = Field(default=DEFAULT_CURRENCY, pattern=CURRENCY_PATTERN)

    @field_validator("country_code")
    @classmethod
    def _upper_country_code(cls, value: str) -> str:
        return value.upper()

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        return _validate_timezone(value)


class PlatformSchoolInput(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=SLUG_PATTERN)
    address: str | None = Field(default=None, max_length=500)
    phone: str | None = Field(default=None, max_length=32)
    email: EmailStr | None = None
    timezone: str = Field(default=DEFAULT_TIMEZONE, max_length=64)
    currency: str = Field(default=DEFAULT_CURRENCY, pattern=CURRENCY_PATTERN)

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        return _validate_timezone(value)


class PlatformAdminInput(BaseModel):
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    password: str = Field(min_length=8, max_length=128)


class PlatformOrganizationCreate(BaseModel):
    """Création d'une organisation par un platform admin : organisation, école principale et
    premier SCHOOL_ADMIN, dans une seule transaction (voir platform/service.py)."""

    organization: PlatformOrganizationInput
    school: PlatformSchoolInput
    admin: PlatformAdminInput


class PlatformOrganizationCreated(BaseModel):
    """Réponse de création : jamais de mot de passe ni de token. Le School Admin créé n'est pas
    connecté dans la session du platform admin."""

    organization: OrganizationOut
    school: SchoolOut
    admin: UserOut
    admin_role_code: str = "SCHOOL_ADMIN"


# --- PR #17 — lectures plateforme (métadonnées uniquement, jamais de donnée scolaire) ----------


class PlatformOrganizationListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    country_code: str
    created_at: datetime


class PlatformSchoolListItem(BaseModel):
    id: uuid.UUID
    name: str
    organization_id: uuid.UUID
    slug: str
    created_at: datetime
    # "PLATFORM_OWNER" | "PARTNER", ou None pour une école antérieure à la PR #17 (aucune ligne
    # partner_school_enrollments rétroactive n'est créée par la migration 0023).
    acquisition_source: str | None
    # Agrégats uniquement (COUNT), jamais de donnée individuelle d'élève — voir
    # platform/service.py::student_counts_by_school. `active_student_count` = élèves au statut
    # ACTIVE (même définition que le tableau de bord école) ; base envisagée pour la tarification
    # SaaS de la PR #18, AUCUNE logique de tarification ici.
    student_count: int
    active_student_count: int


class PlatformAccountOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
    role_codes: list[str]


class PlatformPartnerOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    display_name: str
    phone: str | None
    email: str | None
    status: str
    created_at: datetime
    enrollment_count: int


class PlatformPartnerCreate(BaseModel):
    """Création d'un compte partenaire. Aucun mot de passe : le partenaire reçoit un lien
    d'activation (même motif que users/schemas.py::UserCreateRequest)."""

    display_name: str = Field(min_length=2, max_length=255)
    full_name: str = Field(min_length=2, max_length=255)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)


class PlatformPartnerCreated(BaseModel):
    partner: PlatformPartnerOut
    # Même règle que users/schemas.py::UserCreateResponse.dev_reset_token (jamais en production).
    dev_reset_token: str | None


# Enveloppes paginées (même forme que fees/schemas.py::OverdueFeesOut).
class _PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int


class PlatformOrganizationsPage(_PageMeta):
    items: list[PlatformOrganizationListItem]


class PlatformSchoolsPage(_PageMeta):
    items: list[PlatformSchoolListItem]


class PlatformAccountsPage(_PageMeta):
    items: list[PlatformAccountOut]


class PlatformPartnersPage(_PageMeta):
    items: list[PlatformPartnerOut]


# --- PR #19 — plusieurs établissements par organisation --------------------------------------


class PlatformSchoolAdd(BaseModel):
    """Ajout d'un établissement à une organisation EXISTANTE (désignée par le chemin de l'URL,
    jamais par le corps) : nouvelle école + son premier SCHOOL_ADMIN.

    `extra="forbid"` : tout champ inconnu (organization/organization_id/partner_id/school_id/
    acquisition_source/commission_eligible...) est rejeté en 422 — ce parcours ne crée ni ne
    redésigne jamais d'organisation, et la source d'acquisition est toujours décidée côté serveur."""

    model_config = ConfigDict(extra="forbid")

    school: PlatformSchoolInput
    admin: PlatformAdminInput


class PlatformSchoolAdded(BaseModel):
    organization: OrganizationOut
    school: SchoolOut
    admin: UserOut
    admin_role_code: str = "SCHOOL_ADMIN"
    acquisition_source: str
    commission_eligible: bool


class PlatformOrganizationSchoolsOut(BaseModel):
    """Une organisation et ses établissements (métadonnées + agrégats élèves uniquement)."""

    organization: PlatformOrganizationListItem
    schools: list[PlatformSchoolListItem]
