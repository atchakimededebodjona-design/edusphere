import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

PaymentMethod = Literal["CASH", "BANK_TRANSFER", "CHEQUE", "AGENT_DEPOSIT", "OTHER"]
StudentFeeStatus = Literal["PENDING", "PARTIALLY_PAID", "PAID", "CANCELLED"]
PaymentStatus = Literal["COMPLETED", "CANCELLED"]
FeeScopeType = Literal["SCHOOL", "CLASS", "LEVEL"]


class FeeCategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    name: str
    created_at: datetime
    updated_at: datetime


class FeeCategoryCreate(BaseModel):
    school_id: uuid.UUID
    name: str = Field(min_length=1, max_length=128)


class FeeScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    fee_category_id: uuid.UUID
    academic_year_id: uuid.UUID
    name: str
    amount: Decimal
    currency: str
    scope_type: FeeScopeType
    scope_class_id: uuid.UUID | None
    scope_education_level_id: uuid.UUID | None
    is_optional: bool
    due_date: date | None
    created_at: datetime
    updated_at: datetime


class FeeScheduleCreate(BaseModel):
    school_id: uuid.UUID
    fee_category_id: uuid.UUID
    academic_year_id: uuid.UUID
    name: str = Field(min_length=1, max_length=128)
    amount: Decimal = Field(gt=0)
    scope_type: FeeScopeType
    scope_class_id: uuid.UUID | None = None
    scope_education_level_id: uuid.UUID | None = None
    is_optional: bool = False
    due_date: date | None = None


class FeeScheduleGenerateResult(BaseModel):
    created_count: int
    skipped_existing_count: int


class StudentFeeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    fee_schedule_id: uuid.UUID
    amount_due: Decimal
    due_date: date | None
    status: StudentFeeStatus
    note: str | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class StudentFeeBalanceOut(StudentFeeOut):
    fee_schedule_name: str
    amount_paid: Decimal
    balance: Decimal


class StudentFeeUpdate(BaseModel):
    amount_due: Decimal | None = Field(default=None, gt=0)
    due_date: date | None = None
    # Phase 20 : obligatoire dès que `amount_due` est fourni (validé dans le router, pas ici, pour
    # rester cohérent avec la convention déjà utilisée par ce module — validations croisées faites
    # explicitement dans le handler plutôt que via un validator Pydantic dédié).
    note: str | None = Field(default=None, max_length=2000)


class FinancialSummaryOut(BaseModel):
    student_id: uuid.UUID
    total_due: Decimal
    total_paid: Decimal
    balance: Decimal
    fees: list[StudentFeeBalanceOut]


class PaymentAllocationIn(BaseModel):
    student_fee_id: uuid.UUID
    amount: Decimal = Field(gt=0)


class PaymentCreate(BaseModel):
    student_id: uuid.UUID
    amount: Decimal = Field(gt=0)
    method: PaymentMethod
    paid_at: date
    reference: str | None = Field(default=None, max_length=255)
    payer_name: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=2000)
    # Généré côté client (ex. UUID créé à l'ouverture du formulaire, réutilisé tel quel en cas
    # de nouvelle tentative) — protection contre le double-clic, voir fees/models.py::Payment.
    idempotency_key: str = Field(min_length=8, max_length=128)
    allocations: list[PaymentAllocationIn] = Field(min_length=1)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    student_id: uuid.UUID
    amount: Decimal
    method: PaymentMethod
    paid_at: date
    reference: str | None
    payer_name: str | None
    note: str | None
    status: PaymentStatus
    receipt_number: str
    cancelled_at: datetime | None
    cancellation_reason: str | None
    created_at: datetime


class PaymentCancelRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class FeesSummaryOut(BaseModel):
    total_due: Decimal
    total_paid: Decimal
    balance: Decimal
    overdue_count: int
