"""Abstraction d'envoi de SMS (PR #16 — canal SMS des rappels de frais en retard).

Même principe que `EmailProvider`/`StorageProvider` : le code métier dépend de `SmsProvider`,
jamais d'un SDK/fournisseur concret. `HttpSmsProvider` n'utilise que la bibliothèque standard
(`urllib.request`) — même choix déjà fait pour `SmtpEmailProvider` (`smtplib`) : aucune nouvelle
dépendance HTTP pour ce seul besoin, et un appel synchrone dans cette méthode `async` reste
cohérent avec ce précédent (jamais sur un chemin de requête HTTP, uniquement dans le job batch
quotidien — voir fees/overdue_reminders.py).
"""

import json
import logging
import urllib.request
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class SmsProvider(ABC):
    @abstractmethod
    async def send(self, to: str, body: str) -> str | None:
        """Envoie un SMS à `to` (déjà normalisé en E.164 par l'appelant — voir
        `app/core/phone.py` — ce provider ne valide ni ne normalise rien lui-même). Retourne un
        `provider_message_id` opaque si le fournisseur en renvoie un (jamais un secret, jamais
        réutilisé comme clé d'idempotence — voir fees/models.py::FeeOverdueSmsReminder), sinon
        `None`. Lève en cas d'échec : `send_sms_best_effort` ci-dessous est le point unique de
        gestion best-effort, cette méthode reste une implémentation fidèle de l'interface."""


class LocalSmsProvider(SmsProvider):
    """Implémentation filesystem locale (développement/tests) — n'envoie rien réellement, écrit
    chaque SMS sous forme de fichier texte, comme `LocalEmailProvider`."""

    def __init__(self, base_path: str) -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def send(self, to: str, body: str) -> str | None:
        message_id = uuid.uuid4().hex
        target = self._base_path / f"{message_id}.txt"
        target.write_text(f"To: {to}\n\n{body}", encoding="utf-8")
        return message_id


class HttpSmsProvider(SmsProvider):
    """Fournisseur générique : un simple POST JSON vers une URL HTTP configurable, avec un
    en-tête d'autorisation Bearer — compatible avec la plupart des passerelles SMS REST sans
    dépendre du SDK d'un opérateur particulier (jamais importé ici). Le format exact de la charge
    utile/réponse variant d'un fournisseur à l'autre, celui-ci reste volontairement minimal
    (`to`/`body`/`sender_id`) ; un fournisseur réel retenu pourra nécessiter un adaptateur dédié
    implémentant la même interface `SmsProvider`, sans toucher au code métier qui l'utilise."""

    def __init__(self, url: str, auth_token: str, sender_id: str, timeout_seconds: int) -> None:
        self._url = url
        self._auth_token = auth_token
        self._sender_id = sender_id
        self._timeout_seconds = timeout_seconds

    async def send(self, to: str, body: str) -> str | None:
        payload: dict[str, str] = {"to": to, "body": body}
        if self._sender_id:
            payload["sender_id"] = self._sender_id
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._auth_token}",
            },
        )
        # Erreur réseau/HTTP volontairement non capturée ici (même motif que SmtpEmailProvider) —
        # propage vers `send_sms_best_effort`, seul point de gestion best-effort.
        with urllib.request.urlopen(request, timeout=self._timeout_seconds) as response:
            raw_body = response.read()
        try:
            data = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        message_id = data.get("message_id") or data.get("id")
        return str(message_id) if message_id is not None else None


def get_sms_provider(provider: str, local_path: str) -> SmsProvider:
    if provider == "local":
        return LocalSmsProvider(local_path)
    if provider == "http":
        # Échoue explicitement dès la construction (démarrage de l'app), quel que soit
        # l'environnement — même motif que `get_email_provider` pour EMAIL_PROVIDER=smtp sans
        # SMTP_HOST : un fournisseur réel activé sans sa configuration obligatoire ne doit jamais
        # échouer silencieusement au premier envoi, en production comme ailleurs.
        if not settings.sms_http_url or not settings.sms_http_auth_token:
            raise ValueError("SMS_PROVIDER=http requires SMS_HTTP_URL and SMS_HTTP_AUTH_TOKEN to be configured")
        return HttpSmsProvider(
            url=settings.sms_http_url,
            auth_token=settings.sms_http_auth_token,
            sender_id=settings.sms_sender_id,
            timeout_seconds=settings.sms_http_timeout_seconds,
        )
    raise ValueError(f"Unknown SMS provider: {provider}")


# Instance partagée, même principe que `email_provider` dans app/core/email.py.
sms_provider = get_sms_provider(settings.sms_provider, settings.sms_local_path)


async def send_sms_best_effort(to: str, body: str) -> tuple[bool, str | None]:
    """Envoie un SMS sans jamais faire échouer l'appelant (même motif que
    `send_email_best_effort`) — un incident d'envoi ne doit jamais affecter les lignes de suivi
    déjà committées. Retourne `(accepted, provider_message_id)` : `accepted=True` signifie
    uniquement que le FOURNISSEUR a accepté le message pour traitement, jamais que le SMS a été
    livré au téléphone (voir fees/models.py::FeeOverdueSmsReminder.transport_status).

    Le numéro de téléphone (`to`) est journalisé en cas d'échec, exactement comme l'adresse email
    l'est déjà par `send_email_best_effort` — jamais un secret au sens propre, et une donnée déjà
    présente dans les logs applicatifs existants pour le canal email ; jamais le corps du message
    ni aucun jeton/identifiant de compte."""
    try:
        message_id = await sms_provider.send(to, body)
        return True, message_id
    except Exception:  # best-effort volontaire, voir docstring.
        logger.warning(
            "Échec de l'envoi de SMS à %s (fournisseur=%s)", to, settings.sms_provider, exc_info=True
        )
        return False, None
