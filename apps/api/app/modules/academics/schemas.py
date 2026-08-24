import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


# --- Academic years ---------------------------------------------------------
class AcademicYearOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    is_current: bool
    created_at: datetime
    updated_at: datetime


class AcademicYearCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=64)
    start_date: date
    end_date: date
    is_current: bool = False


class AcademicYearUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    is_current: bool | None = None


# --- Academic terms ----------------------------------------------------------
class AcademicTermOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    academic_year_id: uuid.UUID
    school_id: uuid.UUID
    name: str
    start_date: date
    end_date: date
    order_index: int
    created_at: datetime
    updated_at: datetime


class AcademicTermCreate(BaseModel):
    academic_year_id: uuid.UUID
    name: str = Field(min_length=1, max_length=64)
    start_date: date
    end_date: date
    order_index: int = 0


class AcademicTermUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    order_index: int | None = None


# --- Education levels ---------------------------------------------------------
class EducationLevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    order_index: int
    created_at: datetime
    updated_at: datetime


class EducationLevelCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=64)
    order_index: int = 0


class EducationLevelUpdate(BaseModel):
    name: str | None = None
    order_index: int | None = None


# --- Subjects ------------------------------------------------------------------
class SubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    code: str | None
    created_at: datetime
    updated_at: datetime


class SubjectCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=128)
    code: str | None = None


class SubjectUpdate(BaseModel):
    name: str | None = None
    code: str | None = None


# --- Rooms -----------------------------------------------------------------
class RoomOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    capacity: int | None
    created_at: datetime
    updated_at: datetime


class RoomCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=64)
    capacity: int | None = None


class RoomUpdate(BaseModel):
    name: str | None = None
    capacity: int | None = None


# --- Classes -----------------------------------------------------------------
class SchoolClassOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    academic_year_id: uuid.UUID
    education_level_id: uuid.UUID
    name: str
    capacity: int | None
    created_at: datetime
    updated_at: datetime


class SchoolClassCreate(BaseModel):
    academic_year_id: uuid.UUID
    education_level_id: uuid.UUID
    name: str = Field(min_length=1, max_length=64)
    capacity: int | None = None


class SchoolClassUpdate(BaseModel):
    name: str | None = None
    capacity: int | None = None


# --- Class <-> Subject --------------------------------------------------------
class ClassSubjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    subject_id: uuid.UUID
    coefficient: float
    created_at: datetime


class ClassSubjectCreate(BaseModel):
    subject_id: uuid.UUID
    coefficient: float = 1


# --- Teacher assignments -------------------------------------------------------
class TeacherAssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    class_subject_id: uuid.UUID
    created_at: datetime


class TeacherAssignmentCreate(BaseModel):
    user_id: uuid.UUID
    subject_id: uuid.UUID
