import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession
from app.core.storage import storage
from app.modules.academics.models import ClassSubject, SchoolClass, Subject
from app.modules.attendance.models import AttendanceSession
from app.modules.grades.models import Assessment
from app.modules.notifications.models import Notification
from app.modules.report_cards.models import ReportCard
from app.modules.students.models import Student, StudentEnrollment
from app.modules.teacher import service
from app.modules.teacher.schemas import (
    TeacherAnnouncementOut,
    TeacherAssessmentOut,
    TeacherAttendanceSessionOut,
    TeacherClassOut,
    TeacherClassRefOut,
    TeacherDashboardOut,
    TeacherMeOut,
    TeacherNotificationOut,
    TeacherRecentAssessmentOut,
    TeacherReportCardOut,
    TeacherSchoolOut,
    TeacherStudentDetailOut,
    TeacherStudentOut,
    TeacherSubjectOut,
)

router = APIRouter(prefix="/teacher", tags=["teacher"])


async def _enrolled_students(
    db: AsyncSession,
    class_ids: set[uuid.UUID],
    class_id: uuid.UUID | None = None,
    search: str | None = None,
) -> list[tuple[Student, uuid.UUID, str]]:
    """Élèves ACTIFS inscrits dans les classes du périmètre — jamais une liste d'école entière."""
    if not class_ids:
        return []
    stmt = (
        select(Student, SchoolClass.id, SchoolClass.name)
        .join(StudentEnrollment, StudentEnrollment.student_id == Student.id)
        .join(SchoolClass, SchoolClass.id == StudentEnrollment.class_id)
        .where(StudentEnrollment.status == "ACTIVE", StudentEnrollment.class_id.in_(class_ids))
    )
    if class_id is not None:
        stmt = stmt.where(StudentEnrollment.class_id == class_id)
    if search:
        pattern = f"%{search.lower()}%"
        stmt = stmt.where(
            func.lower(Student.first_name).like(pattern)
            | func.lower(Student.last_name).like(pattern)
            | func.lower(Student.matricule).like(pattern)
        )
    result = await db.execute(stmt.order_by(Student.last_name, Student.first_name))
    return [(s, cid, cname) for s, cid, cname in result.all()]


async def _schools_out(db: AsyncSession, school_ids: set[uuid.UUID]) -> list[TeacherSchoolOut]:
    return [TeacherSchoolOut(id=sid, name=await service.school_name(db, sid)) for sid in sorted(school_ids, key=str)]


