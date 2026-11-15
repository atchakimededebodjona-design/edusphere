"""Phase 29, lot B — connecteur PayGate Global (méthode directe), sans réseau ni base de données.

Le transport HTTP est remplacé par une fonction qui enregistre la requête et renvoie une réponse
choisie : on vérifie l'URL, le corps envoyé, l'interprétation des réponses, et que la clé API
n'apparaît jamais dans les journaux.
"""

import json
import logging
import urllib.error
from decimal import Decimal

import pytest

from app.core.config import Settings, validate_production_config, ProductionConfigError
from app.core.online_payment import FakeOnlinePaymentProvider, InitiationResult, PayGateProvider

TOKEN = "jeton-secret-de-test-0123456789"


class Transport:
    def __init__(self, status: int = 200, body: object = None, raw: bytes | None = None, error: Exception | None = None):
        self.status = status
        self.body = body
        self.raw = raw
        self.error = error
        self.calls: list[tuple[str, dict, float]] = []

    def __call__(self, url: str, payload: dict, timeout: float) -> tuple[int, bytes]:
        self.calls.append((url, payload, timeout))
        if self.error is not None:
            raise self.error
        if self.raw is not None:
            return self.status, self.raw
        return self.status, json.dumps(self.body).encode("utf-8")


def _provider(transport: Transport) -> PayGateProvider:
    return PayGateProvider(auth_token=TOKEN, base_url="https://paygateglobal.com/", timeout_seconds=7, post_json=transport)


async def _initiate(provider: PayGateProvider) -> InitiationResult:
    return await provider.initiate(
        identifier="ELABC123", amount=30000, phone_number="90123456", network="TMONEY", description="Abonnement EduLinkage"
    )


async def test_initiate_sends_the_documented_request_and_reads_the_reference() -> None:
    transport = Transport(body={"tx_reference": "PG-7781", "status": 0})
    result = await _initiate(_provider(transport))
    assert result == InitiationResult(accepted=True, tx_reference="PG-7781", code="0")
    url, payload, timeout = transport.calls[0]
    assert url == "https://paygateglobal.com/api/v1/pay"
    assert payload == {
        "auth_token": TOKEN,
        "phone_number": "90123456",
        "amount": 30000,
        "description": "Abonnement EduLinkage",
        "identifier": "ELABC123",
        "network": "TMONEY",
    }
    assert timeout == 7


@pytest.mark.parametrize(
    ("transport", "accepted", "code"),
    [
        (Transport(body={"status": "0", "tx_reference": 99}), True, "0"),
        (Transport(body={"status": 2}), False, "2"),  # clé API refusée
        (Transport(body={"status": 4}), False, "4"),  # paramètres invalides
        (Transport(body={"status": 6}), None, "6"),  # doublon : une transaction existe peut-être
        (Transport(body={"status": "?"}), None, "UNKNOWN"),
        (Transport(status=500, body={}), None, "HTTP_500"),
        (Transport(status=401, body={}), False, "HTTP_401"),
        (Transport(status=429, body={}), None, "HTTP_429"),
        (Transport(raw=b"<html>"), None, "INVALID_RESPONSE"),
        (Transport(body=["liste"]), None, "INVALID_RESPONSE"),
        (Transport(error=TimeoutError()), None, "TIMEOUT"),
        (Transport(error=urllib.error.URLError(TimeoutError())), None, "TIMEOUT"),
        (Transport(error=urllib.error.URLError("refused")), None, "NETWORK_ERROR"),
        (Transport(error=ConnectionResetError()), None, "NETWORK_ERROR"),
    ],
)
async def test_initiate_never_reports_a_false_failure(transport: Transport, accepted: bool | None, code: str) -> None:
    result = await _initiate(_provider(transport))
    assert (result.accepted, result.code) == (accepted, code)


