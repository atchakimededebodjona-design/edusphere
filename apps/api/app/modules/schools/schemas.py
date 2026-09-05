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
    logo_path: str | None
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


class SchoolDashboardOut(BaseModel):
    """Tableau de bord admin (Phase 10) — strictement les 4 métriques approuvées, voir
    app/modules/schools/service.py::get_dashboard_summary pour les définitions exactes."""

    active_student_count: int
    attendance_rate: float | None
    grade_completeness_rate: float | None
    published_report_card_count: int
    current_term_id: uuid.UUID | None
    current_term_name: str | None
