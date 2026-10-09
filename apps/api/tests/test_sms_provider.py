"""PR #16 — infrastructure SMS transactionnelle (canal des rappels de frais en retard).

Même convention d'isolation que `test_email.py` : `LocalSmsProvider` écrit chaque SMS sous forme
de fichier dans un répertoire temporaire propre à chaque test (`tmp_path`), en remplaçant
l'instance partagée `app.core.sms.sms_provider` via monkeypatch.
"""

import logging
from pathlib import Path

import pytest

import app.core.sms as sms_module
from app.core.config import settings
from app.core.sms import HttpSmsProvider, LocalSmsProvider, get_sms_provider, send_sms_best_effort


def _read_sms(directory: Path) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in directory.glob("*.txt")]


# --- LocalSmsProvider (unitaire) ------------------------------------------------------------------
async def test_local_sms_provider_writes_a_file_with_expected_content(tmp_path: Path) -> None:
    provider = LocalSmsProvider(str(tmp_path))
    message_id = await provider.send("+22890123456", "Corps du SMS de test")

    files = list(tmp_path.glob("*.txt"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "+22890123456" in content
    assert "Corps du SMS de test" in content
    # Le provider local renvoie bien un identifiant de message (opaque, pour que les tests
    # puissent vérifier le report de `provider_message_id` sans dépendre d'un vrai fournisseur).
    assert message_id is not None
    assert len(message_id) > 0


# --- Sélection du provider (SMS_PROVIDER) --------------------------------------------------------
def test_get_sms_provider_local_returns_local_provider(tmp_path: Path) -> None:
    provider = get_sms_provider("local", str(tmp_path))
    assert isinstance(provider, LocalSmsProvider)


def test_get_sms_provider_http_returns_http_provider_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instanciation uniquement — aucune requête réseau réelle n'est émise ici. Valeurs
    manifestement factices, jamais un secret réel dans le code de test."""
    monkeypatch.setattr(settings, "sms_http_url", "https://sms.example-test.invalid/send")
    monkeypatch.setattr(settings, "sms_http_auth_token", "test-token-placeholder")
    monkeypatch.setattr(settings, "sms_sender_id", "EduLinkage")

    provider = get_sms_provider("http", "./unused")
    assert isinstance(provider, HttpSmsProvider)


def test_get_sms_provider_http_without_url_raises_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cahier des charges PR #16 §2 : un fournisseur réel activé sans sa configuration obligatoire
    doit échouer EXPLICITEMENT (ici, dès la construction), jamais silencieusement au premier
    envoi."""
    monkeypatch.setattr(settings, "sms_http_url", "")
    monkeypatch.setattr(settings, "sms_http_auth_token", "test-token-placeholder")
    with pytest.raises(ValueError, match="SMS_HTTP_URL"):
        get_sms_provider("http", "./unused")


def test_get_sms_provider_http_without_auth_token_raises_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "sms_http_url", "https://sms.example-test.invalid/send")
    monkeypatch.setattr(settings, "sms_http_auth_token", "")
    with pytest.raises(ValueError, match="SMS_HTTP_AUTH_TOKEN"):
        get_sms_provider("http", "./unused")


def test_get_sms_provider_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        get_sms_provider("carrier-pigeon", "./unused")


# --- send_sms_best_effort (succès/échec, jamais de levée) ----------------------------------------
async def test_send_sms_best_effort_returns_true_and_message_id_on_success(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(sms_module, "sms_provider", LocalSmsProvider(str(tmp_path)))
    accepted, message_id = await send_sms_best_effort("+22890123456", "Corps")
    assert accepted is True
    assert message_id is not None


async def test_send_sms_best_effort_does_not_raise_on_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        async def send(self, to: str, body: str) -> str | None:
            raise RuntimeError("Passerelle SMS indisponible (simulé)")

    monkeypatch.setattr(sms_module, "sms_provider", FailingProvider())
    accepted, message_id = await send_sms_best_effort("+22890123456", "Corps")
    assert accepted is False
    assert message_id is None


async def test_send_sms_best_effort_logs_failure_without_leaking_body_or_secrets(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Cahier des charges PR #16 §2/§10 : jamais de secret dans les logs. Le numéro de
    destinataire est journalisé (même convention déjà appliquée à l'adresse email par
    `send_email_best_effort`), mais jamais le corps du message ni un jeton/identifiant de compte."""

    class FailingProvider:
        async def send(self, to: str, body: str) -> str | None:
            raise RuntimeError("Passerelle SMS indisponible (simulé)")

    monkeypatch.setattr(sms_module, "sms_provider", FailingProvider())
    fake_secret_token = "super-secret-token-should-never-appear-in-logs"
    monkeypatch.setattr(settings, "sms_http_auth_token", fake_secret_token)
    secret_body = "Corps du SMS — ne doit jamais apparaître dans un log"
    with caplog.at_level(logging.WARNING):
        await send_sms_best_effort("+22890123456", secret_body)

    log_text = caplog.text
    assert "+22890123456" in log_text  # destinataire : même convention que l'email, pas un secret
    assert secret_body not in log_text
    assert fake_secret_token not in log_text