@router.get("/announcements", response_model=list[TeacherAnnouncementOut])
async def list_my_announcements(
    db: DbSession, current_user: CurrentUser, limit: int = Query(50, ge=1, le=200)
) -> list[TeacherAnnouncementOut]:
    """Annonces reçues par CET enseignant : école entière, ou une classe où il a une
    TeacherAssignment (voir notifications/service.py::resolve_class_teacher_user_ids). Construit à
    partir de ses propres `Notification` (recipient_user_id = lui), jamais d'une liste d'école :
    aucune autre école, aucune classe non affectée, aucun `recipient_count` administratif."""
    await service.ensure_teacher(db, current_user)
    rows = await db.execute(
        select(Notification)
        .where(Notification.recipient_user_id == current_user.id, Notification.type == "ANNOUNCEMENT")
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    return [
        TeacherAnnouncementOut(id=n.id, title=n.title, body=n.body, created_at=n.created_at, read=n.read_at is not None)
        for n in rows.scalars().all()
    ]


@router.get("/me", response_model=TeacherMeOut)
async def teacher_me(db: DbSession, current_user: CurrentUser) -> TeacherMeOut:
    scope = await service.ensure_teacher(db, current_user)
    return TeacherMeOut(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        phone=current_user.phone,
        is_active=current_user.is_active,
        roles=["TEACHER"],
        schools=await _schools_out(db, scope.school_ids),
    )


@router.get("/dashboard", response_model=TeacherDashboardOut)
async def teacher_dashboard(db: DbSession, current_user: CurrentUser) -> TeacherDashboardOut:
    scope = await service.ensure_teacher(db, current_user)
    students = await _enrolled_students(db, scope.class_ids)

    recent: list[TeacherRecentAssessmentOut] = []
    if scope.class_subject_to_class:
        rows = await db.execute(
            select(Assessment, SchoolClass.name, Subject.name)
            .join(ClassSubject, ClassSubject.id == Assessment.class_subject_id)
            .join(SchoolClass, SchoolClass.id == ClassSubject.class_id)
            .join(Subject, Subject.id == ClassSubject.subject_id)
            .where(Assessment.class_subject_id.in_(list(scope.class_subject_to_class)))
            .order_by(Assessment.assessment_date.desc())
            .limit(5)
        )
        recent = [
            TeacherRecentAssessmentOut(id=a.id, name=a.name, class_name=c, subject_name=s, assessment_date=a.assessment_date)
            for a, c, s in rows.all()
        ]

    notif_rows = await db.execute(
        select(Notification)
        .where(Notification.recipient_user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(5)
    )
    notifications = [
        TeacherNotificationOut(id=n.id, type=n.type, title=n.title, created_at=n.created_at, read=n.read_at is not None)
        for n in notif_rows.scalars().all()
    ]
    return TeacherDashboardOut(
        teacher_name=current_user.full_name,
        schools=await _schools_out(db, scope.school_ids),
        class_count=len(scope.class_ids),
        subject_count=len(scope.class_subject_to_class),
        student_count=len({s.id for s, _, _ in students}),
        recent_assessments=recent,
        recent_notifications=notifications,
    )


@router.get("/classes", response_model=list[TeacherClassOut])
async def list_my_classes(db: DbSession, current_user: CurrentUser) -> list[TeacherClassOut]:
    scope = await service.ensure_teacher(db, current_user)
    if not scope.class_ids:
        return []
    classes = (
        await db.execute(select(SchoolClass).where(SchoolClass.id.in_(scope.class_ids)).order_by(SchoolClass.name))
    ).scalars().all()
    counts: dict[uuid.UUID, int] = {}
    for _, class_id, _ in await _enrolled_students(db, scope.class_ids):
        counts[class_id] = counts.get(class_id, 0) + 1

    out: list[TeacherClassOut] = []
    for school_class in classes:
        subjects = [
            TeacherSubjectOut(
                class_subject_id=cs.id, subject_id=sub.id, subject_name=sub.name, coefficient=float(cs.coefficient)
            )
            for cs, sub in await service.class_subjects_for_scope(db, scope, school_class.id)
        ]
        out.append(
            TeacherClassOut(
                id=school_class.id,
                name=school_class.name,
                school_id=school_class.school_id,
                academic_year_id=school_class.academic_year_id,
                level_name=await service.level_name(db, school_class),
                student_count=counts.get(school_class.id, 0),
                subjects=subjects,
            )
        )
    return out


@router.get("/classes/{class_id}", response_model=TeacherClassOut)
async def get_my_class(class_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> TeacherClassOut:
    school_class = await service.ensure_class_access(db, current_user, class_id)
    scope = await service.teacher_scope(db, current_user)
    students = await _enrolled_students(db, {class_id})
    subjects = [
        TeacherSubjectOut(class_subject_id=cs.id, subject_id=sub.id, subject_name=sub.name, coefficient=float(cs.coefficient))
        for cs, sub in await service.class_subjects_for_scope(db, scope, class_id)
    ]
    return TeacherClassOut(
        id=school_class.id,
        name=school_class.name,
        school_id=school_class.school_id,
        academic_year_id=school_class.academic_year_id,
        level_name=await service.level_name(db, school_class),
        student_count=len(students),
        subjects=subjects,
    )


@router.get("/classes/{class_id}/students", response_model=list[TeacherStudentOut])
async def list_class_students(
    class_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    search: str | None = Query(None, max_length=100),
) -> list[TeacherStudentOut]:
    await service.ensure_class_access(db, current_user, class_id)
    rows = await _enrolled_students(db, {class_id}, class_id=class_id, search=search)
    return [
        TeacherStudentOut(
            id=s.id, matricule=s.matricule, first_name=s.first_name, last_name=s.last_name,
            status=s.status, class_id=cid, class_name=cname,
        )
        for s, cid, cname in rows
    ]


@router.get("/students", response_model=list[TeacherStudentOut])
async def list_my_students(
    db: DbSession,
    current_user: CurrentUser,
    class_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None, max_length=100),
) -> list[TeacherStudentOut]:
    scope = await service.ensure_teacher(db, current_user)
    if class_id is not None and class_id not in scope.class_ids:
        return []
    rows = await _enrolled_students(db, scope.class_ids, class_id=class_id, search=search)
    return [
        TeacherStudentOut(
            id=s.id, matricule=s.matricule, first_name=s.first_name, last_name=s.last_name,
            status=s.status, class_id=cid, class_name=cname,
        )
        for s, cid, cname in rows
    ]


@router.get("/students/{student_id}", response_model=TeacherStudentDetailOut)
async def get_my_student(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> TeacherStudentDetailOut:
    scope = await service.ensure_teacher(db, current_user)
    mine = [(cid, cname) for s, cid, cname in await _enrolled_students(db, scope.class_ids) if s.id == student_id]
    student = await db.get(Student, student_id)
    if student is None or not mine:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    classes = list({cid: cname for cid, cname in mine}.items())
    return TeacherStudentDetailOut(
        id=student.id,
        matricule=student.matricule,
        first_name=student.first_name,
        last_name=student.last_name,
        status=student.status,
        classes=[TeacherClassRefOut(class_id=cid, class_name=cname) for cid, cname in classes],
    )


@router.get("/classes/{class_id}/attendance-sessions", response_model=list[TeacherAttendanceSessionOut])
async def list_class_attendance_sessions(
    class_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
) -> list[TeacherAttendanceSessionOut]:
    await service.ensure_class_access(db, current_user, class_id)
    stmt = select(AttendanceSession).where(AttendanceSession.class_id == class_id)
    if date_from:
        stmt = stmt.where(AttendanceSession.session_date >= date_from)
    if date_to:
        stmt = stmt.where(AttendanceSession.session_date <= date_to)
    sessions = (await db.execute(stmt.order_by(AttendanceSession.session_date.desc()))).scalars().all()
    return [
        TeacherAttendanceSessionOut(
            id=s.id,
            class_id=s.class_id,
            academic_term_id=s.academic_term_id,
            session_date=s.session_date,
            locked=s.locked,
            taken_by=s.taken_by,
        )
        for s in sessions
    ]


@router.get("/classes/{class_id}/assessments", response_model=list[TeacherAssessmentOut])
async def list_class_assessments(class_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[TeacherAssessmentOut]:
    await service.ensure_class_access(db, current_user, class_id)
    scope = await service.teacher_scope(db, current_user)
    allowed = [cs for cs, cid in scope.class_subject_to_class.items() if cid == class_id]
    if not allowed:
        return []
    rows = await db.execute(
        select(Assessment, Subject.name)
        .join(ClassSubject, ClassSubject.id == Assessment.class_subject_id)
        .join(Subject, Subject.id == ClassSubject.subject_id)
        .where(Assessment.class_subject_id.in_(allowed))
        .order_by(Assessment.assessment_date.desc())
    )
    return [
        TeacherAssessmentOut(
            id=a.id,
            name=a.name,
            class_subject_id=a.class_subject_id,
            subject_name=subject_name,
            academic_term_id=a.academic_term_id,
            max_score=float(a.max_score),
            assessment_date=a.assessment_date,
        )
        for a, subject_name in rows.all()
    ]


@router.get("/classes/{class_id}/report-cards", response_model=list[TeacherReportCardOut])
async def list_class_report_cards(
    class_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    academic_term_id: uuid.UUID | None = Query(None),
) -> list[TeacherReportCardOut]:
    """Bulletins PUBLIÉS des élèves de la classe uniquement. Les brouillons restent administratifs."""
    await service.ensure_class_access(db, current_user, class_id)
    stmt = (
        select(ReportCard, Student)
        .join(Student, Student.id == ReportCard.student_id)
        .where(ReportCard.class_id == class_id, ReportCard.status == "PUBLISHED")
    )
    if academic_term_id is not None:
        stmt = stmt.where(ReportCard.academic_term_id == academic_term_id)
    rows = await db.execute(stmt.order_by(Student.last_name, Student.first_name))
    return [
        TeacherReportCardOut(
            id=rc.id,
            student_id=rc.student_id,
            student_name=f"{s.first_name} {s.last_name}",
            academic_term_id=rc.academic_term_id,
            status=rc.status,
            published_at=rc.published_at,
        )
        for rc, s in rows.all()
    ]


@router.get("/report-cards/{report_card_id}/pdf")
async def download_my_report_card_pdf(report_card_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Response:
    """PDF d'un bulletin PUBLIÉ, uniquement si sa classe fait partie du périmètre enseignant."""
    report_card = await db.get(ReportCard, report_card_id)
    if report_card is None or report_card.status != "PUBLISHED":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")
    await service.ensure_class_access(db, current_user, report_card.class_id)
    content = await storage.download(report_card.pdf_path)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="bulletin_{report_card.id}.pdf"'},
    )
