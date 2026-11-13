"""Abonnements des écoles (Phase 29, lot A) — règles de calcul PURES, sans base de données.

Tout ce qui est calcul (tranche d'effectif, dates de période, état affiché, date de début d'une
nouvelle période ou du trimestre gratuit) vit ici, isolé de SQLAlchemy et de FastAPI, pour être
testé unitairement sans base (tests/test_subscriptions_pricing.py). Le service
(`subscriptions/service.py`) ne fait qu'appeler ces fonctions avec des données déjà chargées.

Bornes des tranches : décision du 2026-11-09 (cadrage Phase 29, §2), FIXÉES dans le code. Seuls
les MONTANTS sont modifiables, via la grille en base (écran plateforme) — jamais les bornes, ce qui
évite toute grille incohérente (tranches qui se chevauchent ou laissent un trou). Au-delà de
1 000 élèves actifs : « tarif adapté », c'est-à-dire un devis saisi par la plateforme.
"""

import calendar
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

PERIOD_MONTHS: tuple[int, ...] = (3, 6, 12)
FREE_QUARTER_MONTHS = 3
EXPIRING_SOON_DAYS = 30

PERIOD_KIND_FREE_TRIAL = "FREE_TRIAL"
PERIOD_KIND_PAID = "PAID"

STATE_NONE = "NONE"
STATE_SCHEDULED = "SCHEDULED"
STATE_TRIAL = "TRIAL"
STATE_ACTIVE = "ACTIVE"
STATE_EXPIRING_SOON = "EXPIRING_SOON"
STATE_EXPIRED = "EXPIRED"


@dataclass(frozen=True)
class Tier:
    number: int
    min_students: int
    max_students: int


# Tranche 0 = forfait de base seul (0 à 100 élèves : une école sans élève actif paie le forfait de
# base). Tranches 1 à 3 = base + supplément de la tranche.
TIERS: tuple[Tier, ...] = (
    Tier(0, 0, 100),
    Tier(1, 101, 250),
    Tier(2, 251, 500),
    Tier(3, 501, 1000),
)
TIER_NUMBERS: tuple[int, ...] = tuple(tier.number for tier in TIERS)
QUOTE_THRESHOLD = TIERS[-1].max_students


def tier_for_student_count(student_count: int) -> int | None:
    """Numéro de tranche pour cet effectif, ou `None` au-delà de 1 000 élèves (devis)."""
    if student_count < 0:
        raise ValueError("student_count must be >= 0")
    for tier in TIERS:
        if tier.min_students <= student_count <= tier.max_students:
            return tier.number
    return None


def is_whole_amount(amount: Decimal) -> bool:
    """Le XOF n'a pas de centimes et PayGate ne traite que des FCFA entiers."""
    return amount == amount.to_integral_value()


def add_months(start: date, months: int) -> date:
    """`start` + `months` mois calendaires. Si le jour n'existe pas dans le mois d'arrivée, on prend
    le dernier jour de ce mois (31 janvier + 1 mois = 28 ou 29 février)."""
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def period_end(start: date, months: int) -> date:
    """Dernier jour INCLUS d'une période de `months` mois commençant le `start` : début + N mois − 1
    jour. La période suivante commence donc toujours exactement le lendemain (aucun trou, aucun
    chevauchement), même en fin de mois."""
    return add_months(start, months) - timedelta(days=1)


def format_invoice_number(year: int, sequence: int) -> str:
    return f"EL-{year}-{sequence:06d}"


@dataclass(frozen=True)
class PeriodSpan:
    kind: str
    starts_on: date
    ends_on: date


@dataclass(frozen=True)
class SubscriptionState:
    state: str
    current: PeriodSpan | None
    # Dernier jour couvert sans interruption à partir de la période en cours (ou de la prochaine
    # période programmée) ; pour une école expirée, dernier jour de sa dernière période.
    covered_until: date | None
    next_starts_on: date | None


def _chain_end(ordered: list[PeriodSpan], first: PeriodSpan) -> date:
    """Fin de la suite de périodes CONTIGUËS qui commence par `first`."""
    end = first.ends_on
    extended = True
    while extended:
        extended = False
        for period in ordered:
            if period.starts_on == end + timedelta(days=1):
                end = period.ends_on
                extended = True
    return end


def compute_state(periods: Iterable[PeriodSpan], today: date) -> SubscriptionState:
    """État AFFICHÉ, calculé à la lecture (aucune colonne de statut stockée). Ne bloque jamais rien :
    décision « rappels seulement » du 2026-11-12."""
    ordered = sorted(periods, key=lambda period: period.starts_on)
    if not ordered:
        return SubscriptionState(STATE_NONE, None, None, None)

    current = next((p for p in ordered if p.starts_on <= today <= p.ends_on), None)
    if current is None:
        upcoming = [p for p in ordered if p.starts_on > today]
        if upcoming:
            first = upcoming[0]
            return SubscriptionState(STATE_SCHEDULED, None, _chain_end(ordered, first), first.starts_on)
        return SubscriptionState(STATE_EXPIRED, None, max(p.ends_on for p in ordered), None)

    covered_until = _chain_end(ordered, current)
    later = [p for p in ordered if p.starts_on > covered_until]
    next_starts_on = later[0].starts_on if later else None
    if (covered_until - today).days <= EXPIRING_SOON_DAYS:
        state = STATE_EXPIRING_SOON
    elif current.kind == PERIOD_KIND_FREE_TRIAL:
        state = STATE_TRIAL
    else:
        state = STATE_ACTIVE
    return SubscriptionState(state, current, covered_until, next_starts_on)


def next_period_start(periods: Iterable[PeriodSpan], today: date) -> date:
    """Début d'une nouvelle période payée : aujourd'hui si rien n'est couvert à partir d'aujourd'hui,
    sinon le lendemain de la dernière période existante (renouvellement anticipé sans perte, et
    jamais de chevauchement avec un trimestre gratuit programmé)."""
    ends = [period.ends_on for period in periods]
    latest_end = max(ends) if ends else None
    if latest_end is not None and latest_end >= today:
        return latest_end + timedelta(days=1)
    return today


def free_quarter_start(launch_date: date, created_on: date, periods: Iterable[PeriodSpan]) -> date:
    """Début du trimestre gratuit : la plus tardive de la date de lancement et de la date de
    création de l'école (une école ancienne ne perd pas son trimestre du seul fait de son
    ancienneté). Cas limite : si des périodes payées existent déjà au-delà de cette date (paiement
    enregistré avant l'attribution), le trimestre gratuit commence le lendemain de la dernière,
    pour ne jamais les chevaucher."""
    start = max(launch_date, created_on)
    ends = [period.ends_on for period in periods]
    if ends and max(ends) >= start:
        start = max(ends) + timedelta(days=1)
    return start
