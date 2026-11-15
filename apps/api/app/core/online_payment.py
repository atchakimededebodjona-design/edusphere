"""Paiement en ligne des abonnements (Phase 29, lot B) — abstraction `OnlinePaymentProvider`.

Distincte de `app/core/payment.py::PaymentProvider` (frais scolaires), qui reste inchangée. Deux
implémentations :
- `PayGateProvider` : méthode DIRECTE de PayGate Global, d'après le guide d'intégration du tableau
  de bord marchand (lu le 2026-11-15) — `POST {base}/api/v1/pay` pour demander le paiement,
  `POST {base}/api/v2/status` (par `identifier`) pour en connaître l'état. La redirection
  (`/v1/page`) et le « Checkout » mettent la clé API dans l'URL vue par le navigateur : écartés
  (cadrage §4.3, critère éliminatoire) ;
- `FakeOnlinePaymentProvider` : tests et développement, aucun appel réseau (motif `LocalSmsProvider`).

Appels HTTP : bibliothèque standard (`urllib.request`) exécutée dans un thread, même choix que
`HttpSmsProvider` — aucune dépendance de production nouvelle (`httpx` n'est installé que pour les
tests). Le transport est injectable pour les tests (`post_json`).

Le jeton ne figure QUE dans le corps JSON envoyé à PayGate. Il n'est jamais journalisé et ne remonte
jamais dans une exception : toute erreur est convertie en un code court (`TIMEOUT`, `HTTP_502`…),
stocké dans `subscription_payments.provider_status_code` (16 caractères au plus).
"""

import asyncio
import json
import logging
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Literal

from app.core.config import settings

logger = logging.getLogger(__name__)

OnlineNetwork = Literal["FLOOZ", "TMONEY"]
StatusState = Literal["SUCCEEDED", "PENDING", "EXPIRED", "CANCELLED", "UNKNOWN"]

# Codes d'état de la vérification (guide officiel, section « Vérifier l'état d'un paiement »).
_STATUS_STATES: dict[str, StatusState] = {"0": "SUCCEEDED", "2": "PENDING", "4": "EXPIRED", "6": "CANCELLED"}

# Codes de la réponse de `/api/v1/pay` : NON décrits par le guide officiel. D'après les intégrations
# existantes : 0 = transaction enregistrée, 2 = jeton invalide, 4 = paramètres invalides,
# 6 = doublon d'identifiant. Seuls 2 et 4 sont traités comme un refus définitif (aucune transaction
# n'a pu être créée) ; un doublon ou tout autre code reste « inconnu » et sera tranché par la
# vérification d'état (jamais un faux échec sur un paiement qui aurait pu aboutir).
_PAY_REFUSED_CODES = {"2", "4"}

MAX_RESPONSE_BYTES = 65_536

PostJson = Callable[[str, dict[str, object], float], tuple[int, bytes]]


@dataclass(frozen=True)
class InitiationResult:
    """`accepted` : True = demande enregistrée par le fournisseur ; False = refus définitif (aucune
    transaction n'existe) ; None = issue inconnue (délai dépassé, réponse illisible, doublon…) :
    la tentative reste en cours et la vérification d'état tranchera."""

    accepted: bool | None
    tx_reference: str | None
    code: str


@dataclass(frozen=True)
class StatusResult:
    state: StatusState
    code: str
    tx_reference: str | None = None
    payment_reference: str | None = None
    payment_method: str | None = None
    # Le guide officiel ne liste pas le montant dans la réponse de vérification : None si absent.
    amount: Decimal | None = None


class OnlinePaymentProvider(ABC):
    name: str

    @abstractmethod
    async def initiate(
        self, *, identifier: str, amount: int, phone_number: str, network: OnlineNetwork, description: str
    ) -> InitiationResult:
        """Demande le paiement. `phone_number` : 8 chiffres locaux (Togo), déjà validés."""

    @abstractmethod
    async def check_status(self, *, identifier: str) -> StatusResult:
        """État de la transaction portant cet `identifier` (notre identifiant)."""


