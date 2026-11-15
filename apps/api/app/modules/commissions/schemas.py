"""Schémas de l'API des commissions des partenaires (migration 0031)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

CommissionStatus = Literal["DUE", "PAID", "CANCELLED"]
SettlementMethod = Literal["MOBILE_MONEY", "BANK_TRANSFER", "CASH", "OTHER"]


class CommissionOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    partner_name: str
    school_id: uuid.UUID
    school_name: str
    invoice_id: uuid.UUID
    invoice_number: str | None
    period_months: int
    base_amount_excl_vat: Decimal
    rate: Decimal
    amount: Decimal
    currency: str
    status: CommissionStatus
    created_at: datetime
    paid_at: datetime | None
    settlement_method: str | None
    settlement_reference: str | None
    cancelled_at: datetime | None
    cancel_reason: str | None


class CommissionTotals(BaseModel):
    due_amount: Decimal
    due_count: int
    paid_amount: Decimal
    paid_count: int


class CommissionsPage(BaseModel):
    items: list[CommissionOut]
    page: int
    page_size: int
    total: int
    total_pages: int
    totals: CommissionTotals


class PartnerCommissionsOut(BaseModel):
    commission_rate: Decimal
    totals: CommissionTotals
    items: list[CommissionOut]


class MarkPaidInput(BaseModel):
    """Versement manuel effectué par la plateforme (Mobile Money, virement…), pour UN partenaire."""

    commission_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    method: SettlementMethod
    reference: str = Field(min_length=1, max_length=255)

    @field_validator("commission_ids")
    @classmethod
    def _unique(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        if len(set(value)) != len(value):
            raise ValueError("Chaque commission ne peut figurer qu'une fois")
        return value

    @field_validator("reference")
    @classmethod
    def _reference(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("La référence du versement est obligatoire")
        return value


class CancelCommissionInput(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Le motif est obligatoire")
        return value


class CommissionRateInput(BaseModel):
    rate: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
