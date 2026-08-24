import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission, is_teacher_only
from app.modules.academics.models import ClassSubject, SchoolClass, TeacherAssignment
from app.modules.grades import service
from app.modules.grades.models import (
    Assessment,
    AssessmentResult,
    AssessmentType,
    StudentSubjectAverage,
    StudentTermAverage,
)
from app.modules.grades.schemas import (
    AssessmentCreate,
    AssessmentOut,
    AssessmentResultOut,
    AssessmentResultsBulkCreate,
    AssessmentResultUpdate,
    AssessmentTypeCreate,
    AssessmentTypeOut,
    ClassPerformanceEntry,
    ClassPerformanceOut,
    StudentAveragesOut,
    StudentSubjectAverageOut,
    StudentSubjectAverageUpdate,
    StudentTermAverageOut,
)
from app.modules.schools.models import School
from app.modules.students.models import Student, StudentEnrollment
from app.modules.users.models import User

router = APIRouter()


# --- Helpers -----------------------------------------------------------------
async def _get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


async def _get_class_subject_or_404(db: AsyncSession, class_subject_id: uuid.UUID) -> ClassSubject:
    class_subject = await db.get(ClassSubject, class_subject_id)
    if class_subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class subject not found")
    return class_subject


async def _get_assessment_or_404(db: AsyncSession, assessment_id: uuid.UUID) -> Assessment:
    assessment = await db.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return assessment


async def _ensure_can_manage_class_subject_grades(
    db: AsyncSession, current_user: User, class_subject: ClassSubject
) -> None:
    """grades.manage scopé à l'école, PUIS, si l'utilisateur n'est que TEACHER pour cette école,
    vérifie qu'il est bien affecté à cette classe+matière (teacher_assignments, Phase 2)."""
    await ensure_permission(
        db, current_user, "grades.manage", organization_id=class_subject.organization_id, school_id=class_subject.school_id
    )
    if await is_teacher_only(db, current_user, class_subject.organization_id, class_subject.school_id):
        result = await db.execute(
            select(TeacherAssignment).where(
                TeacherAssignment.user_id == current_user.id, TeacherAssignment.class_subject_id == class_subject.id
            )
        )
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="You are not assigned to this class subject"
            )


# --- Assessment types ------------------------------------------------------------
@router.get("/assessment-types", response_model=list[AssessmentTypeOut])
async def list_assessment_types(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)
) -> list[AssessmentType]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "grades.read", organization_id=school.organization_id, school_id=school.id)
    result = await db.execute(select(AssessmentType).where(AssessmentType.school_id == school_id).order_by(AssessmentType.name))
    return list(result.scalars().all())


@router.post("/assessment-types", response_model=AssessmentTypeOut, status_code=status.HTTP_201_CREATED)
async def create_assessment_type(payload: AssessmentTypeCreate, db: DbSession, current_user: CurrentUser) -> AssessmentType:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "grades.manage", organization_id=school.organization_id, school_id=school.id)

    assessment_type = AssessmentType(
        id=uuid.uuid4(), school_id=school.id, organization_id=school.organization_id, name=payload.name
    )
    db.add(assessment_type)
    try:
        await db.flush()
        await db.refresh(assessment_type)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An assessment type with this name already exists") from exc
    return assessment_type


# --- Assessments ---------------------------------------------------------------
@router.get("/assessments", response_model=list[AssessmentOut])
async def list_assessments(
    db: DbSession,
    current_user: CurrentUser,
    class_subject_id: uuid.UUID = Query(...),
    academic_term_id: uuid.UUID | None = Query(None),
) -> list[Assessment]:
    class_subject = await _get_class_subject_or_404(db, class_subject_id)
    await ensure_permission(
        db, current_user, "grades.read", organization_id=class_subject.organization_id, school_id=class_subject.school_id
    )
    stmt = select(Assessment).where(Assessment.class_subject_id == class_subject_id)
    if academic_term_id:
        stmt = stmt.where(Assessment.academic_term_id == academic_term_id)
    result = await db.execute(stmt.order_by(Assessment.assessment_date.desc()))
    return list(result.scalars().all())


@router.post("/assessments", response_model=AssessmentOut, status_code=status.HTTP_201_CREATED)
async def create_assessment(payload: AssessmentCreate, db: DbSession, current_user: CurrentUser) -> Assessment:
    class_subject = await _get_class_subject_or_404(db, payload.class_subject_id)
    await _ensure_can_manage_class_subject_grades(db, current_user, class_subject)

    assessment = Assessment(
        id=uuid.uuid4(),
        school_id=class_subject.school_id,
        organization_id=class_subject.organization_id,
        class_subject_id=class_subject.id,
        academic_term_id=payload.academic_term_id,
        assessment_type_id=payload.assessment_type_id,
        name=payload.name,
        max_score=payload.max_score,
        weight=payload.weight,
        assessment_date=payload.assessment_date,
    )
    db.add(assessment)
    await db.flush()
    await db.refresh(assessment)
    await db.commit()
    return assessment


