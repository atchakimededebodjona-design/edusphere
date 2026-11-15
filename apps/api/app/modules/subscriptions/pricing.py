"""Abonnements des écoles (Phase 29, lot A) — règles de calcul PURES, sans base de données.

Tout ce qui est calcul (tranche d'effectif, dates de période, état affiché, date de début d'une
nouvelle période ou du trimestre gratuit) vit ici, isolé de SQLAlchemy et de FastAPI, pour être
testé unitairement sans base (tests/test_subscriptions_pricing.py). Le service
(`subscriptions/service.py`) ne fait qu'appeler ces fonctions avec des données déjà chargées.

Bornes des tranches : grille validée le 2026-11-09, mise en œuvre complète le 2026-11-15, FIXÉES
dans le code. Seuls les MONTANTS sont modifiables, via la grille en base (écran plateforme) — jamais
les bornes, ce qui évite toute grille incohérente (tranches qui se chevauchent ou laissent un trou).

Au-delà de 1 000 élèves actifs : tranche progressive (`STEP_TIER`) — supplément de la tranche
751 à 1 000, plus un supplément par palier de 250 élèves commencé (« +25 000 F par tranche de
250 élèves » sur le trimestre, dans la grille validée). Une grille sans ligne de palier ne chiffre
pas au-delà de 1 000 élèves : la facture passe alors en devis saisi par la plateforme (lot A).
"""

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

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
# base). Tranches 1 à 4 = base + supplément de la tranche. Les grilles enregistrées avant le
# 2026-11-15 n'ont que les tranches 0 à 3 (la tranche 3 couvrait alors 501 à 1 000 élèves).
TIERS: tuple[Tier, ...] = (
    Tier(0, 0, 100),
    Tier(1, 101, 250),
    Tier(2, 251, 500),
    Tier(3, 501, 750),
    Tier(4, 751, 1000),
)
# Lignes obligatoires d'une grille, pour chaque durée.
TIER_NUMBERS: tuple[int, ...] = tuple(tier.number for tier in TIERS)
# Ligne FACULTATIVE d'une grille : supplément par palier de 250 élèves commencé au-delà de 1 000.
STEP_TIER = 5
STEP_STUDENTS = 250
PROGRESSIVE_THRESHOLD = TIERS[-1].max_students


def tier_for_student_count(student_count: int) -> int:
    """Numéro de tranche pour cet effectif : 0 à 4, ou `STEP_TIER` au-delà de 1 000 élèves."""
    if student_count < 0:
        raise ValueError("student_count must be >= 0")
    for tier in TIERS:
        if tier.min_students <= student_count <= tier.max_students:
            return tier.number
    return STEP_TIER


def steps_above_threshold(student_count: int) -> int:
    """Paliers de 250 élèves commencés au-delà de 1 000 : 1 001 à 1 250 → 1, 1 251 à 1 500 → 2…"""
    if student_count <= PROGRESSIVE_THRESHOLD:
        return 0
    return -(-(student_count - PROGRESSIVE_THRESHOLD) // STEP_STUDENTS)


def supplement_for(student_count: int, supplements: Mapping[int, Decimal]) -> Decimal | None:
    """Supplément d'une durée pour cet effectif, d'après les suppléments de la grille pour cette
    durée (`tranche -> supplément`, la clé `STEP_TIER` portant le supplément PAR palier). None si la
    grille n'a pas de prix pour cet effectif : tranche absente (grille antérieure au 2026-11-15) ou,
    au-delà de 1 000 élèves, pas de ligne de palier (la facture passe alors en devis)."""
    tier = tier_for_student_count(student_count)
    if tier != STEP_TIER:
        return supplements.get(tier)
    last_tier, per_step = supplements.get(TIERS[-1].number), supplements.get(STEP_TIER)
    if last_tier is None or per_step is None:
        return None
    return last_tier + steps_above_threshold(student_count) * per_step


def amount_excl_vat(total_incl_vat: Decimal, vat_rate: Decimal | None) -> Decimal:
    """Montant HT d'un total TTC au taux de TVA figé sur la facture, arrondi au franc. Sans taux
    (facture antérieure à la TVA, ou TVA non applicable) : le total est déjà le HT."""
    if not vat_rate:
        return Decimal(total_incl_vat)
    return (Decimal(total_incl_vat) * 100 / (100 + Decimal(vat_rate))).quantize(Decimal("1"), rounding=ROUND_HALF_UP)


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


# --- Rappels (Phase 29, lot C) -------------------------------------------------------------------
# Paliers de rappel de fin de couverture (cadrage §5.7) : J-30, J-7, puis J0 à l'échéance. Un seul
# palier — le plus avancé applicable — est envoyé à chaque passage : si la tâche n'a pas tourné
# pendant plusieurs jours, l'école ne reçoit pas un J-30 périmé juste avant un J-7.
REMINDER_STAGE_J30 = "J30"
REMINDER_STAGE_J7 = "J7"
REMINDER_STAGE_J0 = "J0"
REMINDER_STAGE_INVOICE_J3 = "INVOICE_J3"
REMINDER_STAGES: tuple[str, ...] = (REMINDER_STAGE_J30, REMINDER_STAGE_J7, REMINDER_STAGE_J0, REMINDER_STAGE_INVOICE_J3)
# Au-delà de 7 jours après la fin de couverture, plus aucun rappel « J0 » n'est créé : évite, au
# premier déploiement, de notifier des échéances anciennes.
EXPIRED_REMINDER_WINDOW_DAYS = 7
# Rappel d'une facture émise et non payée, 3 jours avant la fin de sa validité.
INVOICE_REMINDER_DAYS = 3


def coverage_reminder_stage(days_left: int) -> str | None:
    """Palier de rappel selon le nombre de jours restant avant la fin de couverture (négatif une
    fois la couverture terminée)."""
    if days_left < -EXPIRED_REMINDER_WINDOW_DAYS:
        return None
    if days_left <= 0:
        return REMINDER_STAGE_J0
    if days_left <= 7:
        return REMINDER_STAGE_J7
    if days_left <= EXPIRING_SOON_DAYS:
        return REMINDER_STAGE_J30
    return None
