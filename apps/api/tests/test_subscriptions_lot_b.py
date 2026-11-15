"""Phase 29, lot B — paiement des abonnements par Mobile Money (PayGate Global, méthode directe).

Avec `FakeOnlinePaymentProvider` (aucun appel réseau) : lancement, confirmation par la notification
ou par la tâche de rapprochement, notification falsifiée, montant différent, notification répétée
ou simultanée avec la tâche, succès tardif, double paiement, coupe-circuit, plafond, idempotence,
droits et isolation (cadrage §15).

Écrit pour fonctionner dans la CI (base partagée par toute la suite) : chaque test crée ses propres
écoles et ne compte que ses propres lignes.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.online_payment import FakeOnlinePaymentProvider, InitiationResult, fake_online_payment_provider
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.subscriptions.models import PAYMENT_CODE_LOCAL_TIMEOUT, SubscriptionPayment
from app.modules.subscriptions.online_payments import ReconcileResult, check_payment, reconcile_online_payments
from app.modules.subscriptions.reminders import run_subscription_reminders
from tests.test_fees import _create_user_with_role
from tests.test_subscriptions import API, _active_grid, _audit_actions, _issue, _key, _owner, _pay, _school

PHONE = "90 12 34 56"


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeOnlinePaymentProvider:
    monkeypatch.setattr(settings, "subscription_online_payment_enabled", True)
    monkeypatch.setattr(settings, "payment_online_provider", "fake")
    fake_online_payment_provider.next_initiation = None
    return fake_online_payment_provider


# --- Helpers -----------------------------------------------------------------------------------
async def _setup(client: AsyncClient, prefix: str) -> tuple[dict, dict, dict]:
    owner = await _owner(client, prefix)
    await _active_grid(client, owner["headers"])
    data = await _school(client, prefix)
    issued = await _issue(client, data)
    assert issued.status_code == 201, issued.text
    return owner, data, issued.json()


async def _start(client: AsyncClient, data: dict, invoice: dict, *, network: str = "FLOOZ", phone: str = PHONE, key: str | None = None):
    return await client.post(
        f"{API}/school-subscription/invoices/{invoice['id']}/payments",
        json={"network": network, "phone_number": phone, "idempotency_key": key or _key()},
        headers=data["headers"],
    )


async def _started(client: AsyncClient, data: dict, invoice: dict, **kwargs) -> dict:
    response = await _start(client, data, invoice, **kwargs)
    assert response.status_code == 201, response.text
    return response.json()


async def _row(payment_id: str) -> SubscriptionPayment:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return (await db.execute(select(SubscriptionPayment).where(SubscriptionPayment.id == uuid.UUID(payment_id)))).scalar_one()


async def _scalar(sql: str, **params):
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        return await db.scalar(text(sql), params)


async def _execute(sql: str, **params) -> None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(text(sql), params)
        await db.commit()


async def _invoice_status(invoice: dict) -> str:
    return await _scalar("SELECT status FROM subscription_invoices WHERE id = :i", i=uuid.UUID(invoice["id"]))


async def _paid_periods(invoice: dict) -> int:
    return await _scalar("SELECT count(*) FROM school_subscription_periods WHERE invoice_id = :i", i=uuid.UUID(invoice["id"]))


async def _age(payment_id: str, interval: str) -> None:
    await _execute(
        f"UPDATE subscription_payments SET created_at = created_at - interval '{interval}' WHERE id = :p",
        p=uuid.UUID(payment_id),
    )


async def _reconcile() -> ReconcileResult:
    async with AsyncSessionLocal() as db:
        return await reconcile_online_payments(db)


async def _callback(client: AsyncClient, identifier: str | None, **extra):
    payload = {"identifier": identifier, "tx_reference": f"PG-{uuid.uuid4().hex[:8]}", "amount": "30000", "payment_method": "FLOOZ", **extra}
    response = await client.post(f"{API}/payment-providers/paygate/callback", json=payload)
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    return response


async def _callback_results(identifier: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = await db.execute(
            text("SELECT result FROM payment_provider_callbacks WHERE identifier = :i ORDER BY received_at"), {"i": identifier}
        )
        return [row[0] for row in rows.all()]


# --- Coupe-circuit, validation ------------------------------------------------------------------
async def test_online_payment_is_off_by_default(client: AsyncClient) -> None:
    _, data, invoice = await _setup(client, "lotboff")
    subscription = (await client.get(f"{API}/school-subscription?school_id={data['school']['id']}", headers=data["headers"])).json()
    assert subscription["online_payment_enabled"] is False
    refused = await _start(client, data, invoice)
    assert refused.status_code == 409 and "not available" in refused.json()["detail"]


async def test_invalid_phone_numbers_are_rejected(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbphone")
    for phone in ("12345", "+33 6 12 34 56 78", "abcdefghij"):
        assert (await _start(client, data, invoice, phone=phone)).status_code == 422, phone
    accepted = await _started(client, data, invoice, phone="+228 90-12-34-56", network="TMONEY")
    assert accepted["payer_phone_last4"] == "3456" and accepted["method"] == "TMONEY"
    assert fake.initiations[-1]["phone_number"] == "90123456" and fake.initiations[-1]["network"] == "TMONEY"


# --- Confirmation ----------------------------------------------------------------------------------
async def test_success_confirmed_by_the_callback_only_once(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbcb")
    subscription = (await client.get(f"{API}/school-subscription?school_id={data['school']['id']}", headers=data["headers"])).json()
    assert subscription["online_payment_enabled"] is True and subscription["online_payment_max_amount"] == settings.paygate_max_amount

    payment = await _started(client, data, invoice)
    assert payment["status"] == "PENDING" and payment["amount"] == invoice["total_amount"]
    assert payment["payer_phone_last4"] == "3456" and "identifier" not in payment
    row = await _row(payment["id"])
    assert fake.initiations[-1] == {"identifier": row.identifier, "amount": 30000, "phone_number": "90123456", "network": "FLOOZ"}

    fake.set_status(row.identifier, "SUCCEEDED")
    await _callback(client, row.identifier)
    assert await _invoice_status(invoice) == "PAID"
    assert await _paid_periods(invoice) == 1
    confirmed = await _row(payment["id"])
    assert confirmed.status == "SUCCEEDED" and confirmed.confirmed_at is not None
    assert confirmed.payment_reference is not None and confirmed.tx_reference == f"FAKE-{row.identifier}"

    await _callback(client, row.identifier)  # notification répétée : sans effet
    assert await _paid_periods(invoice) == 1
    assert await _callback_results(row.identifier) == ["CHECK_SCHEDULED", "NOT_IN_PROGRESS"]

    actions = await _audit_actions(data["school"]["id"])
    assert "subscription_payment.online_initiated" in actions and "subscription_payment.confirmed" in actions
    notified = await _scalar(
        "SELECT count(*) FROM notifications WHERE school_id = :s AND type = 'SUBSCRIPTION_PAYMENT_CONFIRMED' AND recipient_user_id = :u",
        s=uuid.UUID(data["school"]["id"]),
        u=uuid.UUID(data["user"]["id"]),
    )
    assert notified == 1
    receipt = await client.get(f"{API}/school-subscription/invoices/{invoice['id']}/receipt.pdf", headers=data["headers"])
    assert receipt.status_code == 200 and receipt.content.startswith(b"%PDF")


async def test_success_confirmed_by_the_reconciliation_job_without_callback(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbjob")
    payment = await _started(client, data, invoice)
    row = await _row(payment["id"])
    fake.set_status(row.identifier, "SUCCEEDED")
    await _age(payment["id"], "2 minutes")
    result = await _reconcile()
    assert result.enabled and result.errors == 0
    assert (await _row(payment["id"])).status == "SUCCEEDED"
    assert await _invoice_status(invoice) == "PAID" and await _paid_periods(invoice) == 1


async def test_school_screen_refresh_confirms_and_shows_the_attempt(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbscreen")
    payment = await _started(client, data, invoice)
    url = f"{API}/school-subscription/payments/{payment['id']}"
    pending = await client.get(url, headers=data["headers"])
    assert pending.status_code == 200 and pending.json()["status"] == "PENDING"
    fake.set_status((await _row(payment["id"])).identifier, "SUCCEEDED")
    await _execute("UPDATE subscription_payments SET last_checked_at = now() - interval '1 minute' WHERE id = :p", p=uuid.UUID(payment["id"]))
    done = await client.get(url, headers=data["headers"])
    assert done.json()["status"] == "SUCCEEDED" and await _invoice_status(invoice) == "PAID"
    detail = (await client.get(f"{API}/school-subscription/invoices/{invoice['id']}", headers=data["headers"])).json()
    assert [(p["provider"], p["status"], p["payer_phone_last4"]) for p in detail["payments"]] == [("PAYGATE", "SUCCEEDED", "3456")]


# --- Notifications falsifiées et cas anormaux --------------------------------------------------------
async def test_forged_callbacks_never_confirm_anything(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbforged")
    payment = await _started(client, data, invoice)
    row = await _row(payment["id"])

    unknown = f"EL{uuid.uuid4().hex[:20].upper()}"
    await _callback(client, unknown)
    await _callback(client, row.identifier, amount="30000")  # PayGate dit encore « en cours »
    malformed = await client.post(
        f"{API}/payment-providers/paygate/callback", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert malformed.status_code == 200 and malformed.json() == {"status": "ok"}

    assert (await _row(payment["id"])).status == "PENDING"
    assert await _invoice_status(invoice) == "ISSUED" and await _paid_periods(invoice) == 0
    assert await _callback_results(unknown) == ["UNKNOWN_IDENTIFIER"]
    assert await _callback_results(row.identifier) == ["CHECK_SCHEDULED"]

    # Le journal des notifications est réservé à la plateforme (RLS), même pour l'école concernée.
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(data["user"]["id"]))
        assert await db.scalar(text("SELECT count(*) FROM payment_provider_callbacks")) == 0


async def test_amount_mismatch_is_an_anomaly(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbamount")
    payment = await _started(client, data, invoice)
    fake.set_status((await _row(payment["id"])).identifier, "SUCCEEDED", amount=Decimal("100"))
    checked = await client.get(f"{API}/school-subscription/payments/{payment['id']}", headers=data["headers"])
    assert checked.json()["status"] == "ANOMALY"
    assert await _invoice_status(invoice) == "ISSUED" and await _paid_periods(invoice) == 0
    assert "subscription_payment.anomaly" in await _audit_actions(data["school"]["id"])


async def test_simultaneous_callback_job_and_screen_create_a_single_period(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbrace")
    payment = await _started(client, data, invoice)
    row = await _row(payment["id"])
    fake.set_status(row.identifier, "SUCCEEDED")
    await _age(payment["id"], "2 minutes")

    async def direct_check() -> None:
        async with AsyncSessionLocal() as db:
            await set_platform_wide_context(db)
            await check_payment(db, uuid.UUID(payment["id"]))

    await asyncio.gather(_callback(client, row.identifier), _reconcile(), direct_check(), direct_check())
    assert (await _row(payment["id"])).status == "SUCCEEDED"
    assert await _invoice_status(invoice) == "PAID" and await _paid_periods(invoice) == 1


async def test_late_success_after_a_local_timeout_is_still_confirmed(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotblate")
    payment = await _started(client, data, invoice)
    row = await _row(payment["id"])
    await _age(payment["id"], "20 minutes")
    await _reconcile()  # toujours « en cours » chez PayGate, au-delà du délai : close localement
    closed = await _row(payment["id"])
    assert closed.status == "EXPIRED" and closed.provider_status_code == PAYMENT_CODE_LOCAL_TIMEOUT
    assert await _invoice_status(invoice) == "ISSUED"

    # Dernière vérification à J+1 par la tâche : le paiement a finalement abouti.
    fake.set_status(row.identifier, "SUCCEEDED")
    await _execute(
        "UPDATE subscription_payments SET created_at = now() - interval '25 hours', "
        "last_checked_at = now() - interval '24 hours 30 minutes' WHERE id = :p",
        p=uuid.UUID(payment["id"]),
    )
    await _reconcile()
    assert (await _row(payment["id"])).status == "SUCCEEDED"
    assert await _invoice_status(invoice) == "PAID" and await _paid_periods(invoice) == 1


async def test_success_on_an_already_paid_invoice_is_a_double_payment_anomaly(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    owner, data, invoice = await _setup(client, "lotbdouble")
    payment = await _started(client, data, invoice)
    row = await _row(payment["id"])
    await _age(payment["id"], "20 minutes")
    await _reconcile()
    assert (await _row(payment["id"])).status == "EXPIRED"
    manual = await _pay(client, owner["headers"], invoice)
    assert manual.status_code == 201, manual.text

    fake.set_status(row.identifier, "SUCCEEDED")
    await _callback(client, row.identifier)
    assert (await _row(payment["id"])).status == "ANOMALY"
    assert await _paid_periods(invoice) == 1
    assert "subscription_payment.anomaly" in await _audit_actions(data["school"]["id"])


# --- Lancement : refus, issue inconnue, idempotence, plafond ------------------------------------------
async def test_refusal_closes_the_attempt_and_allows_a_new_one(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbrefused")
    fake.next_initiation = InitiationResult(accepted=False, tx_reference=None, code="4")
    refused = await _started(client, data, invoice)
    assert refused["status"] == "FAILED"
    retry = await _started(client, data, invoice)
    assert retry["status"] == "PENDING" and retry["id"] != refused["id"]

    fake.next_initiation = None
    _, other, other_invoice = await _setup(client, "lotbunknown")
    fake.next_initiation = InitiationResult(accepted=None, tx_reference=None, code="TIMEOUT")
    unknown = await _started(client, other, other_invoice)
    assert unknown["status"] == "PENDING"
    assert (await _row(unknown["id"])).provider_status_code == "TIMEOUT"


async def test_idempotency_and_a_single_attempt_in_progress(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbidem")
    key = _key()
    first = await _started(client, data, invoice, key=key)
    again = await _started(client, data, invoice, key=key)
    other_key = await _started(client, data, invoice)
    assert first["id"] == again["id"] == other_key["id"]
    conflict = await _start(client, data, invoice, key=key, phone="91 00 00 01")
    assert conflict.status_code == 409
    count = await _scalar("SELECT count(*) FROM subscription_payments WHERE invoice_id = :i", i=uuid.UUID(invoice["id"]))
    assert count == 1


async def test_amount_above_the_online_limit_requires_a_manual_payment(
    client: AsyncClient, fake: FakeOnlinePaymentProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, data, invoice = await _setup(client, "lotbmax")
    monkeypatch.setattr(settings, "paygate_max_amount", 1000)
    refused = await _start(client, data, invoice)
    assert refused.status_code == 409 and "limit" in refused.json()["detail"]


# --- Interactions avec le reste du cycle de la facture ----------------------------------------------
async def test_attempt_in_progress_blocks_cancel_manual_payment_expiry_and_a_new_invoice(
    client: AsyncClient, fake: FakeOnlinePaymentProvider
) -> None:
    owner, data, invoice = await _setup(client, "lotbblock")
    await _started(client, data, invoice)
    cancel = await client.post(
        f"{API}/platform/subscription-invoices/{invoice['id']}/cancel", json={"reason": "test"}, headers=owner["headers"]
    )
    assert cancel.status_code == 409
    assert (await _pay(client, owner["headers"], invoice)).status_code == 409

    # Validité dépassée pendant la tentative : la tâche quotidienne n'expire pas la facture.
    await _execute("UPDATE subscription_invoices SET expires_at = now() - interval '1 minute' WHERE id = :i", i=uuid.UUID(invoice["id"]))
    async with AsyncSessionLocal() as db:
        await run_subscription_reminders(db, only_school_ids={uuid.UUID(data["school"]["id"])})
    assert await _invoice_status(invoice) == "ISSUED"
    blocked = await _issue(client, data)
    assert blocked.status_code == 409 and "being verified" in blocked.json()["detail"]


# --- Droits et isolation -----------------------------------------------------------------------------
async def test_permissions_and_isolation(client: AsyncClient, fake: FakeOnlinePaymentProvider) -> None:
    _, data, invoice = await _setup(client, "lotbrbac")
    other = await _school(client, "lotbrbacother")
    director = await _create_user_with_role(client, data["headers"], data["school"]["id"], "DIRECTOR", "lotbrbac.dir")
    teacher = await _create_user_with_role(client, data["headers"], data["school"]["id"], "TEACHER", "lotbrbac.teach")

    assert (await _start(client, director, invoice)).status_code == 403  # consultation seulement
    assert (await _start(client, other, invoice)).status_code == 404
    payment = await _started(client, data, invoice)
    url = f"{API}/school-subscription/payments/{payment['id']}"
    assert (await client.get(url, headers=director["headers"])).status_code == 200
    assert (await client.get(url, headers=teacher["headers"])).status_code == 403
    assert (await client.get(url, headers=other["headers"])).status_code == 404
