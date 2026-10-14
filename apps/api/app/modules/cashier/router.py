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

Isolation : l'école est chargée sous le contexte RLS de l'appelant (404 pour une autre
organisation, même convention que le reste de l'API), puis la permission est vérifiée pour CETTE
école (`ensure_permission`, règle de portée unique) — 403 pour une autre école de la même
organisation. Toutes les requêtes filtrent explicitement sur `school_id`.

L'encaissement lui-même reste `POST /payments` (fees/router.py) : aucune logique de paiement ici.
"""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import CurrentUser, DbSession, ensure_permission
from app.modules.academics.models import AcademicYear, SchoolClass
from app.modules.cashier.schemas import CashierDayOut, CashierPaymentOut, CashierStudentOut
from app.modules.fees.models import Payment
from app.modules.schools.models import School
from app.modules.students.models import Student, StudentEnrollment

router = APIRouter()

SEARCH_MIN_LENGTH = 2
SEARCH_DEFAULT_LIMIT = 20
SEARCH_MAX_LIMIT = 50
DAY_MAX_PAYMENTS = 500


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
    target_day = day or date.today()

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
            }
        )
        for payment, matricule, first_name, last_name in result.all()
    ]
    total = sum((p.amount for p in payments if p.status == "COMPLETED"), start=Decimal("0"))
    return CashierDayOut(day=target_day, currency=school.currency, total_completed=total, payments=payments)