@pytest.mark.parametrize(
    ("body", "state", "code"),
    [
        ({"status": 0, "tx_reference": "PG-1", "payment_reference": "FL-9", "payment_method": "FLOOZ"}, "SUCCEEDED", "0"),
        ({"status": 2}, "PENDING", "2"),
        ({"status": 4}, "EXPIRED", "4"),
        ({"status": 6}, "CANCELLED", "6"),
        ({"status": 9}, "UNKNOWN", "9"),
        ({"message": "not found"}, "UNKNOWN", "UNKNOWN"),
        ({"status": 0, "identifier": "AUTRE"}, "UNKNOWN", "ID_MISMATCH"),
    ],
)
async def test_check_status_maps_the_documented_codes(body: dict, state: str, code: str) -> None:
    transport = Transport(body=body)
    result = await _provider(transport).check_status(identifier="ELABC123")
    assert (result.state, result.code) == (state, code)
    url, payload, _ = transport.calls[0]
    assert url == "https://paygateglobal.com/api/v2/status"
    assert payload == {"auth_token": TOKEN, "identifier": "ELABC123"}


async def test_check_status_reads_optional_fields() -> None:
    body = {"status": 0, "tx_reference": "PG-1", "payment_reference": "FL-9", "payment_method": "T-Money", "amount": "30000"}
    result = await _provider(Transport(body=body)).check_status(identifier="ELABC123")
    assert result.tx_reference == "PG-1" and result.payment_reference == "FL-9" and result.payment_method == "T-Money"
    assert result.amount == Decimal("30000")
    absent = await _provider(Transport(body={"status": 0})).check_status(identifier="ELABC123")
    assert absent.amount is None


async def test_the_api_key_never_reaches_the_logs(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    for transport in (
        Transport(body={"status": 2}),
        Transport(status=403, body={"auth_token": TOKEN}),
        Transport(raw=TOKEN.encode()),
        Transport(error=TimeoutError(TOKEN)),
        Transport(error=urllib.error.URLError(TOKEN)),
    ):
        await _initiate(_provider(transport))
        await _provider(transport).check_status(identifier="ELABC123")
    assert caplog.records, "les erreurs doivent être journalisées"
    assert TOKEN not in caplog.text


async def test_fake_provider_is_pending_until_a_test_decides() -> None:
    fake = FakeOnlinePaymentProvider()
    accepted = await fake.initiate(identifier="ELX", amount=1000, phone_number="90123456", network="FLOOZ", description="d")
    assert accepted.accepted is True
    assert (await fake.check_status(identifier="ELX")).state == "PENDING"
    fake.set_status("ELX", "SUCCEEDED", amount=Decimal("1000"))
    assert (await fake.check_status(identifier="ELX")).state == "SUCCEEDED"
    fake.next_initiation = InitiationResult(accepted=False, tx_reference=None, code="4")
    refused = await fake.initiate(identifier="ELY", amount=1000, phone_number="90123456", network="FLOOZ", description="d")
    assert refused.accepted is False and (await fake.check_status(identifier="ELY")).state == "UNKNOWN"


# --- Contrôle de démarrage en production ---------------------------------------------------------
def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "jwt_secret_key": "s" * 48,
        "database_url": "postgresql+asyncpg://owner:pw@db:5432/edusphere",
        "app_database_url": "postgresql+asyncpg://edusphere_app:pw@db:5432/edusphere",
        "cors_allowed_origins": "https://edulinkage.com",
        "public_base_url": "https://api.edulinkage.com",
        "public_web_base_url": "https://edulinkage.com",
        "email_provider": "smtp",
        "smtp_username": "user",
        "smtp_password": "password",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


def test_production_refuses_online_payment_without_paygate_and_token() -> None:
    validate_production_config(_production_settings())  # coupe-circuit inactif : rien d'exigé
    with pytest.raises(ProductionConfigError, match="PAYMENT_ONLINE_PROVIDER=paygate"):
        validate_production_config(_production_settings(subscription_online_payment_enabled=True))
    with pytest.raises(ProductionConfigError, match="PAYGATE_AUTH_TOKEN") as refused:
        validate_production_config(
            _production_settings(subscription_online_payment_enabled=True, payment_online_provider="paygate")
        )
    assert TOKEN not in str(refused.value)
    validate_production_config(
        _production_settings(
            subscription_online_payment_enabled=True, payment_online_provider="paygate", paygate_auth_token=TOKEN
        )
    )
