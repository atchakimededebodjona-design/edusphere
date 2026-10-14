import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.modules.fees.schemas import PaymentMethod, PaymentStatus


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


class CashierDayOut(BaseModel):
    """Journal de caisse d'UNE journée pour l'utilisateur courant (ses propres encaissements)."""

    day: date
    currency: str
    total_completed: Decimal
    payments: list[CashierPaymentOut]
