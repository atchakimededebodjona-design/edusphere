"""Caisse scolaire, lot 2 — endpoints dédiés au poste de caisse (`/cashier/*`).

Le CAISSIER (lot 1, migration 0025) détient `fees.read`, `payments.read`, `payments.manage` mais
volontairement PAS `students.read` : `GET /students` (dossier élève complet) lui reste fermé. Ce
module expose uniquement ce dont le comptoir a besoin, sans élargir ses permissions :

- `GET /cashier/students/search` : retrouver un élève par matricule/prénom/nom pour encaisser.
  Projection minimale (id, matricule, prénom, nom, classe), recherche obligatoire (>= 2 caractères),
  résultats plafonnés — jamais une liste complète des élèves. Exige `fees.read` ET
  `payments.manage` dans l'école (l'autorisation d'encaisser) : un PLATFORM_SUPPORT (lecture seule),
  un enseignant ou un parent n'y ont pas accès.
- `GET /cashier/payments` : journal de caisse du jour de l'utilisateur courant (ses propres
  encaissements uniquement, `recorded_by`), avec la devise de l'école. Exige `payments.read`.
- `GET /cashier/offline-roster` (Phase 32, lot 3) : liste gardée sur l'appareil pour encaisser pendant
  une coupure — exception voulue et bornée, voir l'endpoint.

Isolation : l'école est chargée sous le contexte RLS de l'appelant (404 pour une autre
organisation, même convention que le reste de l'API), puis la permission est vérifiée pour CETTE
école (`ensure_permission`, règle de portée unique) — 403 pour une autre école de la même
organisation. Toutes les requêtes filtrent explicitement sur `school_id`.

L'encaissement lui-même reste `POST /payments` (fees/router.py) : aucune logique de paiement ici.
"""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.modules.academics.models import AcademicYear, SchoolClass
from app.modules.cash.service import get_open_session, school_today
from app.modules.cashier.schemas import (
    CashierDayOut,
    CashierOfflineRosterOut,
    CashierPaymentOut,
    CashierRosterFeeOut,
    CashierRosterStudentOut,
    CashierStudentOut,
)
from app.modules.fees.models import FeeSchedule, Payment, PaymentAllocation, StudentFee
from app.modules.schools.models import School
from app.modules.students.models import Student, StudentEnrollment

router = APIRouter()

SEARCH_MIN_LENGTH = 2
SEARCH_DEFAULT_LIMIT = 20
SEARCH_MAX_LIMIT = 50
DAY_MAX_PAYMENTS = 500
# Phase 32, lot 3 — borne de la liste gardée sur l'appareil (au-delà : `truncated`, la recherche en
# ligne reste complète).
ROSTER_MAX_STUDENTS = 5000


async def _get_school_or_404(db: AsyncSession, school_id: uuid.UUID) -> School:
    school = await db.get(School, school_id)
    if school is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="School not found")
    return school


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def _current_class_names(db: AsyncSession, student_ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
    """Classe de l'inscription ACTIVE de chaque élève, en une seule requête : l'année marquée
    courante d'abord, sinon la plus récente."""
    if not student_ids:
        return {}
    rows = await db.execute(
        select(StudentEnrollment.student_id, SchoolClass.name)
        .join(SchoolClass, SchoolClass.id == StudentEnrollment.class_id)
        .join(AcademicYear, AcademicYear.id == StudentEnrollment.academic_year_id)
        .where(StudentEnrollment.student_id.in_(student_ids), StudentEnrollment.status == "ACTIVE")
        .order_by(AcademicYear.is_current.desc(), AcademicYear.start_date.desc())
    )
    names: dict[uuid.UUID, str] = {}
    for student_id, class_name in rows.all():
        names.setdefault(student_id, class_name)
    return names


@router.get("/cashier/students/search", response_model=list[CashierStudentOut])
async def search_students_for_cashier(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    search: str = Query(..., min_length=SEARCH_MIN_LENGTH, max_length=100),
    limit: int = Query(SEARCH_DEFAULT_LIMIT, ge=1, le=SEARCH_MAX_LIMIT),
) -> list[CashierStudentOut]:
    term = search.strip()
    if len(term) < SEARCH_MIN_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Search must contain at least {SEARCH_MIN_LENGTH} characters",
        )
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "fees.read", organization_id=school.organization_id, school_id=school.id)
    await ensure_permission(db, current_user, "payments.manage", organization_id=school.organization_id, school_id=school.id)

    pattern = f"%{_escape_like(term)}%"
    result = await db.execute(
        select(Student.id, Student.matricule, Student.first_name, Student.last_name)
        .where(
            Student.school_id == school.id,
            or_(
                Student.matricule.ilike(pattern, escape="\\"),
                Student.first_name.ilike(pattern, escape="\\"),
                Student.last_name.ilike(pattern, escape="\\"),
            ),
        )
        .order_by(Student.last_name, Student.first_name, Student.matricule)
        .limit(limit)
    )
    rows = result.all()
    class_names = await _current_class_names(db, [row.id for row in rows])
    return [
        CashierStudentOut(
            id=row.id,
            matricule=row.matricule,
            first_name=row.first_name,
            last_name=row.last_name,
            current_class_name=class_names.get(row.id),
        )
        for row in rows
    ]


