import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.modules.auth.schemas import UserOut
from app.modules.organizations.schemas import OrganizationOut
from app.modules.platform.schemas import PlatformOrganizationCreate
from app.modules.schools.schemas import SchoolOut


class PartnerDashboardOut(BaseModel):
    school_count: int
    organization_count: int


class PartnerSchoolOut(BaseModel):
    """Métadonnées d'une école inscrite par CE partenaire — jamais de donnée scolaire."""

    school_id: uuid.UUID
    school_name: str
    organization_id: uuid.UUID
    organization_name: str
    enrolled_at: datetime
    status: str


class PartnerSchoolEnrollCreate(PlatformOrganizationCreate):
    """Même contenu que l'inscription plateforme (organisation, école, premier SCHOOL_ADMIN).

    `extra="forbid"` : un client ne peut jamais transmettre `partner_id`/`acquisition_source`/
    `commission_eligible` (ou tout autre champ inconnu) — rejet 422 explicite plutôt qu'un champ
    silencieusement ignoré. Le partenaire est TOUJOURS dérivé côté serveur du compte appelant."""

    model_config = ConfigDict(extra="forbid")


class PartnerSchoolEnrolled(BaseModel):
    organization: OrganizationOut
    school: SchoolOut
    admin: UserOut
    admin_role_code: str = "SCHOOL_ADMIN"
    acquisition_source: str
    commission_eligible: bool


class PartnerAccountOut(BaseModel):
    """Métadonnées de compte uniquement (jamais de donnée financière/académique)."""

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime
    role_codes: list[str]
