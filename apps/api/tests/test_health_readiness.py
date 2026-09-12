"""Tests health/readiness (Phase 16).

`GET /health` (liveness) et `GET /ready` (readiness — DB/Redis/storage) sont publics, sans
authentification, cohérent avec leur usage par un orchestrateur/Docker plutôt qu'un client
applicatif. Le chemin "tout fonctionne" est testé en conditions réelles (DB/Redis/storage
réellement disponibles dans cet environnement de test, pas mockés) ; les chemins d'échec par
dépendance sont testés par monkeypatch ciblé sur la fonction de vérification concernée — arrêter
réellement PostgreSQL/Redis pendant l'exécution de pytest casserait la majorité des autres tests
de cette suite, qui en ont besoin ; cette vérification-là est faite séparément, manuellement,
contre les conteneurs réels (voir docs/phases/PHASE_16_IMPLEMENTATION.md, section "Real-world
validation") — ne pas confondre les deux niveaux de preuve.
"""

import app.core.readiness as readiness_module
from httpx import AsyncClient

from app.core.config import settings


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_200_when_all_dependencies_available(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok", "redis": "ok", "storage": "ok", "email": "ok"}
    # Sprint 1.5 — champ informatif : reflète le provider réellement configuré dans cet
    # environnement (jamais fixé en dur ici, sinon ce test se déconnecterait silencieusement de
    # la vraie configuration dès qu'elle change).
    assert body["email_provider"] == settings.email_provider


async def test_ready_returns_503_when_database_check_fails(client: AsyncClient, monkeypatch) -> None:
    async def failing_check_database(db):
        return "error"

    monkeypatch.setattr(readiness_module, "_check_database", failing_check_database)

    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "error"
    # Les dépendances saines restent rapportées comme telles — un échec n'écrase pas les autres.
    assert body["checks"]["redis"] == "ok"
    assert body["checks"]["storage"] == "ok"


async def test_ready_returns_503_when_redis_check_fails(client: AsyncClient, monkeypatch) -> None:
    async def failing_check_redis():
        return "error"

    monkeypatch.setattr(readiness_module, "_check_redis", failing_check_redis)

    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "error"


async def test_ready_returns_503_when_storage_check_fails(client: AsyncClient, monkeypatch) -> None:
    async def failing_check_storage():
        return "error"

    monkeypatch.setattr(readiness_module, "_check_storage", failing_check_storage)

    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["storage"] == "error"


async def test_ready_returns_503_when_multiple_dependencies_fail(client: AsyncClient, monkeypatch) -> None:
    async def failing_check_database(db):
        return "error"

    async def failing_check_redis():
        return "error"

    monkeypatch.setattr(readiness_module, "_check_database", failing_check_database)
    monkeypatch.setattr(readiness_module, "_check_redis", failing_check_redis)

    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["checks"]["database"] == "error"
    assert body["checks"]["redis"] == "error"
    assert body["checks"]["storage"] == "ok"


async def test_ready_response_never_leaks_connection_strings_or_secrets(client: AsyncClient, monkeypatch) -> None:
    """Un message d'erreur technique (chaîne de connexion, identifiants) ne doit jamais
    apparaître dans le corps de la réponse — seules les valeurs "ok"/"error" sont exposées."""

    async def failing_check_database(db):
        raise ConnectionError("connection to server failed: password authentication failed for user \"edusphere_app\"")

    async def wrapped(db):
        try:
            return await failing_check_database(db)
        except Exception:
            return "error"

    monkeypatch.setattr(readiness_module, "_check_database", wrapped)

    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    assert "password" not in response.text
    assert "edusphere_app" not in response.text


# --- Sprint 1.5 — vérification de configuration email ------------------------------------------
async def test_ready_reports_ok_when_email_provider_is_local(client: AsyncClient, monkeypatch) -> None:
    """`EMAIL_PROVIDER=local` est une configuration valide et auto-cohérente (aucun envoi réel
    attendu) — ne doit jamais faire échouer la readiness, contrairement à un `smtp` mal
    configuré ci-dessous."""
    monkeypatch.setattr(settings, "email_provider", "local")

    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["email"] == "ok"
    assert body["email_provider"] == "local"


async def test_ready_returns_503_when_smtp_selected_without_credentials(client: AsyncClient, monkeypatch) -> None:
    """`EMAIL_PROVIDER=smtp` sans identifiants garantit l'échec de tout envoi — même sévérité
    qu'une base de données ou un Redis indisponible."""
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_username", "")
    monkeypatch.setattr(settings, "smtp_password", "")

    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["email"] == "error"
    # Les dépendances saines restent rapportées comme telles — un échec n'écrase pas les autres.
    assert body["checks"]["database"] == "ok"
    assert body["email_provider"] == "smtp"


async def test_ready_reports_ok_when_smtp_selected_with_credentials(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_username", "no-reply@example.tg")
    monkeypatch.setattr(settings, "smtp_password", "irrelevant-for-this-check")

    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json()["checks"]["email"] == "ok"
