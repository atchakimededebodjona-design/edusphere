"""2026-11-24 — `GET /public/legal-identity` : identité de l'entreprise pour les pages juridiques.

Sans authentification, en lecture seule, lue dans la configuration du serveur (BILLING_*)."""

import pytest
from httpx import AsyncClient

from app.core.config import settings

URL = "/api/v1/public/legal-identity"


async def test_legal_identity_comes_from_the_server_configuration(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "billing_trade_name", "EduLinkage")
    monkeypatch.setattr(settings, "billing_legal_name", "Entreprise Essai SARL")
    monkeypatch.setattr(settings, "billing_address", "Rue de l'essai, Lomé")
    monkeypatch.setattr(settings, "billing_rccm", "TG-LFW-01-2026-B12-00001")
    monkeypatch.setattr(settings, "billing_nif", "1000000000")
    monkeypatch.setattr(settings, "billing_email", "contact@exemple.tg")

    response = await client.get(URL)  # aucun en-tête d'authentification
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "public, max-age=3600"
    body = response.json()
    assert set(body) == {"trade_name", "legal_name", "legal_form", "address", "nif", "rccm", "phone", "email"}
    assert body["legal_name"] == "Entreprise Essai SARL"
    assert body["rccm"] == "TG-LFW-01-2026-B12-00001"
    assert body["email"] == "contact@exemple.tg"


async def test_legal_identity_never_exposes_other_settings(client: AsyncClient) -> None:
    body = (await client.get(URL)).json()
    text = str(body)
    for secret in (settings.jwt_secret_key, settings.paygate_auth_token or "jamais-vide-ici"):
        if secret:
            assert secret not in text
