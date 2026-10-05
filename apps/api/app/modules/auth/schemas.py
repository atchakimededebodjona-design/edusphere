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
    is_platform_admin: bool
    created_at: datetime
    last_login_at: datetime | None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


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
