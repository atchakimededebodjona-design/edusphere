"""Tarifs publics de la page d'accueil (2026-11-16) : `GET /public/subscription-pricing`.

Route sans authentification et en lecture seule. Elle donne les montants de la grille ACTIVE et les
bornes des tranches, sans identifiant ni libellé de grille, et sans aucune donnée d'école.
"""

import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.modules.subscriptions import pricing
from tests.test_security_hardening import _clear_pattern
from tests.test_subscriptions import API, _active_grid, _owner

URL = f"{API}/public/subscription-pricing"


async def test_public_pricing_exposes_only_the_active_grid_amounts(client: AsyncClient) -> None:
    owner = await _owner(client, "pubprice")
    active = await _active_grid(client, owner["headers"], base_delta=1000)

    response = await client.get(URL)  # aucun en-tête d'authentification
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=300"
    body = response.json()
    assert set(body) == {"currency", "tiers", "step_students", "periods"}
    assert body["currency"] == "XOF"
    assert body["step_students"] == pricing.STEP_STUDENTS
    assert body["tiers"] == [
        {"tier": t.number, "min_students": t.min_students, "max_students": t.max_students} for t in pricing.TIERS
    ]
    # Les montants sont exactement ceux de la grille qui vient d'être activée.
    assert body["periods"] == active["periods"]
    assert "id" not in body and "label" not in body


async def test_public_pricing_is_rate_limited(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "public_pricing_rate_limit_max_attempts", 2)
    await _clear_pattern("public_pricing_attempts:*")
    for _ in range(2):
        assert (await client.get(URL)).status_code == 200
    blocked = await client.get(URL)
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers
    await _clear_pattern("public_pricing_attempts:*")
