"""Schémas de l'API des abonnements (Phase 29, lot A).

Côté école, le client n'envoie JAMAIS de montant, d'effectif ni de tranche : uniquement la durée
choisie et une clé d'idempotence. Tout est calculé par le serveur (cadrage §5.2, §9).
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.phone import normalize_phone_to_e164
from app.modules.subscriptions.pricing import is_whole_amount

PeriodMonths = Literal[3, 6, 12]
ManualPaymentMethod = Literal["FLOOZ", "TMONEY", "BANK_TRANSFER", "CASH", "OTHER"]
OnlinePaymentNetwork = Literal["FLOOZ", "TMONEY"]
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
    supplement_tier_1: Decimal  # 101 à 250 élèves
    supplement_tier_2: Decimal  # 251 à 500 élèves
    supplement_tier_3: Decimal  # 501 à 750 élèves (501 à 1 000 dans les grilles antérieures au 2026-11-15)
    # 751 à 1 000 élèves : obligatoire pour enregistrer une grille ; absent (None) des grilles
    # antérieures au 2026-11-15, affichées en lecture seule.
    supplement_tier_4: Decimal | None = None
    # Supplément PAR palier de 250 élèves commencé au-delà de 1 000. Facultatif : sans palier, la
    # facture d'une école de plus de 1 000 élèves passe en devis.
    supplement_step: Decimal | None = None

    @field_validator("base_amount")
    @classmethod
    def _base(cls, value: Decimal) -> Decimal:
        return _whole_positive(value, allow_zero=False)

    @field_validator("supplement_tier_1", "supplement_tier_2", "supplement_tier_3")
    @classmethod
    def _supplement(cls, value: Decimal) -> Decimal:
        return _whole_positive(value, allow_zero=True)

    @field_validator("supplement_tier_4", "supplement_step")
    @classmethod
    def _optional_supplement(cls, value: Decimal | None) -> Decimal | None:
        return None if value is None else _whole_positive(value, allow_zero=True)


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
        if any(period.supplement_tier_4 is None for period in self.periods):
            raise ValueError("Le supplément de la tranche 751 à 1 000 élèves est obligatoire pour les trois durées")
        with_step = sum(period.supplement_step is not None for period in self.periods)
        if with_step not in (0, len(self.periods)):
            raise ValueError(
                "Le supplément par palier de 250 élèves au-delà de 1 000 se renseigne pour les trois durées, ou pour aucune"
            )
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


# --- Tarifs publics (page d'accueil, 2026-11-16) ----------------------------------------------
class PublicTierOut(BaseModel):
    tier: int
    min_students: int
    max_students: int


class PublicPricingOut(BaseModel):
    """Montants de la grille ACTIVE et bornes des tranches, sans rien d'autre : ni identifiant, ni
    libellé, ni historique. `periods` est vide sans grille active (la page affiche alors « tarifs
    sur demande »)."""

    currency: str
    tiers: list[PublicTierOut]
    step_students: int
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
    # Lot B — paiement Mobile Money : proposé seulement si le coupe-circuit est actif, et pour un
    # montant inférieur ou égal au plafond (au-delà : paiement manuel par la plateforme).
    online_payment_enabled: bool = False
    online_payment_max_amount: int = 0


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
    # Lot B — 4 derniers chiffres du numéro du payeur (jamais le numéro complet).
    payer_phone_last4: str | None = None


# --- Paiement en ligne (lot B) -----------------------------------------------------------------
def normalize_togo_mobile_number(raw: str) -> str:
    """Numéro togolais valide, ramené à ses 8 chiffres nationaux (format attendu par PayGate d'après
    les intégrations existantes ; à confirmer par le premier paiement réel). Accepte les espaces,
    tirets, l'indicatif +228, 228 ou 00228."""
    e164 = normalize_phone_to_e164(raw, "TG")
    if e164 is None or not e164.startswith("+228") or len(e164) != 12:
        raise ValueError("Numéro de téléphone invalide : indiquez un numéro togolais à 8 chiffres")
    return e164[4:]


class OnlinePaymentInput(BaseModel):
    network: OnlinePaymentNetwork
    phone_number: str = Field(min_length=8, max_length=32)
    idempotency_key: str = Field(min_length=8, max_length=128)

    @field_validator("phone_number")
    @classmethod
    def _phone(cls, value: str) -> str:
        return normalize_togo_mobile_number(value)


class OnlinePaymentOut(BaseModel):
    """État d'une tentative de paiement en ligne, pour l'écran de l'école. Ni identifiant PayGate,
    ni numéro complet, ni code technique du fournisseur."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invoice_id: uuid.UUID
    method: str
    status: str
    amount: Decimal
    currency: str
    payer_phone_last4: str | None
    created_at: datetime
    confirmed_at: datetime | None


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
