import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Sex = Literal["M", "F"]
StudentStatus = Literal["ACTIVE", "INACTIVE", "GRADUATED", "WITHDRAWN", "TRANSFERRED"]
EnrollmentStatus = Literal["ACTIVE", "WITHDRAWN", "TRANSFERRED", "COMPLETED"]
GuardianRelationship = Literal["father", "mother", "guardian", "other"]


# --- Students ------------------------------------------------------------------
class StudentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    matricule: str
    first_name: str
    last_name: str
    date_of_birth: date
    sex: Sex
    place_of_birth: str | None
    address: str | None
    status: StudentStatus
    photo_path: str | None
    created_at: datetime
    updated_at: datetime


class StudentCreate(BaseModel):
    school_id: uuid.UUID
    matricule: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=128)
    last_name: str = Field(min_length=1, max_length=128)
    date_of_birth: date
    sex: Sex
    place_of_birth: str | None = None
    address: str | None = None


class StudentUpdate(BaseModel):
    matricule: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    sex: Sex | None = None
    place_of_birth: str | None = None
    address: str | None = None
    status: StudentStatus | None = None
    status_change_reason: str | None = None


# --- Guardians -----------------------------------------------------------------
class GuardianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    full_name: str
    relationship_type: GuardianRelationship
    phone: str | None
    email: str | None
    address: str | None
    is_emergency_contact: bool
    created_at: datetime
    updated_at: datetime


class GuardianCreate(BaseModel):
    school_id: uuid.UUID
    full_name: str = Field(min_length=1, max_length=255)
    relationship_type: GuardianRelationship
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_emergency_contact: bool = False


class GuardianUpdate(BaseModel):
    full_name: str | None = None
    relationship_type: GuardianRelationship | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    is_emergency_contact: bool | None = None


class StudentGuardianOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    guardian_id: uuid.UUID
    is_primary_contact: bool
    created_at: datetime


class StudentGuardianCreate(BaseModel):
    guardian_id: uuid.UUID
    is_primary_contact: bool = False


# --- Enrollments ---------------------------------------------------------------
class StudentEnrollmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    class_id: uuid.UUID
    academic_year_id: uuid.UUID
    enrollment_date: date
    status: EnrollmentStatus
    created_at: datetime
    updated_at: datetime


class StudentEnrollmentCreate(BaseModel):
    class_id: uuid.UUID
    enrollment_date: date


class StudentEnrollmentUpdate(BaseModel):
    status: EnrollmentStatus


# --- Documents -------------------------------------------------------------------
class StudentDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    document_type: str
    file_path: str
    original_filename: str
    uploaded_by: uuid.UUID | None
    created_at: datetime


# --- Import CSV/Excel -------------------------------------------------------------
class StudentImportRowError(BaseModel):
    row: int
    reason: str


class StudentImportReport(BaseModel):
    total_rows: int
    created: int
    duplicates_skipped: int
    errors: list[StudentImportRowError]
