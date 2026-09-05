"""Tests de l'infrastructure d'email transactionnel (Phase 9).

`LocalEmailProvider` (utilisée en test, comme en dev) écrit chaque email sous forme de fichier —
on isole chaque test dans son propre répertoire temporaire (`tmp_path`) en remplaçant l'instance
partagée `app.core.email.email_provider`, plutôt que de dépendre du répertoire réel configuré
par `.env` (partagé entre tous les tests, cohérent avec l'isolation déjà pratiquée pour Redis
dans test_auth_rate_limit.py via monkeypatch).
"""

from pathlib import Path

import pytest
from httpx import AsyncClient

import app.core.email as email_module
from app.core.config import settings
from app.core.email import LocalEmailProvider, SmtpEmailProvider, get_email_provider, send_email_best_effort
from tests.conftest import register_school, unique_email


async def _login(client: AsyncClient, email: str, password: str = "SuperSecret123") -> str:
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return response.json()["access_token"]


def _read_emails(directory: Path) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in directory.glob("*.txt")]


# --- LocalEmailProvider (unitaire) --------------------------------------------------------------
async def test_local_email_provider_writes_a_file_with_expected_content(tmp_path: Path) -> None:
    provider = LocalEmailProvider(str(tmp_path))
    await provider.send("teacher@example.tg", "Sujet de test", "Corps du message")

    files = list(tmp_path.glob("*.txt"))
    assert len(files) == 1
    content = files[0].read_text(encoding="utf-8")
    assert "teacher@example.tg" in content
    assert "Sujet de test" in content
    assert "Corps du message" in content


# --- Sélection du provider (Phase 14 — préparation configuration de production) ------------------
def test_get_email_provider_local_returns_local_provider(tmp_path: Path) -> None:
    provider = get_email_provider("local", str(tmp_path))
    assert isinstance(provider, LocalEmailProvider)


def test_get_email_provider_smtp_returns_smtp_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Instanciation uniquement — aucune connexion réseau réelle n'est établie ici (voir
    PHASE_14_IMPLEMENTATION.md §7 : livraison externe non testée dans cet environnement). Valeurs
    manifestement factices, jamais de secret réel dans le code de test."""
    monkeypatch.setattr(settings, "smtp_host", "smtp.example-test.invalid")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", "test-user-placeholder")
    monkeypatch.setattr(settings, "smtp_password", "test-password-placeholder")
    monkeypatch.setattr(settings, "smtp_from_address", "no-reply@example-test.invalid")
    monkeypatch.setattr(settings, "smtp_use_tls", True)

    provider = get_email_provider("smtp", "./unused")
    assert isinstance(provider, SmtpEmailProvider)


def test_get_email_provider_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError):
        get_email_provider("carrier-pigeon", "./unused")


async def test_send_email_best_effort_does_not_raise_on_provider_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingProvider:
        async def send(self, to: str, subject: str, body: str) -> None:
            raise RuntimeError("SMTP down")

    monkeypatch.setattr(email_module, "email_provider", FailingProvider())
    # Ne doit jamais lever — un incident d'envoi ne bloque pas l'appelant (cf. docstring).
    await send_email_best_effort("someone@example.tg", "Sujet", "Corps")


# --- Intégration : mot de passe oublié déclenche réellement un envoi ----------------------------
async def test_forgot_password_triggers_a_real_email_send(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))

    data = await register_school(client, "emailforgot")
    email = data["user"]["email"]

    response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert response.status_code == 202
    assert response.json()["dev_token"]  # comportement existant préservé (hors production)

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    assert email in emails[0]
    assert "reset-password?token=" in emails[0]


async def test_forgot_password_unknown_email_sends_nothing(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Renforce la garantie anti-énumération existante (test_forgot_password_unknown_email_does_not_leak,
    test_auth.py) jusqu'à la couche email : aucun envoi ne doit être déclenché pour un compte
    inexistant."""
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))

    response = await client.post(
        "/api/v1/auth/forgot-password", json={"email": unique_email("ghost.emailtest")}
    )
    assert response.status_code == 202
    assert response.json()["dev_token"] is None
    assert _read_emails(tmp_path) == []


# --- Intégration : création d'utilisateur déclenche un envoi d'invitation -----------------------
async def test_create_user_triggers_invitation_email(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))

    data = await register_school(client, "emailinvite")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    teacher_email = unique_email("teacher.emailinvite")

    response = await client.post(
        "/api/v1/users",
        json={"email": teacher_email, "full_name": "Prof Test", "school_id": school_id, "role_code": "TEACHER"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    assert response.json()["dev_reset_token"]  # comportement existant préservé

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    assert teacher_email in emails[0]
    assert "reset-password?token=" in emails[0]


async def test_reattaching_existing_user_does_not_send_a_new_invitation(
    client: AsyncClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))

    data = await register_school(client, "emailreattach")
    headers = {"Authorization": f"Bearer {await _login(client, data['user']['email'])}"}
    school_id = data["school"]["id"]
    other_school = await register_school(client, "emailreattach-other")
    other_headers = {"Authorization": f"Bearer {await _login(client, other_school['user']['email'])}"}

    shared_email = unique_email("shared.emailreattach")
    first = await client.post(
        "/api/v1/users",
        json={"email": shared_email, "full_name": "Partagé", "school_id": school_id, "role_code": "TEACHER"},
        headers=headers,
    )
    assert first.status_code == 201
    assert len(_read_emails(tmp_path)) == 1

    second = await client.post(
        "/api/v1/users",
        json={
            "email": shared_email,
            "full_name": "Partagé",
            "school_id": other_school["school"]["id"],
            "role_code": "TEACHER",
        },
        headers=other_headers,
    )
    assert second.status_code == 201
    assert second.json()["dev_reset_token"] is None
    # Toujours un seul email au total : aucun second envoi pour un compte déjà existant.
    assert len(_read_emails(tmp_path)) == 1
