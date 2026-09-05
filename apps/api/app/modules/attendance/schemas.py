import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AttendanceStatusValue = Literal["PRESENT", "ABSENT", "LATE"]


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


class AttendanceRecordUpdate(BaseModel):
    status: AttendanceStatusValue | None = None
    justified: bool | None = None
    reason: str | None = None


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
