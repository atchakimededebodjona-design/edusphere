import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.fees.schemas import PaymentMethod, PaymentStatus

CashSessionStatus = Literal["OPEN", "CLOSED"]
CashMovementType = Literal["CASH_IN", "CASH_OUT", "BANK_DEPOSIT", "OTHER"]
CashMovementDirection = Literal["IN", "OUT"]
CashVarianceReason = Literal[
    "COUNTING_ERROR", "CHANGE_ERROR", "UNRECORDED_PAYMENT", "UNRECORDED_MOVEMENT", "LOSS_OR_THEFT", "OTHER"
]

# Montants : 2 décimales maximum (max_digits=12, decimal_places=2), comme Numeric(12, 2) en base —
# jamais d'arrondi silencieux d'un montant saisi.


# --- Entrées ------------------------------------------------------------------------------------
class CashSessionOpen(BaseModel):
    school_id: uuid.UUID
    opening_amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class CashMovementCreate(BaseModel):
    type: CashMovementType
    # Obligatoire pour OTHER uniquement ; ignorée sinon (direction fixée par le type).
    direction: CashMovementDirection | None = None
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)
    reference: str | None = Field(default=None, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def _direction_rules(self) -> "CashMovementCreate":
        if not self.reason.strip():
            raise ValueError("reason must not be blank")
        if self.type == "OTHER" and self.direction is None:
            raise ValueError("direction is required for OTHER movements")
        return self


class CashCountLineIn(BaseModel):
    denomination: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    quantity: int = Field(ge=0, le=1_000_000)


class CashCountCreate(BaseModel):
    lines: list[CashCountLineIn] = Field(min_length=1, max_length=50)


class CashSessionClose(BaseModel):
    # Comptage et solde théorique sur lesquels l'utilisateur s'appuie : refus (409) si l'un des deux
    # a changé entre l'affichage et la clôture (nouveau paiement, nouveau comptage...).
    count_id: uuid.UUID
    expected_amount: Decimal = Field(max_digits=12, decimal_places=2)
    variance_reason: CashVarianceReason | None = None
    variance_note: str | None = Field(default=None, max_length=2000)


# --- Sorties ------------------------------------------------------------------------------------
class CashTotalsOut(BaseModel):
    opening_amount: Decimal
    cash_payments_total: Decimal
    cash_payments_count: int
    movements_in_total: Decimal
    movements_out_total: Decimal
    expected_amount: Decimal


class CashSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    school_id: uuid.UUID
    cashier_user_id: uuid.UUID
    cashier_name: str | None = None
    opened_at: datetime
    opened_by: uuid.UUID
    opening_amount: Decimal
    status: CashSessionStatus
    closed_at: datetime | None
    closed_by: uuid.UUID | None
    expected_amount: Decimal | None
    counted_amount: Decimal | None
    variance_amount: Decimal | None
    variance_reason: str | None
    variance_note: str | None
    business_date: date


class CashSessionSummaryOut(CashSessionOut):
    """Ligne de supervision : session + agrégats SQL (théorique figé à la clôture, live sinon)."""

    cash_payments_total: Decimal
    cash_payments_count: int
    movements_in_total: Decimal
    movements_out_total: Decimal
    current_expected_amount: Decimal


class CashMovementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    cash_session_id: uuid.UUID
    type: CashMovementType
    direction: CashMovementDirection
    amount: Decimal
    reason: str
    reference: str | None
    created_by: uuid.UUID
    created_at: datetime


class CashCountLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    denomination: Decimal
    quantity: int
    line_total: Decimal


class CashCountOut(BaseModel):
    id: uuid.UUID
    cash_session_id: uuid.UUID
    counted_by: uuid.UUID
    counted_at: datetime
    total_amount: Decimal
    lines: list[CashCountLineOut]


class CashSessionPaymentOut(BaseModel):
    id: uuid.UUID
    receipt_number: str
    amount: Decimal
    method: PaymentMethod
    status: PaymentStatus
    paid_at: date
    created_at: datetime
    student_id: uuid.UUID
    student_matricule: str
    student_first_name: str
    student_last_name: str


class CashSessionDetailOut(BaseModel):
    session: CashSessionOut
    totals: CashTotalsOut
    payments: list[CashSessionPaymentOut]
    movements: list[CashMovementOut]
    latest_count: CashCountOut | None
    currency: str


class CashRegisterContextOut(BaseModel):
    """État de "ma caisse" pour une école : session OPEN courante (ou aucune) + référentiels."""

    school_id: uuid.UUID
    currency: str
    timezone: str
    business_date: date
    denominations: list[Decimal]
    variance_reasons: list[str]
    current: CashSessionDetailOut | None


# --- Rapports -----------------------------------------------------------------------------------
class CashSessionsAggregateOut(BaseModel):
    sessions_count: int
    open_count: int
    closed_count: int
    opening_total: Decimal
    cash_payments_total: Decimal
    movements_in_total: Decimal
    movements_out_total: Decimal
    expected_total: Decimal
    counted_total: Decimal
    variance_total: Decimal


class PaymentMethodTotalOut(BaseModel):
    method: PaymentMethod
    completed_count: int
    completed_total: Decimal
    cancelled_count: int
    cancelled_total: Decimal


class CashDailyReportOut(BaseModel):
    day: date
    currency: str
    timezone: str
    sessions: CashSessionsAggregateOut
    payments_by_method: list[PaymentMethodTotalOut]


class CashierReportRowOut(BaseModel):
    cashier_user_id: uuid.UUID
    cashier_name: str | None
    sessions_count: int
    open_count: int
    cash_payments_total: Decimal
    cash_payments_count: int
    movements_in_total: Decimal
    movements_out_total: Decimal
    variance_total: Decimal


class CashierReportOut(BaseModel):
    date_from: date
    date_to: date
    currency: str
    rows: list[CashierReportRowOut]


class PaymentMethodReportOut(BaseModel):
    date_from: date
    date_to: date
    currency: str
    rows: list[PaymentMethodTotalOut]
