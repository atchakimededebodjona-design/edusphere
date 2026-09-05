import uuid

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.core.storage import storage
from app.modules.academics.models import AcademicYear, EducationLevel, SchoolClass
from app.modules.fees import service
from app.modules.fees.models import FeeCategory, FeeSchedule, Payment, StudentFee
from app.modules.fees.schemas import (
    FeeCategoryCreate,
    FeeCategoryOut,
    FeeScheduleCreate,
    FeeScheduleGenerateResult,
    FeeScheduleOut,
    FeesSummaryOut,
    FinancialSummaryOut,
    PaymentCancelRequest,
    PaymentCreate,
    PaymentOut,
    StudentFeeOut,
    StudentFeeUpdate,
)
from app.modules.schools.models import School
from app.modules.students.models import Student

router = APIRouter()


# --- Helpers -----------------------------------------------------------------
async def _get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


async def _get_student_or_404(db: AsyncSession, student_id: uuid.UUID) -> Student:
    student = await db.get(Student, student_id)
    if student is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


async def _get_fee_category_or_404(db: AsyncSession, fee_category_id: uuid.UUID) -> FeeCategory:
    category = await db.get(FeeCategory, fee_category_id)
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fee category not found")
    return category


async def _get_fee_schedule_or_404(db: AsyncSession, fee_schedule_id: uuid.UUID) -> FeeSchedule:
    schedule = await db.get(FeeSchedule, fee_schedule_id)
    if schedule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fee schedule not found")
    return schedule


async def _get_student_fee_or_404(db: AsyncSession, student_fee_id: uuid.UUID) -> StudentFee:
    student_fee = await db.get(StudentFee, student_fee_id)
    if student_fee is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student fee not found")
    return student_fee


async def _get_payment_or_404(db: AsyncSession, payment_id: uuid.UUID) -> Payment:
    payment = await db.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment


# --- Fee categories ------------------------------------------------------------
@router.post("/fee-categories", response_model=FeeCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_fee_category(payload: FeeCategoryCreate, db: DbSession, current_user: CurrentUser) -> FeeCategory:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "fees.manage", organization_id=school.organization_id, school_id=school.id)

    category = FeeCategory(id=uuid.uuid4(), school_id=school.id, organization_id=school.organization_id, name=payload.name)
    db.add(category)
    try:
        await db.flush()
        await db.refresh(category)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A fee category with this name already exists") from exc
    return category


@router.get("/fee-categories", response_model=list[FeeCategoryOut])
async def list_fee_categories(db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...)) -> list[FeeCategory]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "fees.read", organization_id=school.organization_id, school_id=school.id)
    result = await db.execute(select(FeeCategory).where(FeeCategory.school_id == school_id).order_by(FeeCategory.name))
    return list(result.scalars().all())


# --- Fee schedules ---------------------------------------------------------------
@router.post("/fee-schedules", response_model=FeeScheduleOut, status_code=status.HTTP_201_CREATED)
async def create_fee_schedule(payload: FeeScheduleCreate, db: DbSession, current_user: CurrentUser) -> FeeSchedule:
    school = await _get_school_or_404(db, payload.school_id)
    await ensure_permission(db, current_user, "fees.manage", organization_id=school.organization_id, school_id=school.id)

    category = await _get_fee_category_or_404(db, payload.fee_category_id)
    if category.school_id != school.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Fee category does not belong to this school")

    academic_year = await db.get(AcademicYear, payload.academic_year_id)
    if academic_year is None or academic_year.school_id != school.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Academic year does not belong to this school")

    if payload.scope_type == "CLASS":
        if payload.scope_class_id is None or payload.scope_education_level_id is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CLASS scope requires scope_class_id only")
        school_class = await db.get(SchoolClass, payload.scope_class_id)
        if school_class is None or school_class.school_id != school.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Class does not belong to this school")
    elif payload.scope_type == "LEVEL":
        if payload.scope_education_level_id is None or payload.scope_class_id is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="LEVEL scope requires scope_education_level_id only"
            )
        level = await db.get(EducationLevel, payload.scope_education_level_id)
        if level is None or level.school_id != school.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Education level does not belong to this school")
    elif payload.scope_class_id is not None or payload.scope_education_level_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SCHOOL scope must not set a class or level")

    schedule = FeeSchedule(
        id=uuid.uuid4(),
        school_id=school.id,
        organization_id=school.organization_id,
        fee_category_id=category.id,
        academic_year_id=academic_year.id,
        name=payload.name,
        amount=payload.amount,
        currency=school.currency,
        scope_type=payload.scope_type,
        scope_class_id=payload.scope_class_id,
        scope_education_level_id=payload.scope_education_level_id,
        is_optional=payload.is_optional,
        due_date=payload.due_date,
    )
    db.add(schedule)
    await db.flush()
    await db.refresh(schedule)
    await db.commit()
    return schedule


