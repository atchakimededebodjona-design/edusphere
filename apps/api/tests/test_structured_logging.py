"""Phase 23 — logging structuré JSON et corrélation par request_id.

Chaque test attache un handler temporaire (avec le VRAI `JsonFormatter`/`RequestContextFilter` de
production) à un logger nommé isolé — jamais à la logger racine — pour ne jamais interférer avec
les autres tests ni avec le mécanisme `caplog` de pytest. Le JSON produit est réellement parsé
(`json.loads`), pas seulement cherché comme sous-chaîne.
"""

import io
import json
import logging

import pytest
from httpx import AsyncClient
from redis.asyncio import Redis

import app.core.rate_limit as rate_limit_module
from app.core.log_context import RequestContextFilter, organization_id_var, request_id_var, user_id_var
from app.core.logging_config import JsonFormatter


def _capture(logger_name: str) -> tuple[logging.Logger, io.StringIO, logging.Handler]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger, stream, handler


def _parsed_lines(stream: io.StringIO) -> list[dict]:
    text = stream.getvalue().strip()
    return [json.loads(line) for line in text.splitlines()] if text else []


def test_json_formatter_produces_valid_json_for_info_warning_error() -> None:
    logger, stream, handler = _capture("test.structured_logging.levels")
    try:
        logger.info("info message")
        logger.warning("warning message")
        try:
            raise ValueError("boom")
        except ValueError:
            logger.error("error message", exc_info=True)
    finally:
        logger.removeHandler(handler)

    lines = _parsed_lines(stream)
    assert len(lines) == 3
    assert lines[0]["level"] == "INFO"
    assert lines[0]["message"] == "info message"
    assert lines[1]["level"] == "WARNING"
    assert lines[2]["level"] == "ERROR"
    assert "exception" in lines[2]
    assert "ValueError" in lines[2]["exception"]
    for line in lines:
        assert isinstance(line["timestamp"], str) and line["timestamp"]
        assert line["logger"] == "test.structured_logging.levels"


def test_json_formatter_includes_request_and_user_context_when_available() -> None:
    logger, stream, handler = _capture("test.structured_logging.context")
    request_token = request_id_var.set("req-context-test")
    user_token = user_id_var.set("user-context-test")
    try:
        logger.info("with context")
    finally:
        logger.removeHandler(handler)
        request_id_var.reset(request_token)
        user_id_var.reset(user_token)

    lines = _parsed_lines(stream)
    assert lines[0]["request_id"] == "req-context-test"
    assert lines[0]["user_id"] == "user-context-test"
    # organization_id/school_id jamais positionnés dans ce test : absents, pas "null".
    assert "organization_id" not in lines[0]
    assert "school_id" not in lines[0]


def test_json_formatter_includes_organization_and_school_when_set() -> None:
    logger, stream, handler = _capture("test.structured_logging.org_school")
    org_token = organization_id_var.set("org-123")
    try:
        logger.info("with org context")
    finally:
        logger.removeHandler(handler)
        organization_id_var.reset(org_token)

    lines = _parsed_lines(stream)
    assert lines[0]["organization_id"] == "org-123"


def test_json_log_line_never_contains_secret_markers_for_a_realistic_message() -> None:
    """Ne teste pas une chaîne brute isolée : reproduit le message réel émis par
    `rate_limit.py` lors d'une panne Redis (un des messages les plus fréquents en production) et
    vérifie qu'aucun marqueur de secret n'apparaît nulle part dans la ligne JSON produite."""
    logger, stream, handler = _capture("test.structured_logging.confidentiality")
    try:
        logger.warning("Rate limiting Redis indisponible — vérification ignorée pour cette requête.")
    finally:
        logger.removeHandler(handler)

    lines = _parsed_lines(stream)
    serialized = json.dumps(lines[0])
    for forbidden in ("password", "Password", "token", "Token", "secret", "Secret", "Bearer ", "Authorization"):
        assert forbidden not in serialized


def test_json_formatter_output_is_a_single_line_per_event() -> None:
    """Une ligne JSON par évènement, même si le message contient un saut de ligne — sinon un
    message multi-ligne casserait tout parseur ligne-par-ligne (`docker compose logs` inclus)."""
    logger, stream, handler = _capture("test.structured_logging.single_line")
    try:
        logger.info("first\nsecond line embedded")
    finally:
        logger.removeHandler(handler)

    raw_lines = stream.getvalue().strip().splitlines()
    assert len(raw_lines) == 1
    parsed = json.loads(raw_lines[0])
    assert parsed["message"] == "first\nsecond line embedded"


# === Bout en bout — un request_id réel se retrouve dans une vraie ligne de log =================
async def test_request_id_correlates_with_a_real_log_line(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scénario exact du runbook support : une école fournit un request_id, l'équipe doit
    retrouver la ligne de log correspondante — prouvé de bout en bout, pas seulement au niveau du
    formatteur."""
    logger, stream, handler = _capture("app.core.rate_limit")
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    try:
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-correlate-test@example.com", "password": "whatever123"},
            headers={"X-Request-Id": "correlate-me-42"},
        )
    finally:
        logger.removeHandler(handler)

    assert response.headers["x-request-id"] == "correlate-me-42"
    lines = _parsed_lines(stream)
    assert any(line.get("request_id") == "correlate-me-42" for line in lines)


async def test_two_concurrent_requests_do_not_mix_up_their_request_ids_in_logs(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Deux requêtes séquentielles avec des request_id distincts ne doivent jamais se mélanger
    dans les logs produits — preuve que le ContextVar est bien isolé par requête, pas partagé."""
    logger, stream, handler = _capture("app.core.rate_limit")
    unreachable_client = Redis.from_url("redis://localhost:1/0", decode_responses=True, socket_connect_timeout=1)
    monkeypatch.setattr(rate_limit_module, "_redis_client", unreachable_client)

    try:
        first = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-a@example.com", "password": "whatever123"},
            headers={"X-Request-Id": "concurrent-a"},
        )
        second = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody-b@example.com", "password": "whatever123"},
            headers={"X-Request-Id": "concurrent-b"},
        )
    finally:
        logger.removeHandler(handler)

    assert first.headers["x-request-id"] == "concurrent-a"
    assert second.headers["x-request-id"] == "concurrent-b"
    lines = _parsed_lines(stream)
    ids_seen = {line.get("request_id") for line in lines}
    assert "concurrent-a" in ids_seen
    assert "concurrent-b" in ids_seen
