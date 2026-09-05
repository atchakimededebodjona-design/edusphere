import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.academics.models import AcademicTerm, AcademicYear
from app.modules.attendance import service as attendance_service
from app.modules.grades import service as grades_service
from app.modules.report_cards.models import ReportCard
from app.modules.schools.models import School
from app.modules.students.models import Student


async def _get_current_term(db: AsyncSession, school_id: uuid.UUID) -> AcademicTerm | None:
    """« Terme courant » : le terme de l'année marquée `is_current` (AcademicYear.is_current,
    déjà utilisée ailleurs — ex. apps/web ClassesPanel) dont la période couvre aujourd'hui.
    Aucune nouvelle notion de "période" : uniquement les champs déjà existants."""
    today = date.today()
    result = await db.execute(
        select(AcademicTerm)
        .join(AcademicYear, AcademicYear.id == AcademicTerm.academic_year_id)
        .where(
            AcademicTerm.school_id == school_id,
            AcademicYear.is_current.is_(True),
            AcademicTerm.start_date <= today,
            AcademicTerm.end_date >= today,
        )
    )
    return result.scalar_one_or_none()


async def get_dashboard_summary(db: AsyncSession, school: School) -> dict:
    """Tableau de bord admin (Phase 10) — strictement les 4 métriques approuvées. Chaque
    métrique réutilise une définition déjà existante dans son module d'origine plutôt que
    d'inventer une nouvelle règle métier : voir attendance/service.py::compute_school_summary
    et grades/service.py::compute_school_completeness."""
    student_count_result = await db.execute(
        select(func.count()).select_from(Student).where(Student.school_id == school.id, Student.status == "ACTIVE")
    )
    active_student_count = student_count_result.scalar_one()

    published_result = await db.execute(
        select(func.count())
        .select_from(ReportCard)
        .where(ReportCard.school_id == school.id, ReportCard.published_at.isnot(None))
    )
    published_report_card_count = published_result.scalar_one()

    current_term = await _get_current_term(db, school.id)

    attendance_rate: float | None = None
    grade_completeness_rate: float | None = None
    if current_term is not None:
        attendance_summary = await attendance_service.compute_school_summary(db, school.id, current_term.id)
        attendance_rate = attendance_summary["attendance_rate"]
        completeness = await grades_service.compute_school_completeness(db, school.id, current_term.id)
        grade_completeness_rate = completeness["completeness_rate"]

    return {
        "active_student_count": active_student_count,
        "attendance_rate": attendance_rate,
        "grade_completeness_rate": grade_completeness_rate,
        "published_report_card_count": published_report_card_count,
        "current_term_id": current_term.id if current_term else None,
        "current_term_name": current_term.name if current_term else None,
    }
