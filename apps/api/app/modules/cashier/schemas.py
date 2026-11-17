import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.modules.fees.schemas import PaymentMethod, PaymentStatus, StudentFeeStatus


class CashierStudentOut(BaseModel):
    """Projection MINIMALE d'un élève pour la caisse : de quoi l'identifier au comptoir, rien de
    plus (ni date de naissance, ni tuteurs, ni documents — le CAISSIER n'a pas `students.read`)."""

    id: uuid.UUID
    matricule: str
    first_name: str
    last_name: str
    current_class_name: str | None = None


class CashierPaymentOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    student_matricule: str
    student_first_name: str
    student_last_name: str
    amount: Decimal
    method: PaymentMethod
    paid_at: date
    status: PaymentStatus
    receipt_number: str
    created_at: datetime
    # Phase 32, lot 3 — encaissement fait sans internet (sinon null).
    offline_collected_at: datetime | None = None
    provisional_receipt_number: str | None = None


class CashierDayOut(BaseModel):
    """Journal de caisse d'UNE journée pour l'utilisateur courant (ses propres encaissements)."""

    day: date
    currency: str
    total_completed: Decimal
    payments: list[CashierPaymentOut]


class CashierRosterFeeOut(BaseModel):
    """Frais d'un élève tel que l'écran d'encaissement en a besoin (mêmes champs et même calcul que
    `GET /students/{id}/financial-summary`)."""

    id: uuid.UUID
    fee_schedule_name: str
    amount_due: Decimal
    amount_paid: Decimal
    balance: Decimal
    due_date: date | None
    status: StudentFeeStatus
    created_at: datetime


class CashierRosterStudentOut(CashierStudentOut):
    fees: list[CashierRosterFeeOut]


class CashierOfflineRosterOut(BaseModel):
    """Phase 32, lot 3 — liste gardée sur l'appareil du caissier pour encaisser pendant une coupure :
    élèves ayant encore quelque chose à payer, avec leurs frais. `generated_at` date la liste ;
    `cash_session_id` est la caisse ouverte au moment du téléchargement."""

    school_id: uuid.UUID
    currency: str
    generated_at: datetime
    cash_session_id: uuid.UUID
    truncated: bool
    students: list[CashierRosterStudentOut]
