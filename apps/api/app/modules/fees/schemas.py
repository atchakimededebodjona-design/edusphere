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


# --- Sprint 1.4 — vue opérationnelle des frais en retard (lecture seule) ----------------------

# Concepts de portée dérivés uniquement des données déjà écrites par les Sprints 1.2/1.3/1.6,
# jamais d'un nouveau canal : IN_APP_SENT <=> une ligne `notifications` (type FEE_OVERDUE, ce
# student_fee_id) référence le `user_id` de ce tuteur. Le canal email (Sprint 1.6) reflète
# désormais `FeeOverdueEmailReminder.transport_status` au lieu de la simple existence de la ligne
# (`EMAIL_SENT` avant Sprint 1.6) — jamais "delivered"/"reçu"/"envoyé" seul, le transport SMTP
# accepté n'est pas une preuve de remise réelle :
#   EMAIL_ATTEMPTED           <=> transport_status == "ATTEMPTED" (tentative enregistrée, résultat
#                                  pas encore connu — inclut les lignes créées avant ce sprint)
#   EMAIL_TRANSPORT_ACCEPTED  <=> transport_status == "TRANSPORT_ACCEPTED"
#   EMAIL_TRANSPORT_FAILED    <=> transport_status == "TRANSPORT_FAILED"
# Une liste plutôt qu'un scalaire unique : un même tuteur peut légitimement cumuler IN_APP_SENT et
# UN statut email au fil du temps (ex. rappelé par email avant de créer un compte, puis notifié
# in-app pour ce même frais toujours impayé lors d'une exécution ultérieure du job) — voir
# PHASE_14_DISCOVERY_REPORT §5. Jamais plusieurs statuts email à la fois pour un même tuteur/frais
# (une seule ligne `fee_overdue_email_reminders`, contrainte unique). ["NO_CHANNEL"] seul si ni
# in-app ni email n'a jamais été tenté.
OverdueContactChannel = Literal[
    "IN_APP_SENT", "EMAIL_ATTEMPTED", "EMAIL_TRANSPORT_ACCEPTED", "EMAIL_TRANSPORT_FAILED", "NO_CHANNEL"
]


class OverdueFeeGuardianContact(BaseModel):
    guardian_id: uuid.UUID
    full_name: str
    has_user_account: bool
    email: str | None
    statuses: list[OverdueContactChannel]


class OverdueFeeItem(BaseModel):
    student_fee_id: uuid.UUID
    student_id: uuid.UUID
    student_matricule: str
    student_first_name: str
    student_last_name: str
    fee_schedule_name: str
    amount_due: Decimal
    remaining_balance: Decimal
    due_date: date
    overdue_days: int
    currency: str
    guardians: list[OverdueFeeGuardianContact]


class OverdueFeesOut(BaseModel):
    items: list[OverdueFeeItem]
    page: int
    page_size: int
    total: int
    total_pages: int
