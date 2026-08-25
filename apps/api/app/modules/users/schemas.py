import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    created_at: datetime


class RoleAssignmentOut(BaseModel):
    role_code: str
    organization_id: uuid.UUID | None
    school_id: uuid.UUID | None


class UserWithRolesOut(BaseModel):
    user: UserOut
    roles: list[RoleAssignmentOut]


class UserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=255)
    phone: str | None = None
    school_id: uuid.UUID
    role_code: str


class UserCreateResponse(BaseModel):
    user: UserOut
    roles: list[RoleAssignmentOut]
    # Non renseigné hors environnement "production" (email non intégré) — voir
    # app/modules/auth/service.py::request_password_reset pour le même mécanisme et la même
    # justification. `None` si l'utilisateur existait déjà (son mot de passe reste inchangé).
    dev_reset_token: str | None