# --- Results -----------------------------------------------------------------------
@router.get("/results", response_model=list[AssessmentResultOut])
async def list_results(db: DbSession, current_user: CurrentUser, assessment_id: uuid.UUID = Query(...)) -> list[AssessmentResult]:
    assessment = await _get_assessment_or_404(db, assessment_id)
    await ensure_permission(
        db, current_user, "grades.read", organization_id=assessment.organization_id, school_id=assessment.school_id
    )
    result = await db.execute(select(AssessmentResult).where(AssessmentResult.assessment_id == assessment_id))
    return list(result.scalars().all())


@router.post("/results", response_model=list[AssessmentResultOut], status_code=status.HTTP_201_CREATED)
async def submit_results(payload: AssessmentResultsBulkCreate, db: DbSession, current_user: CurrentUser) -> list[AssessmentResult]:
    assessment = await _get_assessment_or_404(db, payload.assessment_id)
    class_subject = await _get_class_subject_or_404(db, assessment.class_subject_id)
    await _ensure_can_manage_class_subject_grades(db, current_user, class_subject)

    entries = [(entry.student_id, entry.score, entry.is_absent) for entry in payload.results]
    return await service.apply_results_and_recompute(db, assessment, entries)


@router.patch("/results/{result_id}", response_model=AssessmentResultOut)
async def update_result(result_id: uuid.UUID, payload: AssessmentResultUpdate, db: DbSession, current_user: CurrentUser) -> AssessmentResult:
    result_row = await db.get(AssessmentResult, result_id)
    if result_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    assessment = await _get_assessment_or_404(db, result_row.assessment_id)
    class_subject = await _get_class_subject_or_404(db, assessment.class_subject_id)
    await _ensure_can_manage_class_subject_grades(db, current_user, class_subject)

    entries = [
        (
            result_row.student_id,
            payload.score if payload.score is not None else result_row.score,
            payload.is_absent if payload.is_absent is not None else result_row.is_absent,
        )
    ]
    updated = await service.apply_results_and_recompute(db, assessment, entries)
    return updated[0]


# --- Averages --------------------------------------------------------------------
@router.get("/students/{student_id}/averages", response_model=StudentAveragesOut)
async def get_student_averages(
    student_id: uuid.UUID, db: DbSession, current_user: CurrentUser, academic_term_id: uuid.UUID | None = Query(None)
) -> StudentAveragesOut:
    student = await db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    await ensure_permission(db, current_user, "grades.read", organization_id=student.organization_id, school_id=student.school_id)

    subject_stmt = select(StudentSubjectAverage).where(StudentSubjectAverage.student_id == student_id)
    term_stmt = select(StudentTermAverage).where(StudentTermAverage.student_id == student_id)
    if academic_term_id:
        subject_stmt = subject_stmt.where(StudentSubjectAverage.academic_term_id == academic_term_id)
        term_stmt = term_stmt.where(StudentTermAverage.academic_term_id == academic_term_id)

    subject_result = await db.execute(subject_stmt)
    term_result = await db.execute(term_stmt)

    return StudentAveragesOut(
        subject_averages=[StudentSubjectAverageOut.model_validate(row) for row in subject_result.scalars().all()],
        term_averages=[StudentTermAverageOut.model_validate(row) for row in term_result.scalars().all()],
    )


@router.patch("/student-subject-averages/{average_id}", response_model=StudentSubjectAverageOut)
async def update_subject_average_appreciation(
    average_id: uuid.UUID, payload: StudentSubjectAverageUpdate, db: DbSession, current_user: CurrentUser
) -> StudentSubjectAverage:
    average = await db.get(StudentSubjectAverage, average_id)
    if average is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Average not found")

    class_subject = await _get_class_subject_or_404(db, average.class_subject_id)
    await _ensure_can_manage_class_subject_grades(db, current_user, class_subject)

    average.appreciation = payload.appreciation
    await db.flush()
    await db.refresh(average)
    await db.commit()
    return average


@router.get("/classes/{class_id}/performance", response_model=ClassPerformanceOut)
async def get_class_performance(
    class_id: uuid.UUID, db: DbSession, current_user: CurrentUser, academic_term_id: uuid.UUID = Query(...)
) -> ClassPerformanceOut:
    school_class = await db.get(SchoolClass, class_id)
    if school_class is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Class not found")
    await ensure_permission(
        db, current_user, "grades.read", organization_id=school_class.organization_id, school_id=school_class.school_id
    )

    result = await db.execute(
        select(StudentTermAverage)
        .join(StudentEnrollment, StudentEnrollment.student_id == StudentTermAverage.student_id)
        .where(
            StudentTermAverage.academic_term_id == academic_term_id,
            StudentEnrollment.class_id == class_id,
            StudentEnrollment.status == "ACTIVE",
        )
        .order_by(StudentTermAverage.rank.asc().nullslast())
    )
    rows = list(result.scalars().all())

    return ClassPerformanceOut(
        academic_term_id=academic_term_id,
        class_id=class_id,
        students=[ClassPerformanceEntry(student_id=r.student_id, average=r.average, rank=r.rank) for r in rows],
    )
