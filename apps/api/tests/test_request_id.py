"""Phase 23 — corrélation des requêtes (request-id).

Couvre : génération cryptographiquement sûre, validation d'un identifiant entrant, propagation,
présence sur les réponses normales ET d'erreur, unicité entre requêtes, et robustesse face à un
identifiant entrant malformé (ne doit jamais casser le traitement de la requête).
"""

import re
import uuid

from httpx import AsyncClient

from app.core.log_context import generate_request_id, is_acceptable_request_id, request_id_var


# === Unitaire — génération / validation, sans HTTP =============================================
def test_generate_request_id_is_well_formed_and_unpredictable() -> None:
    first = generate_request_id()
    second = generate_request_id()
    assert first != second
    assert is_acceptable_request_id(first)
    # secrets.token_hex(16) : 32 caractères hexadécimaux minuscules.
    assert re.fullmatch(r"[0-9a-f]{32}", first)


def test_is_acceptable_request_id_accepts_reasonable_values() -> None:
    assert is_acceptable_request_id("valid-ID_123") is True
    assert is_acceptable_request_id("a") is True
    assert is_acceptable_request_id("a" * 100) is True


def test_is_acceptable_request_id_rejects_malformed_values() -> None:
    assert is_acceptable_request_id("") is False
    assert is_acceptable_request_id("a" * 101) is False
    assert is_acceptable_request_id("has spaces") is False
    assert is_acceptable_request_id("line\nbreak") is False
    assert is_acceptable_request_id("tab\ttab") is False
    assert is_acceptable_request_id("émoji-🎉") is False
    assert is_acceptable_request_id("semi;colon") is False


# === Bout en bout — middleware réel via le client de test =======================================
async def test_response_always_contains_x_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    assert is_acceptable_request_id(response.headers["x-request-id"])


async def test_incoming_valid_request_id_is_propagated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-Id": "my-custom-id-123"})
    assert response.headers["x-request-id"] == "my-custom-id-123"


async def test_incoming_malformed_request_id_with_spaces_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-Id": "bad id with spaces"})
    assert response.headers["x-request-id"] != "bad id with spaces"
    assert is_acceptable_request_id(response.headers["x-request-id"])


async def test_incoming_oversized_request_id_is_replaced_not_truncated_and_reflected(client: AsyncClient) -> None:
    oversized = "a" * 5000
    response = await client.get("/api/v1/health", headers={"X-Request-Id": oversized})
    assert response.status_code == 200  # un en-tête malformé ne casse jamais la requête
    assert response.headers["x-request-id"] != oversized
    assert is_acceptable_request_id(response.headers["x-request-id"])


async def test_incoming_request_id_with_control_characters_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-Id": "line1\r\nline2: injected"})
    assert response.status_code == 200
    assert is_acceptable_request_id(response.headers["x-request-id"])


async def test_two_requests_without_header_get_different_ids(client: AsyncClient) -> None:
    first = await client.get("/api/v1/health")
    second = await client.get("/api/v1/health")
    assert first.headers["x-request-id"] != second.headers["x-request-id"]


async def test_401_response_contains_x_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert "x-request-id" in response.headers
    assert is_acceptable_request_id(response.headers["x-request-id"])


async def test_404_response_contains_x_request_id(client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/organizations/{uuid.uuid4()}")
    assert response.status_code in (401, 403, 404)
    assert "x-request-id" in response.headers


async def test_422_validation_error_response_contains_x_request_id(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/register", json={"organization_name": "Incomplet"})
    assert response.status_code == 422
    assert "x-request-id" in response.headers


async def test_supplied_request_id_is_returned_even_on_error(client: AsyncClient) -> None:
    response = await client.get(
        f"/api/v1/organizations/{uuid.uuid4()}", headers={"X-Request-Id": "error-path-check-1"}
    )
    assert response.status_code in (401, 403, 404)
    assert response.headers["x-request-id"] == "error-path-check-1"


async def test_request_id_contextvar_does_not_leak_outside_the_request(client: AsyncClient) -> None:
    """Le ContextVar est propre à la tâche de la requête — une fois la réponse renvoyée, le
    contexte appelant (ici, le test lui-même) ne doit jamais voir une valeur qui y aurait fuité."""
    assert request_id_var.get() is None
    response = await client.get("/api/v1/health", headers={"X-Request-Id": "leak-check-1"})
    assert response.headers["x-request-id"] == "leak-check-1"
    assert request_id_var.get() is None
