import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Assessment types --------------------------------------------------------
class AssessmentTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class AssessmentTypeCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=64)


# --- Assessments ---------------------------------------------------------------
class AssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_subject_id: uuid.UUID
    academic_term_id: uuid.UUID
    assessment_type_id: uuid.UUID
    name: str
    max_score: float
    weight: float
    assessment_date: date
    created_at: datetime
    updated_at: datetime


class AssessmentCreate(BaseModel):
    class_subject_id: uuid.UUID
    academic_term_id: uuid.UUID
    assessment_type_id: uuid.UUID
    name: str = Field(min_length=1, max_length=128)
    max_score: float = Field(default=20, gt=0)
    weight: float = Field(default=1, gt=0)
    assessment_date: date


# --- Results ---------------------------------------------------------------------
class AssessmentResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    student_id: uuid.UUID
    score: float | None
    is_absent: bool
    created_at: datetime
    updated_at: datetime


class AssessmentResultEntry(BaseModel):
    student_id: uuid.UUID
    score: float | None = None
    is_absent: bool = False


class AssessmentResultsBulkCreate(BaseModel):
    assessment_id: uuid.UUID
    results: list[AssessmentResultEntry] = Field(min_length=1)


class AssessmentResultUpdate(BaseModel):
    score: float | None = None
    is_absent: bool | None = None


# --- Averages --------------------------------------------------------------------
class StudentSubjectAverageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    class_subject_id: uuid.UUID
    academic_term_id: uuid.UUID
    average: float | None
    rank: int | None
    appreciation: str | None
    updated_at: datetime


class StudentSubjectAverageUpdate(BaseModel):
    appreciation: str = Field(max_length=500)


class StudentTermAverageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    academic_term_id: uuid.UUID
    average: float | None
    rank: int | None
    updated_at: datetime


class StudentAveragesOut(BaseModel):
    subject_averages: list[StudentSubjectAverageOut]
    term_averages: list[StudentTermAverageOut]


class ClassPerformanceEntry(BaseModel):
    student_id: uuid.UUID
    average: float | None
    rank: int | None


class ClassPerformanceOut(BaseModel):
    academic_term_id: uuid.UUID
    class_id: uuid.UUID
    students: list[ClassPerformanceEntry]
