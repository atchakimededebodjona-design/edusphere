"""Coupures acceptées au comptage physique, par devise — SEULE source de ces valeurs (backend ET
frontend : l'interface les reçoit de l'API, jamais codées en dur côté client).

XOF (franc CFA BCEAO) : billets 10 000 / 5 000 / 2 000 / 1 000 / 500 et pièces 500 / 250 / 200 /
100 / 50 / 25 / 10 / 5 / 1. La coupure 500 existe sous les deux formes (billet et pièce) : une seule
ligne de comptage par valeur (contrainte `uq_cash_count_line_denomination`), le caissier additionne.
"""

from decimal import Decimal

CASH_DENOMINATIONS: dict[str, tuple[Decimal, ...]] = {
    "XOF": tuple(
        Decimal(value) for value in ("10000", "5000", "2000", "1000", "500", "250", "200", "100", "50", "25", "10", "5", "1")
    ),
}


def denominations_for(currency: str) -> tuple[Decimal, ...]:
    """Coupures de `currency` (ordre décroissant) ; tuple vide si la devise n'a pas de catalogue
    (le comptage est alors refusé explicitement plutôt que d'accepter n'importe quelle valeur)."""
    return CASH_DENOMINATIONS.get(currency.upper(), ())
