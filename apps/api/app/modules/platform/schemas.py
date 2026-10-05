import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, EmailStr, Field, field_validator

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