@router.get("/fee-schedules", response_model=list[FeeScheduleOut])
async def list_fee_schedules(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    academic_year_id: uuid.UUID | None = Query(None),
) -> list[FeeSchedule]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "fees.read", organization_id=school.organization_id, school_id=school.id)
    stmt = select(FeeSchedule).where(FeeSchedule.school_id == school_id)
    if academic_year_id is not None:
        stmt = stmt.where(FeeSchedule.academic_year_id == academic_year_id)
    result = await db.execute(stmt.order_by(FeeSchedule.name))
    return list(result.scalars().all())


@router.post("/fee-schedules/{fee_schedule_id}/generate", response_model=FeeScheduleGenerateResult)
async def generate_fee_schedule(fee_schedule_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> FeeScheduleGenerateResult:
    schedule = await _get_fee_schedule_or_404(db, fee_schedule_id)
    await ensure_permission(
        db, current_user, "fees.manage", organization_id=schedule.organization_id, school_id=schedule.school_id
    )
    return await service.generate_student_fees(db, schedule)


# --- Situation financière d'un élève ---------------------------------------------
@router.get("/students/{student_id}/financial-summary", response_model=FinancialSummaryOut)
async def get_student_financial_summary(student_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> FinancialSummaryOut:
    student = await _get_student_or_404(db, student_id)
    await ensure_permission(db, current_user, "fees.read", organization_id=student.organization_id, school_id=student.school_id)
    return await service.compute_financial_summary(db, student)


@router.patch("/student-fees/{student_fee_id}", response_model=StudentFeeOut)
async def update_student_fee(student_fee_id: uuid.UUID, payload: StudentFeeUpdate, db: DbSession, current_user: CurrentUser) -> StudentFee:
    student_fee = await _get_student_fee_or_404(db, student_fee_id)
    await ensure_permission(
        db, current_user, "fees.manage", organization_id=student_fee.organization_id, school_id=student_fee.school_id
    )
    if student_fee.status == "CANCELLED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot adjust a cancelled fee")

    # Phase 20 (traçabilité financière) : une note explicative est obligatoire dès qu'on modifie
    # le montant dû — c'est une opération sensible qui doit toujours être justifiée, pas seulement
    # attribuable (voir fees/models.py::StudentFee.updated_by).
    if payload.amount_due is not None and not (payload.note and payload.note.strip()):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A note is required when adjusting the due amount",
        )

    changed = False
    if payload.amount_due is not None:
        student_fee.amount_due = payload.amount_due
        changed = True
    if payload.due_date is not None:
        student_fee.due_date = payload.due_date
        changed = True
    if payload.note is not None:
        student_fee.note = payload.note
        changed = True

    if changed:
        student_fee.updated_by = current_user.id

    await db.flush()
    await db.refresh(student_fee)
    await db.commit()
    return student_fee


# --- Paiements -------------------------------------------------------------------
@router.post("/payments", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(payload: PaymentCreate, db: DbSession, current_user: CurrentUser) -> Payment:
    student = await _get_student_or_404(db, payload.student_id)
    await ensure_permission(
        db, current_user, "payments.manage", organization_id=student.organization_id, school_id=student.school_id
    )
    payment, notifications = await service.record_payment(db, student, payload, current_user.id)
    if notifications:
        await service.send_payment_notifications(notifications)
    return payment


@router.post("/payments/{payment_id}/cancel", response_model=PaymentOut)
async def cancel_payment(payment_id: uuid.UUID, payload: PaymentCancelRequest, db: DbSession, current_user: CurrentUser) -> Payment:
    payment = await _get_payment_or_404(db, payment_id)
    await ensure_permission(
        db, current_user, "payments.manage", organization_id=payment.organization_id, school_id=payment.school_id
    )
    return await service.cancel_payment(db, payment, current_user.id, payload.reason)


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    student_id: uuid.UUID | None = Query(None),
    payment_status: str | None = Query(None, alias="status"),
) -> list[Payment]:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "payments.read", organization_id=school.organization_id, school_id=school.id)

    stmt = select(Payment).where(Payment.school_id == school_id)
    if student_id is not None:
        stmt = stmt.where(Payment.student_id == student_id)
    if payment_status is not None:
        stmt = stmt.where(Payment.status == payment_status)
    result = await db.execute(stmt.order_by(Payment.created_at.desc()))
    return list(result.scalars().all())


@router.get("/payments/{payment_id}/receipt.pdf")
async def download_receipt(payment_id: uuid.UUID, db: DbSession, current_user: CurrentUser) -> Response:
    payment = await _get_payment_or_404(db, payment_id)
    await ensure_permission(
        db, current_user, "payments.read", organization_id=payment.organization_id, school_id=payment.school_id
    )
    if payment.pdf_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Receipt not available")

    content = await storage.download(payment.pdf_path)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{payment.receipt_number}.pdf"'},
    )


# --- Analytics ---------------------------------------------------------------------
@router.get("/fees/summary", response_model=FeesSummaryOut)
async def get_fees_summary(
    db: DbSession, current_user: CurrentUser, school_id: uuid.UUID = Query(...), academic_year_id: uuid.UUID | None = Query(None)
) -> FeesSummaryOut:
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "fees.read", organization_id=school.organization_id, school_id=school.id)
    return await service.compute_fees_summary(db, school_id, academic_year_id)
