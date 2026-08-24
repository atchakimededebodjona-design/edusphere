import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SchoolOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    name: str
    slug: str
    address: str | None
    phone: str | None
    email: str | None
    timezone: str
    currency: str
    created_at: datetime
    updated_at: datetime


class SchoolCreate(BaseModel):
    organization_id: uuid.UUID
    name: str
    slug: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    timezone: str = "Africa/Lome"
    currency: str = "XOF"


class SchoolUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    timezone: str | None = None
    currency: str | None = None
