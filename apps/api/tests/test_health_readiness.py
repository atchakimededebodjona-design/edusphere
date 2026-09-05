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


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_returns_200_when_all_dependencies_available(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == {"database": "ok", "redis": "ok", "storage": "ok"}


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
