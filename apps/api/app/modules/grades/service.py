import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.models import AcademicTerm, ClassSubject
from app.modules.grades.models import Assessment, AssessmentResult, StudentSubjectAverage, StudentTermAverage
from app.modules.students.models import Student, StudentEnrollment

TARGET_SCALE = Decimal(20)


async def student_in_class_scope(db: AsyncSession, student: Student, class_id: uuid.UUID) -> bool:
    """Vérifie qu'un élève est activement inscrit dans la classe visée — École ET Classe, même
    contrôle que `attendance/service.py::student_in_class_scope` (Phase 22 — corrige un IDOR
    confirmé : avant cette phase, `grades` n'exigeait aucune appartenance élève/classe, seulement
    une permission `grades.manage` sur l'école de l'appelant, permettant de saisir une note pour
    un `student_id` arbitraire d'un autre tenant — voir PHASE_22_DISCOVERY.md)."""
    result = await db.execute(
        select(StudentEnrollment.id).where(
            StudentEnrollment.student_id == student.id,
            StudentEnrollment.class_id == class_id,
            StudentEnrollment.status == "ACTIVE",
        )
    )
    return result.scalar_one_or_none() is not None


async def recompute_subject_averages(
    db: AsyncSession, student_ids: set[uuid.UUID], class_subject: ClassSubject, academic_term_id: uuid.UUID
) -> None:
    """Moyenne pondérée des évaluations notées (non absentes), pour une matière et une période,
    ramenée sur 20, pour TOUS les élèves de `student_ids` en une seule paire de requêtes (au lieu
    d'une paire par élève) — Phase 25, corrige le N+1 confirmé en Discovery (~40 élèves x plusieurs
    requêtes chacun pour une seule sauvegarde de notes). Une absence exclut l'évaluation du calcul
    plutôt que de compter comme 0 — décision documentée dans PHASE_4 (pas de pénalité implicite).
    Résultat strictement identique à un calcul élève par élève, seul le nombre d'aller-retours SQL
    change."""
    if not student_ids:
        return

    results = await db.execute(
        select(AssessmentResult.student_id, Assessment.max_score, Assessment.weight, AssessmentResult.score)
        .join(Assessment, Assessment.id == AssessmentResult.assessment_id)
        .where(
            Assessment.class_subject_id == class_subject.id,
            Assessment.academic_term_id == academic_term_id,
            AssessmentResult.student_id.in_(student_ids),
            AssessmentResult.is_absent.is_(False),
            AssessmentResult.score.isnot(None),
        )
    )
    rows_by_student: dict[uuid.UUID, list[tuple[float, float, float]]] = {}
    for student_id, max_score, weight, score in results.all():
        rows_by_student.setdefault(student_id, []).append((max_score, weight, score))

    existing_result = await db.execute(
        select(StudentSubjectAverage).where(
            StudentSubjectAverage.student_id.in_(student_ids),
            StudentSubjectAverage.class_subject_id == class_subject.id,
            StudentSubjectAverage.academic_term_id == academic_term_id,
        )
    )
    existing_by_student = {row.student_id: row for row in existing_result.scalars().all()}

    for student_id in student_ids:
        average_row = existing_by_student.get(student_id)
        if average_row is None:
            average_row = StudentSubjectAverage(
                id=uuid.uuid4(),
                school_id=class_subject.school_id,
                organization_id=class_subject.organization_id,
                student_id=student_id,
                class_subject_id=class_subject.id,
                academic_term_id=academic_term_id,
            )
            db.add(average_row)

        rows = rows_by_student.get(student_id, [])
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


