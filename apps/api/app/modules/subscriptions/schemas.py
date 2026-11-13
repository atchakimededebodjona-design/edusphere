"""Schémas de l'API des abonnements (Phase 29, lot A).

Côté école, le client n'envoie JAMAIS de montant, d'effectif ni de tranche : uniquement la durée
choisie et une clé d'idempotence. Tout est calculé par le serveur (cadrage §5.2, §9).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.subscriptions.pricing import is_whole_amount

PeriodMonths = Literal[3, 6, 12]
ManualPaymentMethod = Literal["FLOOZ", "TMONEY", "BANK_TRANSFER", "CASH", "OTHER"]
SubscriptionStateCode = Literal["NONE", "SCHEDULED", "TRIAL", "ACTIVE", "EXPIRING_SOON", "EXPIRED"]

# Plafond de saisie (bien en dessous de la capacité de Numeric(12, 2)) : protège d'une faute de
# frappe grossière, pas une règle commerciale.
MAX_AMOUNT = Decimal("100000000")


def _whole_positive(value: Decimal, *, allow_zero: bool) -> Decimal:
    if value < 0 or (value == 0 and not allow_zero):
        raise ValueError("Le montant doit être positif" if allow_zero else "Le montant doit être strictement positif")
    if value > MAX_AMOUNT:
        raise ValueError("Montant trop élevé")
    if not is_whole_amount(value):
        raise ValueError("Le montant doit être un nombre entier de FCFA")
    return value.quantize(Decimal("1"))


# --- Grille de prix ----------------------------------------------------------------------------
class GridPeriodPrices(BaseModel):
    period_months: PeriodMonths
    base_amount: Decimal
    supplement_tier_1: Decimal
    supplement_tier_2: Decimal
    supplement_tier_3: Decimal

    @field_validator("base_amount")
    @classmethod
    def _base(cls, value: Decimal) -> Decimal:
        return _whole_positive(value, allow_zero=False)

    @field_validator("supplement_tier_1", "supplement_tier_2", "supplement_tier_3")
    @classmethod
    def _supplement(cls, value: Decimal) -> Decimal:
        return _whole_positive(value, allow_zero=True)


class GridInput(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    periods: list[GridPeriodPrices]

    @field_validator("label")
    @classmethod
    def _label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Le libellé est obligatoire")
        return value

    @model_validator(mode="after")
    def _all_periods_once(self) -> "GridInput":
        months = sorted(period.period_months for period in self.periods)
        if months != [3, 6, 12]:
            raise ValueError("La grille doit définir exactement les durées 3, 6 et 12 mois, une fois chacune")
        return self


class GridOut(BaseModel):
    id: uuid.UUID
    label: str
    currency: str
    status: str
    created_at: datetime
    activated_at: datetime | None
    archived_at: datetime | None
    periods: list[GridPeriodPrices]


# --- État de l'abonnement d'une école ----------------------------------------------------------
class PeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: str
    starts_on: date
    ends_on: date
    invoice_id: uuid.UUID | None


class OfferOut(BaseModel):
    period_months: int
    # None si aucune grille active ou si l'effectif dépasse 1 000 élèves (devis).
    base_amount: Decimal | None
    supplement_amount: Decimal | None
    total_amount: Decimal | None


class InvoiceSummaryOut(BaseModel):
    id: uuid.UUID
    number: str | None
    status: str
    period_months: int
    student_count: int
    tier: int | None
    total_amount: Decimal | None
    currency: str
    issued_at: datetime | None
    expires_at: datetime | None
    paid_at: datetime | None
    created_at: datetime


class SchoolSubscriptionOut(BaseModel):
    school_id: uuid.UUID
    school_name: str
    today: date
    state: SubscriptionStateCode
    current_period: PeriodOut | None
    covered_until: date | None
    next_period_starts_on: date | None
    active_student_count: int
    tier: int | None
    quote_required: bool
    grid_available: bool
    currency: str
    offers: list[OfferOut]
    open_invoice: InvoiceSummaryOut | None
    periods: list[PeriodOut]


# --- Factures ----------------------------------------------------------------------------------
class InvoiceCreate(BaseModel):
    school_id: uuid.UUID
    period_months: PeriodMonths
    idempotency_key: str = Field(min_length=8, max_length=128)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    method: str
    status: str
    amount: Decimal
    currency: str
    reference: str | None
    confirmed_at: datetime | None
    created_at: datetime


class InvoiceOut(InvoiceSummaryOut):
    school_id: uuid.UUID
    organization_id: uuid.UUID
    base_amount: Decimal | None
    supplement_amount: Decimal | None
    grid_id: uuid.UUID | None
    cancelled_at: datetime | None
    cancel_reason: str | None
    payments: list[PaymentOut]
    period: PeriodOut | None


class PlatformInvoiceOut(InvoiceOut):
    school_name: str


class InvoicesPage(BaseModel):
    items: list[PlatformInvoiceOut]
    page: int
    page_size: int
    total: int
    total_pages: int


class QuoteInput(BaseModel):
    total_amount: Decimal

    @field_validator("total_amount")
    @classmethod
    def _amount(cls, value: Decimal) -> Decimal:
        return _whole_positive(value, allow_zero=False)


class CancelInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Le motif est obligatoire")
        return value


class ManualPaymentInput(BaseModel):
    method: ManualPaymentMethod
    amount: Decimal
    reference: str = Field(min_length=1, max_length=255)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("amount")
    @classmethod
    def _amount(cls, value: Decimal) -> Decimal:
        return _whole_positive(value, allow_zero=False)

    @field_validator("reference")
    @classmethod
    def _reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("La référence du paiement est obligatoire")
        return value


# --- Vue plateforme : abonnements par école ----------------------------------------------------
class PlatformSchoolSubscriptionOut(BaseModel):
    school_id: uuid.UUID
    school_name: str
    organization_id: uuid.UUID
    state: SubscriptionStateCode
    current_period_kind: str | None
    covered_until: date | None
    next_period_starts_on: date | None
    has_free_trial: bool
    open_invoice_status: str | None
    active_student_count: int


class PlatformSchoolSubscriptionsPage(BaseModel):
    items: list[PlatformSchoolSubscriptionOut]
    page: int
    page_size: int
    total: int
    total_pages: int
