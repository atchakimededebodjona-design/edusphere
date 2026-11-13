"""Phase 29, lot A — règles de calcul PURES des abonnements (subscriptions/pricing.py).

Aucune base de données, aucun client HTTP : ces fonctions ne dépendent que de la bibliothèque
standard. Volontairement écrites sans `pytest.mark.parametrize` (boucles explicites) pour pouvoir
aussi être exécutées hors pytest, comme simple vérification locale.
"""

from datetime import date
from decimal import Decimal

from app.modules.subscriptions import pricing
from app.modules.subscriptions.pricing import PeriodSpan


def test_tier_boundaries_follow_the_november_9_grid() -> None:
    expected = {
        0: 0,
        1: 0,
        100: 0,
        101: 1,
        250: 1,
        251: 2,
        500: 2,
        501: 3,
        1000: 3,
        1001: None,
        5000: None,
    }
    for count, tier in expected.items():
        assert pricing.tier_for_student_count(count) == tier, count


def test_negative_student_count_is_rejected() -> None:
    try:
        pricing.tier_for_student_count(-1)
    except ValueError:
        return
    raise AssertionError("ValueError attendue")


def test_amounts_must_be_whole_fcfa() -> None:
    assert pricing.is_whole_amount(Decimal("30000"))
    assert pricing.is_whole_amount(Decimal("30000.00"))
    assert not pricing.is_whole_amount(Decimal("30000.50"))


def test_period_end_is_start_plus_months_minus_one_day() -> None:
    cases = [
        (date(2027, 1, 1), 3, date(2027, 3, 31)),
        (date(2027, 1, 1), 6, date(2027, 6, 30)),
        (date(2027, 1, 1), 12, date(2027, 12, 31)),
        (date(2027, 1, 15), 3, date(2027, 4, 14)),
        # Fins de mois : le jour d'arrivée est ramené au dernier jour du mois.
        (date(2027, 1, 31), 1, date(2027, 2, 27)),
        (date(2028, 1, 31), 1, date(2028, 2, 28)),  # 2028 est bissextile : 29 février - 1 jour
        (date(2027, 11, 30), 3, date(2028, 2, 28)),  # 29 février 2028 - 1 jour
        (date(2027, 8, 31), 6, date(2028, 2, 28)),
        (date(2028, 2, 29), 12, date(2029, 2, 27)),
    ]
    for start, months, end in cases:
        assert pricing.period_end(start, months) == end, (start, months)


def test_consecutive_periods_never_overlap_nor_leave_a_gap() -> None:
    start = date(2027, 1, 31)
    for months in (3, 6, 12, 3, 3):
        end = pricing.period_end(start, months)
        assert end >= start
        next_start = pricing.next_period_start([PeriodSpan("PAID", start, end)], start)
        assert (next_start - end).days == 1
        start = next_start


def test_invoice_number_format() -> None:
    assert pricing.format_invoice_number(2027, 1) == "EL-2027-000001"
    assert pricing.format_invoice_number(2027, 123456) == "EL-2027-123456"


def test_state_none_without_any_period() -> None:
    state = pricing.compute_state([], date(2027, 1, 1))
    assert state.state == pricing.STATE_NONE and state.current is None and state.covered_until is None


def test_state_trial_active_expiring_and_expired() -> None:
    trial = PeriodSpan(pricing.PERIOD_KIND_FREE_TRIAL, date(2027, 1, 1), date(2027, 3, 31))
    assert pricing.compute_state([trial], date(2027, 1, 10)).state == pricing.STATE_TRIAL
    # 30 jours ou moins avant la fin : expire bientôt.
    assert pricing.compute_state([trial], date(2027, 3, 1)).state == pricing.STATE_EXPIRING_SOON
    assert pricing.compute_state([trial], date(2027, 4, 1)).state == pricing.STATE_EXPIRED

    paid = PeriodSpan(pricing.PERIOD_KIND_PAID, date(2027, 4, 1), date(2027, 9, 30))
    state = pricing.compute_state([trial, paid], date(2027, 3, 15))
    # Une période payée qui suit sans interruption : la couverture va jusqu'à sa fin.
    assert state.state == pricing.STATE_TRIAL
    assert state.covered_until == date(2027, 9, 30)
    assert pricing.compute_state([trial, paid], date(2027, 5, 1)).state == pricing.STATE_ACTIVE


def test_state_scheduled_when_the_first_period_starts_later() -> None:
    trial = PeriodSpan(pricing.PERIOD_KIND_FREE_TRIAL, date(2027, 1, 1), date(2027, 3, 31))
    state = pricing.compute_state([trial], date(2026, 12, 1))
    assert state.state == pricing.STATE_SCHEDULED
    assert state.next_starts_on == date(2027, 1, 1)
    assert state.covered_until == date(2027, 3, 31)


def test_next_period_start_continues_after_the_latest_period() -> None:
    trial = PeriodSpan(pricing.PERIOD_KIND_FREE_TRIAL, date(2027, 1, 1), date(2027, 3, 31))
    # Paiement pendant le trimestre gratuit : la période payée commence le lendemain de sa fin.
    assert pricing.next_period_start([trial], date(2027, 2, 1)) == date(2027, 4, 1)
    # Trimestre gratuit programmé plus tard : jamais de chevauchement.
    assert pricing.next_period_start([trial], date(2026, 12, 1)) == date(2027, 4, 1)
    # Plus rien de couvert : aujourd'hui.
    assert pricing.next_period_start([trial], date(2027, 5, 10)) == date(2027, 5, 10)
    assert pricing.next_period_start([], date(2027, 5, 10)) == date(2027, 5, 10)


def test_free_quarter_start_rules() -> None:
    launch = date(2027, 1, 1)
    # École déjà en service : date de lancement.
    assert pricing.free_quarter_start(launch, date(2025, 9, 1), []) == launch
    # École créée après le lancement : sa date de création.
    assert pricing.free_quarter_start(launch, date(2027, 2, 10), []) == date(2027, 2, 10)
    # Période payée déjà enregistrée au-delà : le trimestre gratuit vient après, sans chevauchement.
    paid = PeriodSpan(pricing.PERIOD_KIND_PAID, date(2026, 12, 1), date(2027, 2, 28))
    assert pricing.free_quarter_start(launch, date(2025, 9, 1), [paid]) == date(2027, 3, 1)



def test_coverage_reminder_stages() -> None:
    expected = {
        45: None,
        31: None,
        30: pricing.REMINDER_STAGE_J30,
        8: pricing.REMINDER_STAGE_J30,
        7: pricing.REMINDER_STAGE_J7,
        1: pricing.REMINDER_STAGE_J7,
        0: pricing.REMINDER_STAGE_J0,
        -7: pricing.REMINDER_STAGE_J0,
        -8: None,
    }
    for days_left, stage in expected.items():
        assert pricing.coverage_reminder_stage(days_left) == stage, days_left

if __name__ == "__main__":  # vérification locale hors pytest
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
    print(f"{len(tests)} tests de calcul OK")