async def recompute_term_averages(db: AsyncSession, student_ids: set[uuid.UUID], academic_term_id: uuid.UUID) -> None:
    """Moyenne générale, pondérée par les coefficients des matières de la classe active pour
    l'année scolaire de la période, pour TOUS les élèves de `student_ids` en un nombre fixe de
    requêtes plutôt qu'une requête d'inscription + une requête de matières de classe + une
    requête de moyenne matière PAR MATIÈRE PAR ÉLÈVE — Phase 25, corrige le N+1 le plus coûteux
    confirmé en Discovery (dominant du total ~360 requêtes pour une classe de 40 élèves/8
    matières). Résultat strictement identique à un calcul élève par élève."""
    if not student_ids:
        return

    term = await db.get(AcademicTerm, academic_term_id)
    assert term is not None

    enrollments_result = await db.execute(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id.in_(student_ids),
            StudentEnrollment.academic_year_id == term.academic_year_id,
            StudentEnrollment.status == "ACTIVE",
        )
    )
    enrollment_by_student = {e.student_id: e for e in enrollments_result.scalars().all()}

    existing_result = await db.execute(
        select(StudentTermAverage).where(
            StudentTermAverage.student_id.in_(student_ids),
            StudentTermAverage.academic_term_id == academic_term_id,
        )
    )
    term_average_by_student = {row.student_id: row for row in existing_result.scalars().all()}

    class_ids = {e.class_id for e in enrollment_by_student.values()}
    class_subjects_by_class: dict[uuid.UUID, list[ClassSubject]] = {}
    if class_ids:
        class_subjects_result = await db.execute(select(ClassSubject).where(ClassSubject.class_id.in_(class_ids)))
        for class_subject in class_subjects_result.scalars().all():
            class_subjects_by_class.setdefault(class_subject.class_id, []).append(class_subject)

    all_class_subject_ids = [cs.id for subjects in class_subjects_by_class.values() for cs in subjects]
    subject_average_by_key: dict[tuple[uuid.UUID, uuid.UUID], float] = {}
    if all_class_subject_ids:
        subject_averages_result = await db.execute(
            select(StudentSubjectAverage).where(
                StudentSubjectAverage.student_id.in_(student_ids),
                StudentSubjectAverage.class_subject_id.in_(all_class_subject_ids),
                StudentSubjectAverage.academic_term_id == academic_term_id,
            )
        )
        for row in subject_averages_result.scalars().all():
            if row.average is not None:
                subject_average_by_key[(row.student_id, row.class_subject_id)] = row.average

    for student_id in student_ids:
        term_average_row = term_average_by_student.get(student_id)
        if term_average_row is None:
            term_average_row = StudentTermAverage(
                id=uuid.uuid4(),
                school_id=term.school_id,
                organization_id=term.organization_id,
                student_id=student_id,
                academic_term_id=academic_term_id,
            )
            db.add(term_average_row)

        enrollment = enrollment_by_student.get(student_id)
        if enrollment is None:
            term_average_row.average = None
            continue

        weighted_sum = Decimal(0)
        total_coefficient = Decimal(0)
        for class_subject in class_subjects_by_class.get(enrollment.class_id, []):
            subject_average = subject_average_by_key.get((student_id, class_subject.id))
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
    classement général, pour chaque élève concerné.

    Phase 25 — l'upsert et les deux étapes de recalcul de moyenne sont batchés par lot d'élèves
    (une requête pour tous les élèves de `entries` au lieu d'une requête par élève) : corrige un
    N+1 confirmé en Discovery Phase 25 (~360 requêtes SQL pour une classe de 40 élèves/8 matières
    lors d'une seule sauvegarde de notes). Les classements restaient déjà en une seule requête
    (portée classe/matière entière, pas par élève) et ne changent pas. Résultats et règles de
    calcul strictement identiques à la version précédente — seul le nombre d'aller-retours SQL
    change."""
    class_subject = await db.get(ClassSubject, assessment.class_subject_id)
    assert class_subject is not None

    entry_student_ids = [student_id for student_id, _, _ in entries]
    existing_results = await db.execute(
        select(AssessmentResult).where(
            AssessmentResult.assessment_id == assessment.id,
            AssessmentResult.student_id.in_(entry_student_ids),
        )
    )
    existing_by_student = {row.student_id: row for row in existing_results.scalars().all()}

    saved_results = []
    student_ids: set[uuid.UUID] = set()

    for student_id, score, is_absent in entries:
        row = existing_by_student.get(student_id)
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

    await recompute_subject_averages(db, student_ids, class_subject, assessment.academic_term_id)
    await recompute_subject_ranks(db, assessment.class_subject_id, assessment.academic_term_id)
    await recompute_term_averages(db, student_ids, assessment.academic_term_id)
    await recompute_term_ranks(db, class_subject.class_id, assessment.academic_term_id)

    # refresh() AVANT commit : ces tables ont RLS activée, leurs lignes ne sont visibles que le
    # temps de la transaction courante (voir app/modules/auth/service.py::register pour le
    # détail de ce piège). Batché en une seule requête pour tous les résultats plutôt qu'un
    # refresh() par ligne (Phase 25) — `populate_existing` recharge les instances déjà en
    # identity map avec leurs valeurs serveur (updated_at) sans requête supplémentaire par ligne.
    if saved_results:
        result_ids = [row.id for row in saved_results]
        refreshed = await db.execute(
            select(AssessmentResult).where(AssessmentResult.id.in_(result_ids)).execution_options(populate_existing=True)
        )
        refreshed_by_id = {row.id: row for row in refreshed.scalars().all()}
        saved_results = [refreshed_by_id[row.id] for row in saved_results]

    await db.commit()
    return saved_results


async def compute_school_completeness(db: AsyncSession, school_id: uuid.UUID, academic_term_id: uuid.UUID) -> dict:
    """Complétude de saisie des notes (Phase 10, tableau de bord admin) : pour les évaluations
    créées ce terme, résultats attendus (un par élève activement inscrit dans la classe de
    l'évaluation, cf. `student_enrollments.status == "ACTIVE"`, même filtre que
    `recompute_term_averages`/`recompute_term_ranks` ci-dessus) vs résultats effectivement
    saisis (`assessment_results`). N'invente pas de notion de "note attendue" au-delà de ce que
    le modèle représente déjà (une inscription active = un résultat attendu par évaluation)."""
    expected_result = await db.execute(
        select(func.count())
        .select_from(Assessment)
        .join(ClassSubject, ClassSubject.id == Assessment.class_subject_id)
        .join(
            StudentEnrollment,
            (StudentEnrollment.class_id == ClassSubject.class_id) & (StudentEnrollment.status == "ACTIVE"),
        )
        .where(Assessment.school_id == school_id, Assessment.academic_term_id == academic_term_id)
    )
    expected = expected_result.scalar_one()

    actual_result = await db.execute(
        select(func.count())
        .select_from(AssessmentResult)
        .join(Assessment, Assessment.id == AssessmentResult.assessment_id)
        .where(Assessment.school_id == school_id, Assessment.academic_term_id == academic_term_id)
    )
    actual = actual_result.scalar_one()

    rate = round(actual / expected * 100, 2) if expected > 0 else None
    return {"expected_results": expected, "actual_results": actual, "completeness_rate": rate}
