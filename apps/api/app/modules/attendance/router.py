import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission, is_teacher_only
from app.modules.academics.models import AcademicTerm, SchoolClass
from app.modules.attendance import service
from app.modules.attendance.models import AttendanceRecord, AttendanceSession
from app.modules.attendance.schemas import (
    AttendanceClassStatisticsOut,
    AttendanceClassStudentStatsEntry,
    AttendanceRecordOut,
    AttendanceRecordsBulkCreate,
    AttendanceRecordUpdate,
    AttendanceSessionCreate,
    AttendanceSessionOut,
    AttendanceSessionUpdate,
    AttendanceStudentSummaryOut,
)
from app.modules.students.models import Student
from app.modules.users.models import User

router = APIRouter()


# --- Helpers -----------------------------------------------------------------
async def _get_class_or_404(db: AsyncSession, class_id: uuid.UUID) -> SchoolClass:
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    return school_class


async def _get_academic_term_or_404(db: AsyncSession, academic_term_id: uuid.UUID) -> AcademicTerm:
    academic_term = await db.get(AcademicTerm, academic_term_id)
    if academic_term is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Academic term not found")
    return academic_term


async def _get_session_or_404(db: AsyncSession, session_id: uuid.UUID) -> AttendanceSession:
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance session not found")
    return session


async def _get_student_or_404(db: AsyncSession, student_id: uuid.UUID) -> Student:
    student = await db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