@router.get("/cashier/payments", response_model=CashierDayOut)
async def list_my_cashier_payments(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
    day: date | None = Query(None),
) -> CashierDayOut:
    """Encaissements de l'utilisateur courant pour `day` (date de paiement, aujourd'hui par défaut)
    dans cette école. Jamais les opérations d'un autre utilisateur : la vue générale reste
    `GET /payments` (inchangé), réservée aux mêmes détenteurs de `payments.read`."""
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "payments.read", organization_id=school.organization_id, school_id=school.id)
    # Lot 3 — journée métier dans le fuseau de l'école, jamais celui du serveur.
    target_day = day or school_today(school)

    result = await db.execute(
        select(Payment, Student.matricule, Student.first_name, Student.last_name)
        .join(Student, Student.id == Payment.student_id)
        .where(
            Payment.school_id == school.id,
            Payment.recorded_by == current_user.id,
            Payment.paid_at == target_day,
        )
        .order_by(Payment.created_at.desc())
        .limit(DAY_MAX_PAYMENTS)
    )
    payments = [
        CashierPaymentOut.model_validate(
            {
                "id": payment.id,
                "student_id": payment.student_id,
                "student_matricule": matricule,
                "student_first_name": first_name,
                "student_last_name": last_name,
                "amount": payment.amount,
                "method": payment.method,
                "paid_at": payment.paid_at,
                "status": payment.status,
                "receipt_number": payment.receipt_number,
                "created_at": payment.created_at,
                "offline_collected_at": payment.offline_collected_at,
                "provisional_receipt_number": payment.provisional_receipt_number,
            }
        )
        for payment, matricule, first_name, last_name in result.all()
    ]
    total = sum((p.amount for p in payments if p.status == "COMPLETED"), start=Decimal("0"))
    return CashierDayOut(day=target_day, currency=school.currency, total_completed=total, payments=payments)


@router.get("/cashier/offline-roster", response_model=CashierOfflineRosterOut)
async def get_offline_roster(
    db: DbSession,
    current_user: CurrentUser,
    school_id: uuid.UUID = Query(...),
) -> CashierOfflineRosterOut:
    """Phase 32, lot 3 — liste gardée sur l'appareil du caissier pour encaisser pendant une coupure.

    EXCEPTION VOULUE à la règle « jamais une liste complète des élèves » de ce module (décision de
    l'école du 2026-11-17) : sans elle, rien ne peut être encaissé au début d'une coupure. Bornée :
    - mêmes permissions que la recherche (`fees.read` ET `payments.manage` dans CETTE école) ;
    - seulement avec une caisse OUVERTE par l'appelant dans cette école (409 sinon) : un compte qui
      n'encaisse pas n'a pas cette liste ;
    - projection minimale (matricule, nom, classe) et seulement les élèves qui ont encore quelque chose
      à payer, avec leurs frais (même calcul que `GET /students/{id}/financial-summary`) ;
    - côté appareil, rangée par compte et effacée à la déconnexion (lib/offline/responseCache.ts).
    Chaque encaissement fait hors connexion est revérifié par `POST /payments` à son envoi.
    """
    school = await _get_school_or_404(db, school_id)
    await ensure_permission(db, current_user, "fees.read", organization_id=school.organization_id, school_id=school.id)
    await ensure_permission(db, current_user, "payments.manage", organization_id=school.organization_id, school_id=school.id)
    session = await get_open_session(db, school.id, current_user.id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An open cash session is required to prepare offline collection",
        )

    paid = (
        select(PaymentAllocation.student_fee_id.label("fee_id"), func.sum(PaymentAllocation.amount).label("paid"))
        .join(Payment, Payment.id == PaymentAllocation.payment_id)
        .where(PaymentAllocation.school_id == school.id, Payment.status == "COMPLETED")
        .group_by(PaymentAllocation.student_fee_id)
        .subquery("paid_by_fee")
    )
    fee_rows = await db.execute(
        select(StudentFee, FeeSchedule.name, func.coalesce(paid.c.paid, 0))
        .join(FeeSchedule, FeeSchedule.id == StudentFee.fee_schedule_id)
        .outerjoin(paid, paid.c.fee_id == StudentFee.id)
        .where(StudentFee.school_id == school.id, StudentFee.status != "CANCELLED")
        .order_by(StudentFee.due_date.asc().nulls_last(), StudentFee.created_at)
    )
    fees_by_student: dict[uuid.UUID, list[CashierRosterFeeOut]] = {}
    for student_fee, schedule_name, paid_amount in fee_rows.all():
        amount_paid = Decimal(str(paid_amount))
        fees_by_student.setdefault(student_fee.student_id, []).append(
            CashierRosterFeeOut(
                id=student_fee.id,
                fee_schedule_name=schedule_name,
                amount_due=student_fee.amount_due,
                amount_paid=amount_paid,
                balance=student_fee.amount_due - amount_paid,
                due_date=student_fee.due_date,
                status=student_fee.status,
                created_at=student_fee.created_at,
            )
        )
    owing = {student_id for student_id, fees in fees_by_student.items() if any(fee.balance > 0 for fee in fees)}

    student_rows = await db.execute(
        select(Student.id, Student.matricule, Student.first_name, Student.last_name)
        .where(Student.school_id == school.id)
        .order_by(Student.last_name, Student.first_name, Student.matricule)
    )
    selected = [row for row in student_rows.all() if row.id in owing]
    truncated = len(selected) > ROSTER_MAX_STUDENTS
    selected = selected[:ROSTER_MAX_STUDENTS]
    class_names = await _current_class_names(db, [row.id for row in selected])
    return CashierOfflineRosterOut(
        school_id=school.id,
        currency=school.currency,
        generated_at=datetime.now(timezone.utc),
        cash_session_id=session.id,
        truncated=truncated,
        students=[
            CashierRosterStudentOut(
                id=row.id,
                matricule=row.matricule,
                first_name=row.first_name,
                last_name=row.last_name,
                current_class_name=class_names.get(row.id),
                fees=fees_by_student[row.id],
            )
            for row in selected
        ],
    )
