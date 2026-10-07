import uuid
from datetime import date, datetime

from pydantic import BaseModel


class TeacherSchoolOut(BaseModel):
    id: uuid.UUID
    name: str


class TeacherAnnouncementOut(BaseModel):
    """Annonce reçue par CET enseignant (école entière, ou une classe où il est affecté) — jamais
    `recipient_count` ni aucune autre donnée d'historique administratif : reconstruit depuis ses
    propres `Notification`, pas depuis l'agrégat utilisé par `GET /announcements` (SCHOOL_ADMIN)."""

    id: uuid.UUID
    title: str
    body: str
    created_at: datetime
    read: bool


class TeacherMeOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    is_active: bool
    roles: list[str]
    schools: list[TeacherSchoolOut]


class TeacherSubjectOut(BaseModel):
    class_subject_id: uuid.UUID
    subject_id: uuid.UUID
    subject_name: str
    coefficient: float


class TeacherClassOut(BaseModel):
    id: uuid.UUID
    name: str
    school_id: uuid.UUID
    academic_year_id: uuid.UUID
    level_name: str | None
    student_count: int
    subjects: list[TeacherSubjectOut]


class TeacherStudentOut(BaseModel):
    id: uuid.UUID
    matricule: str
    first_name: str
    last_name: str
    status: str
    class_id: uuid.UUID
    class_name: str


class TeacherClassRefOut(BaseModel):
    class_id: uuid.UUID
    class_name: str


class TeacherStudentDetailOut(BaseModel):
    """Fiche élève en LECTURE SEULE : identité et classes du périmètre enseignant uniquement.
    Pas de coordonnées, documents, tuteurs ni informations administratives."""

    id: uuid.UUID
    matricule: str
    first_name: str
    last_name: str
    status: str
    classes: list[TeacherClassRefOut]


class TeacherAssessmentOut(BaseModel):
    id: uuid.UUID
    name: str
    class_subject_id: uuid.UUID
    subject_name: str
    academic_term_id: uuid.UUID
    max_score: float
    assessment_date: date


class TeacherAttendanceSessionOut(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    academic_term_id: uuid.UUID
    session_date: date
    locked: bool
    taken_by: uuid.UUID | None


class TeacherReportCardOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_name: str
    academic_term_id: uuid.UUID
    status: str
    published_at: datetime | None


class TeacherNotificationOut(BaseModel):
    id: uuid.UUID
    type: str
    title: str
    created_at: datetime
    read: bool


class TeacherRecentAssessmentOut(BaseModel):
    id: uuid.UUID
    name: str
    class_name: str
    subject_name: str
    assessment_date: date


class TeacherDashboardOut(BaseModel):
    teacher_name: str
    schools: list[TeacherSchoolOut]
    class_count: int
    subject_count: int
    student_count: int
    recent_assessments: list[TeacherRecentAssessmentOut]
    recent_notifications: list[TeacherNotificationOut]