def _urllib_post_json(url: str, payload: dict[str, object], timeout: float) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": "EduLinkage/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(MAX_RESPONSE_BYTES)
    except urllib.error.HTTPError as exc:
        body = exc.read(MAX_RESPONSE_BYTES) if exc.fp is not None else b""
        return int(exc.code), body


def _short_str(value: object, max_length: int) -> str | None:
    if value is None or isinstance(value, bool) or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text[:max_length] if text else None


def _code(value: object) -> str:
    """Code d'état renvoyé en entier ou en chaîne ; toute autre forme vaut « inconnu »."""
    if isinstance(value, bool):
        return "UNKNOWN"
    if isinstance(value, int):
        return str(value)[:16]
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return value.strip()[:16]
    return "UNKNOWN"


def _amount(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return None


class PayGateProvider(OnlinePaymentProvider):
    name = "paygate"
    PAY_PATH = "/api/v1/pay"
    STATUS_PATH = "/api/v2/status"

    def __init__(
        self, auth_token: str, base_url: str, timeout_seconds: float, post_json: PostJson = _urllib_post_json
    ) -> None:
        self._auth_token = auth_token
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._post_json = post_json

    async def _post(self, path: str, payload: dict[str, object]) -> tuple[int | None, object, str | None]:
        """(statut HTTP, JSON décodé, code d'erreur). Jamais d'exception, jamais le jeton dans un
        message : seules la route et la nature de l'erreur sont journalisées."""
        try:
            http_status, body = await asyncio.to_thread(self._post_json, self._base_url + path, payload, self._timeout)
        except TimeoutError:
            logger.warning("PayGate %s : délai dépassé.", path)
            return None, None, "TIMEOUT"
        except urllib.error.URLError as exc:
            timed_out = isinstance(exc.reason, TimeoutError)
            logger.warning("PayGate %s : %s.", path, "délai dépassé" if timed_out else "erreur réseau")
            return None, None, "TIMEOUT" if timed_out else "NETWORK_ERROR"
        except OSError:
            logger.warning("PayGate %s : erreur réseau.", path)
            return None, None, "NETWORK_ERROR"
        try:
            data = json.loads(body.decode("utf-8")) if body else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("PayGate %s : réponse illisible (HTTP %s).", path, http_status)
            return http_status, None, "INVALID_RESPONSE"
        return http_status, data, None

    async def initiate(
        self, *, identifier: str, amount: int, phone_number: str, network: OnlineNetwork, description: str
    ) -> InitiationResult:
        payload: dict[str, object] = {
            "auth_token": self._auth_token,
            "phone_number": phone_number,
            "amount": amount,
            "description": description,
            "identifier": identifier,
            "network": network,
        }
        http_status, data, error = await self._post(self.PAY_PATH, payload)
        if error is not None:
            return InitiationResult(accepted=None, tx_reference=None, code=error)
        assert http_status is not None
        if not 200 <= http_status < 300:
            # Une requête rejetée (4xx, hors 408/429) n'a créé aucune transaction ; une erreur du
            # serveur PayGate (5xx) laisse l'issue inconnue.
            refused = 400 <= http_status < 500 and http_status not in (408, 429)
            logger.warning("PayGate /pay : HTTP %s.", http_status)
            return InitiationResult(accepted=False if refused else None, tx_reference=None, code=f"HTTP_{http_status}")
        if not isinstance(data, dict):
            return InitiationResult(accepted=None, tx_reference=None, code="INVALID_RESPONSE")
        code = _code(data.get("status"))
        tx_reference = _short_str(data.get("tx_reference"), 128)
        if code == "0":
            return InitiationResult(accepted=True, tx_reference=tx_reference, code=code)
        if code == "2":
            logger.error(
                "PayGate a refusé la clé API (code 2) : vérifier PAYGATE_AUTH_TOKEN et, si une adresse IP "
                "est déclarée dans le profil PayGate, qu'il s'agit bien de celle du serveur."
            )
        if code in _PAY_REFUSED_CODES:
            return InitiationResult(accepted=False, tx_reference=None, code=code)
        return InitiationResult(accepted=None, tx_reference=tx_reference, code=code)

    async def check_status(self, *, identifier: str) -> StatusResult:
        payload: dict[str, object] = {"auth_token": self._auth_token, "identifier": identifier}
        http_status, data, error = await self._post(self.STATUS_PATH, payload)
        if error is not None:
            return StatusResult(state="UNKNOWN", code=error)
        assert http_status is not None
        if not 200 <= http_status < 300:
            return StatusResult(state="UNKNOWN", code=f"HTTP_{http_status}")
        if not isinstance(data, dict):
            return StatusResult(state="UNKNOWN", code="INVALID_RESPONSE")
        returned_identifier = _short_str(data.get("identifier"), 64)
        if returned_identifier is not None and returned_identifier != identifier:
            logger.warning("PayGate /status : identifiant renvoyé différent de l'identifiant demandé.")
            return StatusResult(state="UNKNOWN", code="ID_MISMATCH")
        code = _code(data.get("status"))
        return StatusResult(
            state=_STATUS_STATES.get(code, "UNKNOWN"),
            code=code,
            tx_reference=_short_str(data.get("tx_reference"), 128),
            payment_reference=_short_str(data.get("payment_reference"), 128),
            payment_method=_short_str(data.get("payment_method"), 16),
            amount=_amount(data.get("amount")),
        )


@dataclass
class FakeOnlinePaymentProvider(OnlinePaymentProvider):
    """Aucun appel réseau. Par défaut, une demande est acceptée et reste « en cours » jusqu'à ce
    qu'un test fixe son état (`set_status`). `next_initiation` permet de simuler un refus ou une
    issue inconnue pour la prochaine demande seulement."""

    name: str = "fake"
    initiations: list[dict[str, object]] = field(default_factory=list)
    statuses: dict[str, StatusResult] = field(default_factory=dict)
    status_calls: list[str] = field(default_factory=list)
    next_initiation: InitiationResult | None = None

    async def initiate(
        self, *, identifier: str, amount: int, phone_number: str, network: OnlineNetwork, description: str
    ) -> InitiationResult:
        self.initiations.append(
            {"identifier": identifier, "amount": amount, "phone_number": phone_number, "network": network}
        )
        result = self.next_initiation or InitiationResult(accepted=True, tx_reference=f"FAKE-{identifier}", code="0")
        self.next_initiation = None
        if result.accepted is not False:
            self.statuses.setdefault(identifier, StatusResult(state="PENDING", code="2"))
        return result

    async def check_status(self, *, identifier: str) -> StatusResult:
        self.status_calls.append(identifier)
        return self.statuses.get(identifier, StatusResult(state="UNKNOWN", code="UNKNOWN"))

    def set_status(self, identifier: str, state: StatusState, *, amount: Decimal | None = None, code: str | None = None) -> None:
        codes = {"SUCCEEDED": "0", "PENDING": "2", "EXPIRED": "4", "CANCELLED": "6", "UNKNOWN": "UNKNOWN"}
        self.statuses[identifier] = StatusResult(
            state=state,
            code=code or codes[state],
            tx_reference=f"FAKE-{identifier}",
            payment_reference=f"FAKEREF-{identifier[-6:]}" if state == "SUCCEEDED" else None,
            payment_method="FLOOZ",
            amount=amount,
        )


fake_online_payment_provider = FakeOnlinePaymentProvider()


def get_online_payment_provider() -> OnlinePaymentProvider:
    """Fournisseur choisi à l'appel (et non au chargement du module), pour que la configuration
    reste modifiable par les tests. En production, le coupe-circuit actif impose "paygate" et un
    jeton (config.validate_production_config)."""
    if settings.payment_online_provider == "paygate":
        return PayGateProvider(
            auth_token=settings.paygate_auth_token,
            base_url=settings.paygate_api_base_url,
            timeout_seconds=settings.paygate_timeout_seconds,
        )
    if settings.payment_online_provider == "fake":
        return fake_online_payment_provider
    raise ValueError(f"Unknown PAYMENT_ONLINE_PROVIDER: {settings.payment_online_provider}")
