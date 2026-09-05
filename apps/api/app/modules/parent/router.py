import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession
from app.core.storage import storage
from app.modules.attendance import service as attendance_service
from app.modules.fees import service as fees_service
from app.modules.fees.models import Payment
from app.modules.fees.schemas import FinancialSummaryOut, PaymentOut
from app.modules.grades.models import StudentSubjectAverage, StudentTermAverage
from app.modules.grades.schemas import StudentAveragesOut, StudentSubjectAverageOut, StudentTermAverageOut
from app.modules.parent import service
from app.modules.parent.schemas import ParentAttendanceSummaryOut
from app.modules.report_cards.models import ReportCard
from app.modules.report_cards.schemas import ReportCardOut
from app.modules.students.models import Student
from app.modules.students.schemas import StudentOut
from app.modules.users.models import User

router = APIRouter()


# --- Helpers -----------------------------------------------------------------
async def _get_child_or_404(db: AsyncSession, current_user: User, student_id: uuid.UUID) -> Student:
    """Unique porte d'entrée pour tous les endpoints ci-dessous : aucune permission RBAC n'est
    vérifiée ici (décision validée Phase 7 — PARENT ne reçoit aucune permission `.read` scopée
    école), seule l'appartenance réelle « cet élève est un de mes enfants » compte. 404 dans
    tous les cas d'échec, jamais 403, pour ne jamais révéler l'existence de l'élève à un tiers."""
    student = await service.get_child(db, current_user.id, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


# --- Enfants -------------------------------------------------------------------
@router.get("/parent/children", response_model=list[StudentOut])
async def list_children(db: DbSession, current_user: CurrentUser) -> list[Student]:
    return await service.list_children(db, current_user.id)


# --- Présence (réutilise le calcul de la Phase 6, aucune réécriture) ---------------
@router.get("/parent/children/{student_id}/attendance-summary", response_model=ParentAttendanceSummaryOut)
async def get_child_attendance_summary(
    student_id: uuid.UUID,
    db: DbSession,
    current_user: CurrentUser,
    academic_term_id: uuid.UUID | None = Query(None),
) -> ParentAttendanceSummaryOut:
    """`academic_term_id` optionnel : le mobile parent (pas de sélecteur de période, périmètre
    minimal validé) l'omet et reçoit un agrégat toutes périodes confondues."""
    student = await _get_child_or_404(db, current_user, student_id)
    summary = await attendance_service.compute_student_summary(db, student.id, academic_term_id)
    return ParentAttendanceSummaryOut(student_id=student.id, academic_term_id=academic_term_id, **summary)


# --- Notes (réutilise les moyennes de la Phase 4, aucune réécriture) --------------
@router.get("/parent/children/{student_id}/grades", response_model=StudentAveragesOut)
async def get_child_grades(
    student_id: uuid.UUID, db: DbSession, current_user: CurrentUser, academic_term_id: uuid.UUID | None = Query(None)
) -> StudentAveragesOut:
    student = await _get_child_or_404(db, current_user, student_id)

    subject_stmt = select(StudentSubjectAverage).where(StudentSubjectAverage.student_id == student.id)
    term_stmt = select(StudentTermAverage).where(StudentTermAverage.student_id == student.id)
    if academic_term_id:
        subject_stmt = subject_stmt.where(StudentSubjectAverage.academic_term_id == academic_term_id)
        term_stmt = term_stmt.where(StudentTermAverage.academic_term_id == academic_term_id)

    subject_result = await db.execute(subject_stmt)
    term_result = await db.execute(term_stmt)

    return StudentAveragesOut(
        subject_averages=[StudentSubjectAverageOut.model_validate(row) for row in subject_result.scalars().all()],
        term_averages=[StudentTermAverageOut.model_validate(row) for row in term_result.scalars().all()],
    )


# --- Bulletins — publiés uniquement ------------------------------------------------
@router.get("/parent/children/{student_id}/report-cards", response_model=list[ReportCardOut])
async def list_child_report_cards(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[ReportCard]:
    student = await _get_child_or_404(db, current_user, student_id)
    result = await db.execute(
        select(ReportCard).where(ReportCard.student_id == student.id, ReportCard.published_at.isnot(None))
    )
    return list(result.scalars().all())


@router.get("/parent/children/{student_id}/report-cards/{report_card_id}/pdf")
async def download_child_report_card_pdf(
    student_id: uuid.UUID, report_card_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    student = await _get_child_or_404(db, current_user, student_id)

    report_card = await db.get(ReportCard, report_card_id)
    if report_card is None or report_card.student_id != student.id or report_card.published_at is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report card not found")

    content = await storage.download(report_card.pdf_path)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="bulletin_{student.matricule}.pdf"'},
    )


# --- Frais scolaires (Phase 19) — lecture seule uniquement ------------------------
# Aucune permission RBAC vérifiée ici (comme le reste de ce module) : le lien Guardian via
# _get_child_or_404 est le seul contrôle d'accès. Le parent ne peut jamais créer, modifier,
# annuler un paiement ni déclarer un règlement — voir PHASE_19_DISCOVERY.md §21.
@router.get("/parent/children/{student_id}/fees", response_model=FinancialSummaryOut)
async def get_child_fees(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> FinancialSummaryOut:
    student = await _get_child_or_404(db, current_user, student_id)
    return await fees_service.compute_financial_summary(db, student)


@router.get("/parent/children/{student_id}/payments", response_model=list[PaymentOut])
async def list_child_payments(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> list[Payment]:
    student = await _get_child_or_404(db, current_user, student_id)
    result = await db.execute(
        select(Payment).where(Payment.student_id == student.id).order_by(Payment.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/parent/children/{student_id}/payments/{payment_id}/receipt.pdf")
async def download_child_receipt_pdf(
    student_id: uuid.UUID, payment_id: uuid.UUID, db: DbSession, current_user: CurrentUser
) -> Response:
    student = await _get_child_or_404(db, current_user, student_id)

    payment = await db.get(Payment, payment_id)
    if payment is None or payment.student_id != student.id or payment.pdf_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not found")

    content = await storage.download(payment.pdf_path)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{payment.receipt_number}.pdf"'},
    )
