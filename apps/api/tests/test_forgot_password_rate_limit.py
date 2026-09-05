"""Rate limiting de /auth/forgot-password (Phase 10.1).

Même Redis réel du docker-compose que test_auth_rate_limit.py, pas de mock — cohérent avec les
conventions déjà établies pour tester le rate limiting login (Phase 7.2). Le compteur est
distinct de celui du login (clé `forgot_password_attempts:`, voir app/core/rate_limit.py) :
aucun des deux mécanismes n'affecte l'autre.
"""

import asyncio

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

import app.core.rate_limit as rate_limit_module
from app.core.config import settings
from app.core.rate_limit import _forgot_password_key, _get_client
from tests.conftest import register_school, unique_email


async def _clear_key(email: str) -> None:
    await _get_client().delete(_forgot_password_key(email))


# --- 1 — demandes normales sous le seuil : toujours 202, jamais bloquées -----------------------
async def test_normal_requests_below_threshold_are_allowed(client: AsyncClient) -> None:
    data = await register_school(client, "fprlok")
    email = data["user"]["email"]
    await _clear_key(email)

    for _ in range(settings.forgot_password_rate_limit_max_attempts):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 202


# --- 2 — dépassement de limite : 429 --------------------------------------------------------------
async def test_threshold_exceeded_returns_429(client: AsyncClient) -> None:
    data = await register_school(client, "fprlexceed")
    email = data["user"]["email"]
    await _clear_key(email)

    for _ in range(settings.forgot_password_rate_limit_max_attempts):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 202

    blocked = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


# --- 3 — fenêtre de limitation : expire puis autorise de nouveau -------------------------------
async def test_rate_limit_window_expires_and_requests_succeed_again(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "forgot_password_rate_limit_max_attempts", 2)
    monkeypatch.setattr(settings, "forgot_password_rate_limit_window_seconds", 1)

    data = await register_school(client, "fprlwindow")
    email = data["user"]["email"]
    await _clear_key(email)

    for _ in range(2):
        await client.post("/api/v1/auth/forgot-password", json={"email": email})
    blocked = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert blocked.status_code == 429

    await asyncio.sleep(1.5)

    recovered = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert recovered.status_code == 202


# --- 4 — compte existant : rate limité comme n'importe quel autre email -------------------------
async def test_existing_account_is_rate_limited(client: AsyncClient) -> None:
    data = await register_school(client, "fprlreal")
    email = data["user"]["email"]
    await _clear_key(email)

    for _ in range(settings.forgot_password_rate_limit_max_attempts):
        await client.post("/api/v1/auth/forgot-password", json={"email": email})
    blocked = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert blocked.status_code == 429


# --- 5 — compte inexistant : même comptage, même code -------------------------------------------
async def test_nonexistent_account_is_rate_limited_identically(client: AsyncClient) -> None:
    email = unique_email("fprlghost")
    await _clear_key(email)

    for _ in range(settings.forgot_password_rate_limit_max_attempts):
        response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
        assert response.status_code == 202  # même comportement que pour un compte réel

    blocked = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert blocked.status_code == 429


# --- 6 — absence de fuite d'information : réponse identique compte réel vs inexistant -----------
async def test_no_account_existence_leak(client: AsyncClient) -> None:
    data = await register_school(client, "fprlnoleak")
    real_email = data["user"]["email"]
    fake_email = unique_email("fprlnoleak-ghost")
    await _clear_key(real_email)
    await _clear_key(fake_email)

    real_response = await client.post("/api/v1/auth/forgot-password", json={"email": real_email})
    fake_response = await client.post("/api/v1/auth/forgot-password", json={"email": fake_email})
    assert real_response.status_code == fake_response.status_code == 202
    assert real_response.json()["detail"] == fake_response.json()["detail"]
    # dev_token distingue déjà compte réel/inexistant (comportement existant, hors périmètre du
    # rate limiting) — seul le comportement de LIMITATION doit être identique, vérifié ici via
    # un comptage strictement égal (test suivant) plutôt que le contenu de dev_token.


# --- 7 — Redis indisponible : fail-open, jamais de blocage -----------------------------------------
async def test_redis_unavailable_fails_open(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Pointe le client partagé vers un Redis injoignable (port fermé) : chaque opération lève
    une RedisError réelle (erreur de connexion), capturée par le fail-open déjà en place — la
    requête doit malgré tout aboutir en 202, jamais en 429 ni en erreur serveur."""
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    email = unique_email("fprlredisdown")
    response = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert response.status_code == 202


# --- 8/9 — non-régression login / reset-password (voir aussi test_auth_rate_limit.py, test_auth.py) --
async def test_login_rate_limiting_still_works_independently(client: AsyncClient) -> None:
    """Le rate limiting login (Phase 7.2, clé distincte) n'est ni cassé ni affecté par celui de
    forgot-password — suite complète déjà couverte par test_auth_rate_limit.py, revérifiée ici
    au minimum pour ce fichier spécifique."""
    data = await register_school(client, "fprlloginok")
    email = data["user"]["email"]

    for _ in range(settings.login_rate_limit_max_attempts - 1):
        response = await client.post("/api/v1/auth/login", json={"email": email, "password": "wrong"})
        assert response.status_code == 401
    ok = await client.post("/api/v1/auth/login", json={"email": email, "password": "SuperSecret123"})
    assert ok.status_code == 200


async def test_reset_password_flow_still_works_after_rate_limited_request_window(client: AsyncClient) -> None:
    """Le flux reset-password (token -> nouveau mot de passe -> connexion) reste inchangé : une
    seule demande forgot-password (bien sous la limite) suffit toujours à obtenir un dev_token
    exploitable, comme avant cette phase (voir aussi test_auth.py::test_password_reset_flow)."""
    data = await register_school(client, "fprlresetok")
    email = data["user"]["email"]
    await _clear_key(email)

    forgot = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 202
    dev_token = forgot.json()["dev_token"]
    assert dev_token

    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": dev_token, "new_password": "BrandNewPass1"}
    )
    assert reset.status_code == 204

    login = await client.post("/api/v1/auth/login", json={"email": email, "password": "BrandNewPass1"})
    assert login.status_code == 200
