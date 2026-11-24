"""2026-11-24 — protection anti-spam : « mot de passe oublié » limité aussi par adresse IP.

Sous ASGITransport, toutes les requêtes viennent de la même IP factice : chaque demande avec un
email DIFFÉRENT (jamais bloqué par la limite par email) compte pour la même adresse IP."""

import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import unique_email


async def test_forgot_password_distinct_emails_below_ip_threshold_are_accepted(client: AsyncClient) -> None:
    for _ in range(settings.forgot_password_ip_rate_limit_max_attempts):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email("ipok")})
        assert response.status_code == 202


async def test_forgot_password_distinct_emails_above_ip_threshold_are_refused(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "forgot_password_ip_rate_limit_max_attempts", 3)
    for _ in range(3):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email("ipspam")})
        assert response.status_code == 202

    blocked = await client.post("/api/v1/auth/forgot-password", json={"email": unique_email("ipspam")})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    # Même message que la limite par email : rien n'indique si l'adresse correspond à un compte.
    assert blocked.json()["detail"] == "Too many password reset requests. Please try again later."
