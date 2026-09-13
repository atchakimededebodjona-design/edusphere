import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# Même convention que academics/students/grades : school_id + organization_id dénormalisé sur
# chaque table, réutilisant le mécanisme RLS existant (voir PHASE_6_ATTENDANCE_PLAN.md §11).


class AttendanceSession(Base):
    """Un appel pour une classe entière (pas une matière précise), à une date donnée, dans une
    période académique donnée.

    Scopée par classe et non par class_subject (décision validée, PHASE_6_ATTENDANCE_PLAN.md §8) :
    l'autorisation enseignant réutilise TeacherAssignment via n'importe quelle matière affectée
    dans la classe (voir attendance/service.py::is_teacher_assigned_to_class), sans introduire de
    notion de "professeur principal" absente du modèle academics.
    """

    __tablename__ = "attendance_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    academic_term_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("academic_terms.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_date: Mapped[date] = mapped_column(Date, nullable=False)
    taken_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AttendanceRecord(Base):
    """Présence d'un élève pour une session — statut en colonne contrainte côté schémas (pas de
    table de référence séparée), motif en texte libre : même convention que Student.status /
    AssessmentResult.is_absent / StudentStatusHistory.reason."""

    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_record"),)

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    justified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AttendanceAbsenceEmailReminder(Base):
    """Sprint 1.8 — pendant, pour les absences, de `fees/models.py::FeeOverdueEmailReminder` :
    suivi des emails envoyés aux tuteurs SANS compte utilisateur (`Guardian.user_id IS NULL`) quand
    un élève est marqué ABSENT. Table dédiée pour la même raison que pour les frais :
    `notifications.recipient_user_id` est NOT NULL, un tuteur sans compte n'a structurellement
    aucun user_id à y placer.

    Idempotence par (student_id, guardian_id, absence_date) plutôt que par `attendance_id` seul :
    un même élève peut avoir plusieurs sessions ABSENT à des dates différentes (chacune doit
    pouvoir notifier), mais jamais deux emails pour la même date même si l'enregistrement est
    corrigé/resoumis plusieurs fois (voir attendance/service.py::maybe_notify_absence). `attendance_id`
    référence directement l'AttendanceRecord à l'origine de l'envoi (traçabilité), sans participer
    à la contrainte d'unicité.

    `transport_status`/`transport_checked_at` : même convention exacte que Sprint 1.6
    (`fees/models.py::FeeOverdueEmailReminder`) — `ATTEMPTED` (défaut, avant toute tentative
    réseau), `TRANSPORT_ACCEPTED` (SMTP a accepté le message, pas une preuve de remise),
    `TRANSPORT_FAILED`. String libre, pas de contrainte CHECK, même motif que l'existant."""

    __tablename__ = "attendance_absence_email_reminders"
    __table_args__ = (
        UniqueConstraint("student_id", "guardian_id", "absence_date", name="uq_attendance_absence_email_reminder"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    school_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("schools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    guardian_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("guardians.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attendance_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("attendance_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    absence_date: Mapped[date] = mapped_column(Date, nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    transport_status: Mapped[str] = mapped_column(String(32), nullable=False, default="ATTEMPTED", server_default="ATTEMPTED")
    transport_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
