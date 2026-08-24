import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.models import AcademicTerm, ClassSubject
from app.modules.grades.models import Assessment, AssessmentResult, StudentSubjectAverage, StudentTermAverage
from app.modules.students.models import StudentEnrollment

TARGET_SCALE = Decimal(20)


async def _get_or_create_subject_average(
    db: AsyncSession, student_id: uuid.UUID, class_subject_id: uuid.UUID, academic_term_id: uuid.UUID
) -> StudentSubjectAverage:
    result = await db.execute(
        select(StudentSubjectAverage).where(
            StudentSubjectAverage.student_id == student_id,
            StudentSubjectAverage.class_subject_id == class_subject_id,
            StudentSubjectAverage.academic_term_id == academic_term_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is not None:
        return row

    class_subject = await db.get(ClassSubject, class_subject_id)
    assert class_subject is not None
    row = StudentSubjectAverage(
        id=uuid.uuid4(),
        school_id=class_subject.school_id,
        organization_id=class_subject.organization_id,
        student_id=student_id,
        class_subject_id=class_subject_id,
        academic_term_id=academic_term_id,
    )
    db.add(row)
    return row


async def recompute_subject_average(
    db: AsyncSession, student_id: uuid.UUID, class_subject_id: uuid.UUID, academic_term_id: uuid.UUID
) -> None:
    """Moyenne pondérée des évaluations notées (non absentes) d'un élève, pour une matière et
    une période, ramenée sur 20. Une absence exclut l'évaluation du calcul plutôt que de
    compter comme 0 — décision documentée dans PHASE_4 (pas de pénalité implicite)."""
    result = await db.execute(
        select(Assessment.max_score, Assessment.weight, AssessmentResult.score)
        .join(AssessmentResult, AssessmentResult.assessment_id == Assessment.id)
        .where(
            Assessment.class_subject_id == class_subject_id,
            Assessment.academic_term_id == academic_term_id,
            AssessmentResult.student_id == student_id,
            AssessmentResult.is_absent.is_(False),
            AssessmentResult.score.isnot(None),
        )
    )
    rows = result.all()

    average_row = await _get_or_create_subject_average(db, student_id, class_subject_id, academic_term_id)

    if not rows:
        average_row.average = None
    else:
        weighted_sum = Decimal(0)
        total_weight = Decimal(0)
        for max_score, weight, score in rows:
            percentage = Decimal(score) / Decimal(max_score)
            weighted_sum += percentage * Decimal(weight)
            total_weight += Decimal(weight)
        average_row.average = float(weighted_sum / total_weight * TARGET_SCALE) if total_weight > 0 else None

    await db.flush()


async def recompute_subject_ranks(db: AsyncSession, class_subject_id: uuid.UUID, academic_term_id: uuid.UUID) -> None:
    result = await db.execute(
        select(StudentSubjectAverage)
        .where(
            StudentSubjectAverage.class_subject_id == class_subject_id,
            StudentSubjectAverage.academic_term_id == academic_term_id,
        )
        .order_by(StudentSubjectAverage.average.desc().nullslast())
    )
    rows = list(result.scalars().all())
    _assign_ranks(rows)
    await db.flush()


def _assign_ranks(rows: list) -> None:
    """Classement standard (1, 2, 2, 4...) — les ex æquo partagent le même rang."""
    previous_average = None
    previous_rank = 0
    for index, row in enumerate(rows, start=1):
        if row.average is None:
            row.rank = None
            continue
        if row.average != previous_average:
            row.rank = index
            previous_rank = index
            previous_average = row.average
        else:
            row.rank = previous_rank


async def recompute_term_average(db: AsyncSession, student_id: uuid.UUID, academic_term_id: uuid.UUID) -> None:
    """Moyenne générale d'un élève pour une période, pondérée par les coefficients des
    matières de sa classe active pour l'année scolaire de cette période."""
    term = await db.get(AcademicTerm, academic_term_id)
    assert term is not None

    enrollment_result = await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == student_id,
            StudentEnrollment.academic_year_id == term.academic_year_id,
            StudentEnrollment.status == "ACTIVE",
        )
    )
    enrollment = enrollment_result.scalar_one_or_none()

    average_result = await db.execute(select(StudentTermAverage).where(
        StudentTermAverage.student_id == student_id, StudentTermAverage.academic_term_id == academic_term_id
    ))
    term_average_row = average_result.scalar_one_or_none()

    if term_average_row is None:
        term_average_row = StudentTermAverage(
            id=uuid.uuid4(),
            school_id=term.school_id,
            organization_id=term.organization_id,
            student_id=student_id,
            academic_term_id=academic_term_id,
        )
        db.add(term_average_row)

    if enrollment is None:
        term_average_row.average = None
        await db.flush()
        return

    class_subjects_result = await db.execute(select(ClassSubject).where(ClassSubject.class_id == enrollment.class_id))
    class_subjects = list(class_subjects_result.scalars().all())

    weighted_sum = Decimal(0)
    total_coefficient = Decimal(0)
    for class_subject in class_subjects:
        subject_average_result = await db.execute(
            select(StudentSubjectAverage.average).where(
                StudentSubjectAverage.student_id == student_id,
                StudentSubjectAverage.class_subject_id == class_subject.id,
                StudentSubjectAverage.academic_term_id == academic_term_id,
            )
        )
        subject_average = subject_average_result.scalar_one_or_none()
        if subject_average is None:
            continue
        weighted_sum += Decimal(subject_average) * Decimal(class_subject.coefficient)
        total_coefficient += Decimal(class_subject.coefficient)

    term_average_row.average = float(weighted_sum / total_coefficient) if total_coefficient > 0 else None
    await db.flush()


