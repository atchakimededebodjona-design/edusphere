import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReportCardStatus = Literal["DRAFT", "PUBLISHED"]


class ReportCardTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    html_content: str
    is_default: bool
    created_at: datetime
    updated_at: datetime


class ReportCardTemplateCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=128)
    html_content: str = Field(min_length=1)
    is_default: bool = False


class ReportCardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    class_id: uuid.UUID
    academic_term_id: uuid.UUID
    template_id: uuid.UUID
    status: ReportCardStatus
    verification_code: str
    general_average: float | None
    general_rank: int | None
    generated_at: datetime
    published_at: datetime | None


class ReportCardGenerateRequest(BaseModel):
    class_id: uuid.UUID
    academic_term_id: uuid.UUID
    template_id: uuid.UUID


class ReportCardVerifyOut(BaseModel):
    school_name: str
    student_full_name: str
    class_name: str
    academic_term_name: str
    general_average: float | None
    general_rank: int | None
    status: ReportCardStatus
    generated_at: datetime
