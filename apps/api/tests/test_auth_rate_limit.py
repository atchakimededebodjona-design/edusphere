"""Tests du rate limiting login (Phase 7.2 — durcissement pré-pilote).

Utilise le Redis réel du docker-compose (accessible depuis le conteneur `api`, comme en
développement) — pas de mock, cohérent avec la façon dont RLS/Postgres sont déjà testés en
conditions réelles ailleurs dans ce projet (cf. test_tenant_isolation.py).
"""

import asyncio

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.rate_limit import _get_client, _key
from tests.conftest import register_school, unique_email


async def _clear_key(email: str) -> None:
    await _get_client().delete(_key(email))


# --- 1/3 — tentatives normales sous le seuil : autorisées, comptent les échecs sans bloquer ----
async def test_normal_attempts_below_threshold_are_allowed(client: AsyncClient) -> None:
    data = await register_school(client, "ratelimitok")
    email = data["user"]["email"]
    await _clear_key(email)

    for _ in range(settings.login_rate_limit_max_attempts - 1):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        assert response.status_code == 401

    ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert ok.status_code == 200


# --- 2 — seuil dépassé : refus temporaire (429), même avec le bon mot de passe -----------------
async def test_threshold_exceeded_returns_429_even_with_correct_password(client: AsyncClient) -> None:
    data = await register_school(client, "ratelimitexceed")
    email = data["user"]["email"]
    await _clear_key(email)

    for _ in range(settings.login_rate_limit_max_attempts):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})

    blocked = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers

    blocked_even_correct = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert blocked_even_correct.status_code == 429


# --- 4 — compte inexistant : même comptage, même code que pour un compte réel ------------------
async def test_nonexistent_account_is_rate_limited_identically(client: AsyncClient) -> None:
    email = unique_email("doesnotexist")
    await _clear_key(email)

    for _ in range(settings.login_rate_limit_max_attempts):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": "whatever"})
        assert response.status_code == 401

    blocked = await client.post("/api/v1/auth/login", json={"email": email, "password": "whatever"})
    assert blocked.status_code == 429


# --- 5/6/9 — fenêtre de limitation, expiration, succès après expiration ------------------------
async def test_rate_limit_expires_and_login_succeeds_again(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "login_rate_limit_max_attempts", 2)
    monkeypatch.setattr(settings, "login_rate_limit_window_seconds", 1)

    data = await register_school(client, "ratelimitexpire")
    email = data["user"]["email"]
    await _clear_key(email)

    for _ in range(2):
        await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    blocked = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert blocked.status_code == 429

    await asyncio.sleep(1.5)  # fenêtre de 1s expirée

    recovered = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert recovered.status_code == 200


# --- 7 — isolation entre comptes (tenant-safe) --------------------------------------------------
async def test_rate_limit_isolated_between_accounts(client: AsyncClient) -> None:
    data_a = await register_school(client, "ratelimitisoa")
    data_b = await register_school(client, "ratelimitisob")
    email_a = data_a["user"]["email"]
    email_b = data_b["user"]["email"]
    await _clear_key(email_a)
    await _clear_key(email_b)

    for _ in range(settings.login_rate_limit_max_attempts):
        await client.post("/api/v1/auth/login", json={"email": email_a, "password": "wrong-password"})
    blocked_a = await client.post("/api/v1/auth/login", json={"email": email_a, "password": "wrong-password"})
    assert blocked_a.status_code == 429

    # Le compte B n'est pas affecté par les échecs répétés sur le compte A.
    ok_b = await client.post("/api/v1/auth/login", json={"email": email_b, "password": "SuperSecret123"})
    assert ok_b.status_code == 200


# --- 8 — absence de fuite d'information (compte réel vs inexistant : réponse identique) --------
async def test_no_account_existence_leak_via_rate_limit(client: AsyncClient) -> None:
    data = await register_school(client, "ratelimitnoleak")
    real_email = data["user"]["email"]
    fake_email = unique_email("doesnotexist2")
    await _clear_key(real_email)
    await _clear_key(fake_email)

    real_response = await client.post("/api/v1/auth/login", json={"email": real_email, "password": "wrong-password"})
    fake_response = await client.post("/api/v1/auth/login", json={"email": fake_email, "password": "wrong-password"})
    assert real_response.status_code == fake_response.status_code == 401
    assert real_response.json()["detail"] == fake_response.json()["detail"]


# --- Régression : succès normal réinitialise le compteur ---------------------------------------
async def test_successful_login_resets_attempt_counter(client: AsyncClient) -> None:
    data = await register_school(client, "ratelimitreset")
    email = data["user"]["email"]
    await _clear_key(email)

    await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
    ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert ok.status_code == 200

    # Le compteur est reparti à zéro : on peut de nouveau se tromper `max_attempts - 1` fois
    # sans être bloqué.
    for _ in range(settings.login_rate_limit_max_attempts - 1):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password"})
        assert response.status_code == 401
    still_ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert still_ok.status_code == 200