async def recompute_term_ranks(db: AsyncSession, class_id: uuid.UUID, academic_term_id: uuid.UUID) -> None:
    result = await db.execute(
        select(StudentTermAverage)
        .join(StudentEnrollment, StudentEnrollment.student_id == StudentTermAverage.student_id)
        .where(
            StudentTermAverage.academic_term_id == academic_term_id,
            StudentEnrollment.class_id == class_id,
            StudentEnrollment.status == "ACTIVE",
        )
        .order_by(StudentTermAverage.average.desc().nullslast())
    )
    rows = list(result.scalars().all())
    _assign_ranks(rows)
    await db.flush()


async def apply_results_and_recompute(
    db: AsyncSession, assessment: Assessment, entries: list[tuple[uuid.UUID, float | None, bool]]
) -> list[AssessmentResult]:
    """Upsert des résultats puis recalcul en cascade : moyenne/classement matière -> moyenne/
    classement général, pour chaque élève concerné."""
    class_subject = await db.get(ClassSubject, assessment.class_subject_id)
    assert class_subject is not None

    saved_results = []
    student_ids: set[uuid.UUID] = set()

    for student_id, score, is_absent in entries:
        result = await db.execute(
            select(AssessmentResult).where(
                AssessmentResult.assessment_id == assessment.id, AssessmentResult.student_id == student_id
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = AssessmentResult(
                id=uuid.uuid4(),
                school_id=assessment.school_id,
                organization_id=assessment.organization_id,
                assessment_id=assessment.id,
                student_id=student_id,
            )
            db.add(row)
        row.score = score
        row.is_absent = is_absent
        saved_results.append(row)
        student_ids.add(student_id)

    await db.flush()

    for student_id in student_ids:
        await recompute_subject_average(db, student_id, assessment.class_subject_id, assessment.academic_term_id)

    await recompute_subject_ranks(db, assessment.class_subject_id, assessment.academic_term_id)

    for student_id in student_ids:
        await recompute_term_average(db, student_id, assessment.academic_term_id)

    await recompute_term_ranks(db, class_subject.class_id, assessment.academic_term_id)

    # refresh() AVANT commit : ces tables ont RLS activée, leurs lignes ne sont visibles que le
    # temps de la transaction courante (voir app/modules/auth/service.py::register pour le
    # détail de ce piège).
    for row in saved_results:
        await db.refresh(row)
    await db.commit()
    return saved_results
