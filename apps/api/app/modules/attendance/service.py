import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.models import AcademicTerm, ClassSubject, SchoolClass, TeacherAssignment
from app.modules.attendance.models import AttendanceRecord, AttendanceSession
from app.modules.students.models import Student, StudentEnrollment


async def is_teacher_assigned_to_class(db: AsyncSession, user_id: uuid.UUID, class_id: uuid.UUID) -> bool:
    """Un enseignant peut faire l'appel d'une classe s'il a au moins une TeacherAssignment sur une
    matière de cette classe — même règle que academics/router.py::list_classes, sans introduire de
    notion de professeur principal (décision validée, PHASE_6_ATTENDANCE_PLAN.md §6)."""
    result = await db.execute(
        select(TeacherAssignment.id)
        .join(ClassSubject, ClassSubject.id == TeacherAssignment.class_subject_id)
        .where(ClassSubject.class_id == class_id, TeacherAssignment.user_id == user_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


def validate_session_date(school_class: SchoolClass, academic_term: AcademicTerm, session_date: date) -> None:
    """Cohérence classe <-> période, puis appartenance de la date à la période — les dates futures
    sont explicitement autorisées tant que la date reste dans la période académique (décision
    validée, PHASE_6_ATTENDANCE_PLAN.md §9, §23)."""
    if academic_term.academic_year_id != school_class.academic_year_id:
        raise ValueError("Academic term does not belong to the class's academic year")
    if not (academic_term.start_date <= session_date <= academic_term.end_date):
        raise ValueError("Session date is outside the academic term period")


async def student_in_class_scope(db: AsyncSession, student: Student, class_id: uuid.UUID) -> bool:
    """Vérifie qu'un élève est activement inscrit dans la classe de la session — École ET Classe,
    pas seulement l'école (renforcement validé vs. ce que fait `grades` aujourd'hui)."""
    result = await db.execute(
        select(StudentEnrollment.id).where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.class_id == class_id,
            StudentEnrollment.status == "ACTIVE",
        )
    )
    return result.scalar_one_or_none() is not None


async def upsert_records(
    db: AsyncSession,
    session: AttendanceSession,
    entries: list[tuple[uuid.UUID, str, bool, str | None]],
    recorded_by: uuid.UUID | None,
) -> list[AttendanceRecord]:
    """Upsert idempotent par (session_id, student_id) : une resoumission identique laisse le même
    état final, sans erreur ni duplication — propriété requise pour un futur mode offline (décision
    validée, PHASE_6_ATTENDANCE_PLAN.md §9)."""
    saved: list[AttendanceRecord] = []
    for student_id, status, justified, reason in entries:
        result = await db.execute(
            select(AttendanceRecord).where(
                AttendanceRecord.session_id == session.id, AttendanceRecord.student_id == student_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AttendanceRecord(
                id=uuid.uuid4(),
                school_id=session.school_id,
                organization_id=session.organization_id,
                session_id=session.id,
                student_id=student_id,
            )
            db.add(row)
        row.status = status
        row.justified = justified
        row.reason = reason
        row.recorded_by = recorded_by
        saved.append(row)

    await db.flush()
    # refresh() AVANT commit : ces tables ont RLS activée, leurs lignes ne sont visibles que le
    # temps de la transaction courante (même piège documenté dans grades/service.py).
    for row in saved:
        await db.refresh(row)
    await db.commit()
    return saved


def _summarize(rows: list[tuple[str, bool]]) -> dict:
    """(présents + retards) / total × 100 — un retard compte comme une présence pour le taux
    (décision validée, PHASE_6_ATTENDANCE_PLAN.md §16/§23)."""
    total = len(rows)
    present = sum(1 for status, _ in rows if status == "PRESENT")
    absent = sum(1 for status, _ in rows if status == "ABSENT")
    late = sum(1 for status, _ in rows if status == "LATE")
    justified_absences = sum(1 for status, justified in rows if status == "ABSENT" and justified)
    rate = round((present + late) / total * 100, 2) if total > 0 else None
    return {
        "total_sessions": total,
        "present_count": present,
        "absent_count": absent,
        "late_count": late,
        "justified_absence_count": justified_absences,
        "attendance_rate": rate,
    }


async def compute_student_summary(
    db: AsyncSession, student_id: uuid.UUID, academic_term_id: uuid.UUID | None = None
) -> dict:
    """`academic_term_id=None` agrège toutes les sessions de l'élève, toutes périodes confondues
    — élargissement rétrocompatible (Phase 7) pour le module `parent`, qui n'impose pas de
    sélecteur de période sur mobile ; le endpoint existant (`attendance/router.py`) continue de
    toujours fournir un `academic_term_id` concret, comportement inchangé."""
    stmt = select(AttendanceRecord.status, AttendanceRecord.justified).join(
        AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id
    ).where(AttendanceRecord.student_id == student_id)
    if academic_term_id is not None:
        stmt = stmt.where(AttendanceSession.academic_term_id == academic_term_id)
    result = await db.execute(stmt)
    return _summarize([(status, justified) for status, justified in result.all()])


async def compute_school_summary(db: AsyncSession, school_id: uuid.UUID, academic_term_id: uuid.UUID) -> dict:
    """Même formule que `compute_student_summary`/`compute_class_statistics` (Phase 6), agrégée
    à l'échelle de l'école pour une période — utilisé par le tableau de bord admin (Phase 10),
    aucune nouvelle règle métier."""
    result = await db.execute(
        select(AttendanceRecord.status, AttendanceRecord.justified)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(AttendanceRecord.school_id == school_id, AttendanceSession.academic_term_id == academic_term_id)
    )
    return _summarize([(status, justified) for status, justified in result.all()])


async def compute_class_statistics(db: AsyncSession, class_id: uuid.UUID, academic_term_id: uuid.UUID) -> list[dict]:
    result = await db.execute(
        select(AttendanceRecord.student_id, AttendanceRecord.status, AttendanceRecord.justified)
        .join(AttendanceSession, AttendanceSession.id == AttendanceRecord.session_id)
        .where(AttendanceSession.class_id == class_id, AttendanceSession.academic_term_id == academic_term_id)
    )
    by_student: dict[uuid.UUID, list[tuple[str, bool]]] = {}
    for student_id, status, justified in result.all():
        by_student.setdefault(student_id, []).append((status, justified))

    return [{"student_id": student_id, **_summarize(entries)} for student_id, entries in by_student.items()]