async def _ensure_can_manage_class_attendance(db: AsyncSession, current_user: User, school_class: SchoolClass) -> None:
    """attendance.manage scopé à l'école, PUIS, si l'utilisateur n'est que TEACHER pour cette
    école, vérifie qu'il a au moins une affectation (TeacherAssignment) sur une matière de cette
    classe — même règle que academics/router.py::list_classes."""
    await ensure_permission(
        db, current_user, "attendance.manage", organization_id=school_class.organization_id, school_id=school_class.school_id
    )
    if await is_teacher_only(db, current_user, school_class.organization_id, school_class.school_id):
        if not await service.is_teacher_assigned_to_class(db, current_user.id, school_class.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this class")


async def _ensure_can_write_session(
    db: AsyncSession, current_user: User, session: AttendanceSession, school_class: SchoolClass
) -> None:
    await _ensure_can_manage_class_attendance(db, current_user, school_class)
    if session.locked and await is_teacher_only(db, current_user, school_class.organization_id, school_class.school_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This session is locked")


# --- Sessions ------------------------------------------------------------------
@router.get("/attendance-sessions", response_model=list[AttendanceSessionOut])
async def list_sessions(
    db: DbSession,
    current_user: CurrentUser,
    class_id: uuid.UUID = Query(...),
    academic_term_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> list[AttendanceSession]:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "attendance.read", organization_id=school_class.organization_id, school_id=school_class.school_id
    )
    stmt = select(AttendanceSession).where(AttendanceSession.class_id == class_id)
    if academic_term_id:
        stmt = stmt.where(AttendanceSession.academic_term_id == academic_term_id)
    if date_from:
        stmt = stmt.where(AttendanceSession.session_date >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceSession.session_date <= date_to)
    result = await db.execute(stmt.order_by(AttendanceSession.session_date.desc()))
    return list(result.scalars().all())


@router.post("/attendance-sessions", response_model=AttendanceSessionOut, status_code=status.HTTP_201_CREATED)
async def create_session(payload: AttendanceSessionCreate, db: DbSession, current_user: CurrentUser) -> AttendanceSession:
    school_class = await _get_class_or_404(db, payload.class_id)
    await _ensure_can_manage_class_attendance(db, current_user, school_class)
    academic_term = await _get_academic_term_or_404(db, payload.academic_term_id)

    try:
        service.validate_session_date(school_class, academic_term, payload.session_date)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    session = AttendanceSession(
        id=uuid.uuid4(),
        school_id=school_class.school_id,
        organization_id=school_class.organization_id,
        class_id=school_class.id,
        academic_term_id=academic_term.id,
        session_date=payload.session_date,
        taken_by=current_user.id,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    await db.commit()
    return session


@router.get("/attendance-sessions/{session_id}", response_model=AttendanceSessionOut)
async def get_session(session_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> AttendanceSession:
    session = await _get_session_or_404(db, session_id)
    await ensure_permission(
        db, current_user, "attendance.read", organization_id=session.organization_id, school_id=session.school_id
    )
    return session


@router.patch("/attendance-sessions/{session_id}", response_model=AttendanceSessionOut)
async def update_session(
    session_id: uuid.UUID, payload: AttendanceSessionUpdate, db: DbSession, current_user: CurrentUser
) -> AttendanceSession:
    session = await _get_session_or_404(db, session_id)
    school_class = await _get_class_or_404(db, session.class_id)
    await _ensure_can_manage_class_attendance(db, current_user, school_class)

    if payload.locked is not None and payload.locked != session.locked:
        teacher_only = await is_teacher_only(db, current_user, school_class.organization_id, school_class.school_id)
        if teacher_only and session.locked and not payload.locked:
            # Déverrouillage réservé au niveau administratif (rôles non-TEACHER-only) — décision
            # validée, PHASE_6_ATTENDANCE_PLAN.md point 3. Pas de nouveau rôle/permission : la
            # même distinction is_teacher_only déjà utilisée pour le scoping des écritures.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Only an administrator can unlock a session"
            )
        session.locked = payload.locked
        session.locked_at = datetime.now(timezone.utc) if payload.locked else None
        session.locked_by = current_user.id if payload.locked else None

    await db.flush()
    await db.refresh(session)
    await db.commit()
    return session


# --- Records ---------------------------------------------------------------------
@router.get("/attendance-records", response_model=list[AttendanceRecordOut])
async def list_records(db: DbSession, current_user: CurrentUser, session_id: uuid.UUID = Query(...)) -> list[AttendanceRecord]:
    session = await _get_session_or_404(db, session_id)
    await ensure_permission(
        db, current_user, "attendance.read", organization_id=session.organization_id, school_id=session.school_id
    )
    result = await db.execute(select(AttendanceRecord).where(AttendanceRecord.session_id == session_id))
    return list(result.scalars().all())


@router.post("/attendance-records", response_model=list[AttendanceRecordOut], status_code=status.HTTP_201_CREATED)
async def submit_records(payload: AttendanceRecordsBulkCreate, db: DbSession, current_user: CurrentUser) -> list[AttendanceRecord]:
    session = await _get_session_or_404(db, payload.session_id)
    school_class = await _get_class_or_404(db, session.class_id)
    await _ensure_can_write_session(db, current_user, session, school_class)

    entries: list[tuple[uuid.UUID, str, bool, str | None]] = []
    for entry in payload.records:
        student = await _get_student_or_404(db, entry.student_id)
        # Vérification explicite École + Classe (pas seulement École, contrairement à `grades`) —
        # renforcement validé, PHASE_6_ATTENDANCE_PLAN.md §11.
        if student.school_id != session.school_id or not await service.student_in_class_scope(
            db, student, session.class_id
        ):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found in this class")
        entries.append((entry.student_id, entry.status, entry.justified, entry.reason))

    return await service.upsert_records(db, session, entries, recorded_by=current_user.id)


@router.patch("/attendance-records/{record_id}", response_model=AttendanceRecordOut)
async def update_record(
    record_id: uuid.UUID, payload: AttendanceRecordUpdate, db: DbSession, current_user: CurrentUser
) -> AttendanceRecord:
    record = await db.get(AttendanceRecord, record_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance record not found")

    session = await _get_session_or_404(db, record.session_id)
    school_class = await _get_class_or_404(db, session.class_id)
    await _ensure_can_write_session(db, current_user, session, school_class)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
    record.recorded_by = current_user.id

    await db.flush()
    await db.refresh(record)
    await db.commit()
    return record


# --- Statistics --------------------------------------------------------------------
@router.get("/students/{student_id}/attendance-summary", response_model=AttendanceStudentSummaryOut)
async def get_student_attendance_summary(
    student_id: uuid.UUID, db: DbSession, current_user: CurrentUser, academic_term_id: uuid.UUID = Query(...)
) -> AttendanceStudentSummaryOut:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(
        db, current_user, "attendance.read", organization_id=student.organization_id, school_id=student.school_id
    )
    summary = await service.compute_student_summary(db, student_id, academic_term_id)
    return AttendanceStudentSummaryOut(student_id=student_id, academic_term_id=academic_term_id, **summary)


@router.get("/classes/{class_id}/attendance-statistics", response_model=AttendanceClassStatisticsOut)
async def get_class_attendance_statistics(
    class_id: uuid.UUID, db: DbSession, current_user: CurrentUser, academic_term_id: uuid.UUID = Query(...)
) -> AttendanceClassStatisticsOut:
    school_class = await _get_class_or_404(db, class_id)
    await ensure_permission(
        db, current_user, "attendance.read", organization_id=school_class.organization_id, school_id=school_class.school_id
    )
    entries = await service.compute_class_statistics(db, class_id, academic_term_id)
    return AttendanceClassStatisticsOut(
        class_id=class_id,
        academic_term_id=academic_term_id,
        students=[AttendanceClassStudentStatsEntry(**entry) for entry in entries],
    )
