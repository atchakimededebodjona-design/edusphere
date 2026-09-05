"""Abstraction d'envoi d'email (Phase 9 — infrastructure d'email transactionnel).

Même principe que `StorageProvider` (`app/core/storage.py`) : le code métier dépend de
`EmailProvider`, jamais d'un SDK/fournisseur concret. `SmtpEmailProvider` n'utilise que la
bibliothèque standard (`smtplib`, `email.message`) — aucune nouvelle dépendance externe.
"""

import logging
import smtplib
import uuid
from abc import ABC, abstractmethod
from email.message import EmailMessage
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, body: str) -> None:
        """Envoie un email texte brut à `to`."""


class LocalEmailProvider(EmailProvider):
    """Implémentation filesystem locale (développement/tests) — n'envoie rien réellement,
    écrit chaque email sous forme de fichier texte, comme `LocalStorageProvider` pour les
    fichiers. Permet de vérifier qu'un envoi a bien été déclenché sans dépendre d'un vrai SMTP.
    """

    def __init__(self, base_path: str) -> None:
        self._base_path = Path(base_path)
        self._base_path.mkdir(parents=True, exist_ok=True)

    async def send(self, to: str, subject: str, body: str) -> None:
        target = self._base_path / f"{uuid.uuid4().hex}.txt"
        target.write_text(f"To: {to}\nSubject: {subject}\n\n{body}", encoding="utf-8")


class SmtpEmailProvider(EmailProvider):
    """Envoi réel via SMTP (bibliothèque standard uniquement)."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        from_address: str,
        use_tls: bool,
        timeout_seconds: int = 10,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_address = from_address
        self._use_tls = use_tls
        self._timeout_seconds = timeout_seconds

    async def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        # Erreurs volontairement non capturées ici : `send_email_best_effort` (seul appelant
        # métier) est le point unique de gestion best-effort — cette méthode doit rester une
        # implémentation fidèle de l'interface `EmailProvider.send`, qui peut lever.
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout_seconds) as smtp:
            if self._use_tls:
                smtp.starttls()
            if self._username:
                smtp.login(self._username, self._password)
            smtp.send_message(message)


def get_email_provider(provider: str, local_path: str) -> EmailProvider:
    if provider == "local":
        return LocalEmailProvider(local_path)
    if provider == "smtp":
        # Phase 16 — échouer au démarrage plutôt qu'au premier envoi réel : EMAIL_PROVIDER=smtp
        # sans SMTP_HOST configuré construisait silencieusement un SmtpEmailProvider inutilisable
        # (l'erreur n'apparaissait qu'en production, best-effort, donc jamais visible de
        # l'appelant — voir send_email_best_effort).
        if not settings.smtp_host:
            raise ValueError("EMAIL_PROVIDER=smtp requires SMTP_HOST to be configured")
        return SmtpEmailProvider(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            from_address=settings.smtp_from_address,
            use_tls=settings.smtp_use_tls,
            timeout_seconds=settings.smtp_timeout_seconds,
        )
    raise ValueError(f"Unknown email provider: {provider}")


# Instance partagée, même principe que `storage` dans app/core/storage.py.
email_provider = get_email_provider(settings.email_provider, settings.email_local_path)


async def send_email_best_effort(to: str, subject: str, body: str) -> None:
    """Envoie un email sans jamais faire échouer l'appelant (cohérent avec le principe déjà
    appliqué au rate limiting Redis — app/core/rate_limit.py — un incident d'envoi ne doit pas
    bloquer la création de compte ou la demande de réinitialisation, déjà commitées en base)."""
    try:
        await email_provider.send(to, subject, body)
    except Exception:  # best-effort volontaire, voir docstring.
        logger.warning("Échec de l'envoi d'email à %s (fournisseur=%s)", to, settings.email_provider, exc_info=True)
