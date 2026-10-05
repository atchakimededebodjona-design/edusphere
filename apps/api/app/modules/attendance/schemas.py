import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

AttendanceStatusValue = Literal["PRESENT", "ABSENT", "LATE"]


def _refuse_explicit_null(data: object, field_names: tuple[str, ...]) -> object:
    """PATCH : un champ présent mais à `null` est refusé (422) ; un champ absent reste inchangé.
    Évite d'écrire NULL dans une colonne NOT NULL, ou d'ignorer silencieusement la demande."""
    if isinstance(data, dict):
        for field_name in field_names:
            if field_name in data and data[field_name] is None:
                raise ValueError(f"{field_name} cannot be null; omit the field to leave it unchanged")
    return data


# --- Sessions ------------------------------------------------------------------
class AttendanceSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    class_id: uuid.UUID
    academic_term_id: uuid.UUID
    session_date: date
    taken_by: uuid.UUID | None
    locked: bool
    locked_at: datetime | None
    locked_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class AttendanceSessionCreate(BaseModel):
    class_id: uuid.UUID
    academic_term_id: uuid.UUID
    session_date: date


class AttendanceSessionUpdate(BaseModel):
    locked: bool | None = None

    @model_validator(mode="before")
    @classmethod
    def _refuse_explicit_null(cls, data: object) -> object:
        return _refuse_explicit_null(data, ("locked",))


# --- Records ---------------------------------------------------------------------
class AttendanceRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    student_id: uuid.UUID
    status: AttendanceStatusValue
    justified: bool
    reason: str | None
    created_at: datetime
    updated_at: datetime


class AttendanceRecordEntry(BaseModel):
    student_id: uuid.UUID
    status: AttendanceStatusValue
    justified: bool = False
    reason: str | None = None


class AttendanceRecordsBulkCreate(BaseModel):
    session_id: uuid.UUID
    records: list[AttendanceRecordEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _each_student_once(self) -> "AttendanceRecordsBulkCreate":
        student_ids = [entry.student_id for entry in self.records]
        if len(student_ids) != len(set(student_ids)):
            raise ValueError("Each student may appear only once per submission")
        return self


class AttendanceRecordUpdate(BaseModel):
    """Champ omis = inchangé. `status` et `justified` (NOT NULL en base) refusent `null` (422) ;
    `reason` est nullable et accepte `null` pour effacer le motif."""

    status: AttendanceStatusValue | None = None
    justified: bool | None = None
    reason: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _refuse_explicit_null(cls, data: object) -> object:
        return _refuse_explicit_null(data, ("status", "justified"))


# --- Statistics ------------------------------------------------------------------
class AttendanceStudentSummaryOut(BaseModel):
    student_id: uuid.UUID
    academic_term_id: uuid.UUID
    total_sessions: int
    present_count: int
    absent_count: int
    late_count: int
    justified_absence_count: int
    attendance_rate: float | None


class AttendanceClassStudentStatsEntry(BaseModel):
    student_id: uuid.UUID
    total_sessions: int
    present_count: int
    absent_count: int
    late_count: int
    justified_absence_count: int
    attendance_rate: float | None


class AttendanceClassStatisticsOut(BaseModel):
    class_id: uuid.UUID
    academic_term_id: uuid.UUID
    students: list[AttendanceClassStudentStatsEntry]
