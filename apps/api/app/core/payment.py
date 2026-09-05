"""Abstraction de fournisseur de paiement (Phase 19 — School Fees & Billing).

Même principe que `StorageProvider` (`app/core/storage.py`) et `EmailProvider`
(`app/core/email.py`) : le code métier financier dépend de `PaymentProvider`, jamais d'un SDK
Mobile Money concret, afin qu'un futur fournisseur (TMoney, Flooz...) puisse être branché plus
tard sans réécrire `app/modules/fees`.

Une seule implémentation existe pour cette phase : `ManualPaymentProvider`, qui n'effectue AUCUN
appel réseau — elle enregistre uniquement qu'un paiement a été saisi manuellement par le
personnel de l'école (espèces, virement, chèque, dépôt agent...). Aucune intégration Mobile
Money réelle n'existe dans ce dépôt (TMoney/Flooz/Moov Money/Airtel Money ou autre) — ne pas
interpréter cette abstraction comme une preuve du contraire.
"""

from abc import ABC, abstractmethod
from decimal import Decimal


class PaymentResult:
    """Résultat renvoyé par un `PaymentProvider` — volontairement minimal (pas de sur-architecture,
    voir consigne Phase 19 §5). `external_reference` reste `None` pour un paiement manuel (aucun
    système tiers ne l'a produit) ; un futur fournisseur en ligne y placerait l'identifiant de
    transaction retourné par son API."""

    def __init__(self, accepted: bool, external_reference: str | None = None) -> None:
        self.accepted = accepted
        self.external_reference = external_reference


class PaymentProvider(ABC):
    @abstractmethod
    async def record(self, amount: Decimal, method: str, reference: str | None) -> PaymentResult:
        """Enregistre un paiement pour ce montant/cette méthode. Ne lève pas pour un refus
        fonctionnel normal (ex. montant invalide déjà validé en amont par `fees/service.py`) —
        cette méthode ne fait qu'acter la transaction, la validation métier reste dans le module
        `fees`, jamais dans le provider."""


class ManualPaymentProvider(PaymentProvider):
    """Seule implémentation de cette phase : aucun appel externe, aucun secret, aucune
    dépendance nouvelle — le paiement est déjà enregistré en base par `fees/service.py` avant
    même l'appel à ce provider ; il ne fait qu'acter que l'enregistrement suit bien le chemin de
    l'abstraction, pour qu'un futur fournisseur réel s'y substitue sans changer `fees/service.py`.
    """

    async def record(self, amount: Decimal, method: str, reference: str | None) -> PaymentResult:
        return PaymentResult(accepted=True, external_reference=None)


def get_payment_provider(provider: str) -> PaymentProvider:
    if provider == "manual":
        return ManualPaymentProvider()
    raise ValueError(f"Unknown payment provider: {provider}")


# Instance partagée, même principe que `storage`/`email_provider`.
payment_provider = get_payment_provider("manual")
