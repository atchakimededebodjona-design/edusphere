"""PR #16 — normalisation de numéro de téléphone (E.164) pour le canal SMS.

Tests purement unitaires (aucune base de données) : `normalize_phone_to_e164` ne dépend que de
`phonenumbers`, jamais de l'état applicatif.
"""

from app.core.phone import normalize_phone_to_e164


def test_valid_togo_number_local_format_normalizes_to_e164() -> None:
    assert normalize_phone_to_e164("90123456", "TG") == "+22890123456"


def test_valid_togo_number_with_spaces_and_dashes_normalizes() -> None:
    assert normalize_phone_to_e164("90 12-34 56", "TG") == "+22890123456"


def test_already_e164_number_is_returned_unchanged_regardless_of_default_region() -> None:
    # Un numéro déjà au format international (préfixe "+") ignore `default_region` — ici un
    # numéro français valide, alors que la région par défaut fournie est "TG".
    assert normalize_phone_to_e164("+33612345678", "TG") == "+33612345678"


def test_missing_number_returns_none() -> None:
    assert normalize_phone_to_e164(None, "TG") is None


def test_empty_or_blank_string_returns_none() -> None:
    assert normalize_phone_to_e164("", "TG") is None
    assert normalize_phone_to_e164("   ", "TG") is None


def test_garbage_string_returns_none_never_raises() -> None:
    assert normalize_phone_to_e164("pas-un-numero", "TG") is None
    assert normalize_phone_to_e164("123", "TG") is None
    assert normalize_phone_to_e164("++++", "TG") is None
    assert normalize_phone_to_e164("abcdefghij", "TG") is None


def test_different_default_region_changes_interpretation_of_local_format() -> None:
    # Le même numéro local (sans indicatif) est interprété différemment selon la région par
    # défaut — exactement pourquoi `Organization.country_code` doit piloter ce paramètre plutôt
    # qu'une valeur figée en dur (voir fees/overdue_reminders.py).
    togo_result = normalize_phone_to_e164("90123456", "TG")
    assert togo_result == "+22890123456"
    # Un numéro français valide à 9 chiffres (sans le 0 initial), région FR.
    french_result = normalize_phone_to_e164("612345678", "FR")
    assert french_result == "+33612345678"


def test_valid_number_for_wrong_region_is_rejected() -> None:
    # Un numéro français complet, analysé avec une région TG sans indicatif explicite, n'est pas
    # un numéro togolais valide — doit être rejeté plutôt que mal interprété.
    assert normalize_phone_to_e164("0612345678", "TG") is None
