import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.organizations.schemas import OrganizationOut
from app.modules.schools.schemas import SchoolOut


class RegisterRequest(BaseModel):
    organization_name: str = Field(min_length=2, max_length=255)
    organization_slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    country_code: str = Field(min_length=2, max_length=2)
    school_name: str = Field(min_length=2, max_length=255)
    school_slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9-]+$")
    admin_full_name: str = Field(min_length=2, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    is_platform_admin: bool
    created_at: datetime
    last_login_at: datetime | None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterResponse(BaseModel):
    organization: OrganizationOut
    school: SchoolOut
    user: UserOut
    tokens: TokenPair


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    device_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


class RoleAssignmentOut(BaseModel):
    role_code: str
    organization_id: uuid.UUID | None
    school_id: uuid.UUID | None


class MeOut(BaseModel):
    user: UserOut
    roles: list[RoleAssignmentOut]
    permissions: list[str]


class SessionOut(BaseModel):
    id: uuid.UUID
    device_id: str | None
    ip: str | None
    user_agent: str | None
    created_at: datetime
    expires_at: datetime
