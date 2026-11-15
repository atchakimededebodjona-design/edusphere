"""Commissions des partenaires (migration 0031, décisions du 2026-11-15).

Un partenaire touche son taux (20 % par défaut, réglable par partenaire) du montant HT de chaque
facture d'abonnement payée et confirmée d'une école qu'il a inscrite ; rien pendant une suspension ;
versement manuel par la plateforme. Écrit pour la CI (base partagée) : chaque test crée ses
propres partenaires et écoles et ne compte que ses propres lignes.
"""

import asyncio
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.core.config import settings
from app.core.online_payment import FakeOnlinePaymentProvider, fake_online_payment_provider
from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.commissions.models import PartnerCommission
from app.modules.commissions.service import commission_amount
from app.modules.subscriptions import pricing
from app.modules.subscriptions.models import SubscriptionPayment
from app.modules.subscriptions.online_payments import reconcile_online_payments
from tests.conftest import register_school
from tests.pr17_helpers import auth, create_partner, enroll_school_as_partner
from tests.test_subscriptions import API, BASES, _active_grid, _audit_actions, _issue, _owner, _pay

PHONE = "90 12 34 56"


# --- Helpers -----------------------------------------------------------------------------------
async def _partner_school(client: AsyncClient, owner: dict, prefix: str, partner: dict | None = None) -> tuple[dict, dict]:
    partner = partner or await create_partner(client, owner["headers"], f"{prefix}p")
    body = await enroll_school_as_partner(client, partner["headers"], f"{prefix}s")
    assert body["commission_eligible"] is True
    data = {"school": body["school"], "organization": body["organization"], "user": body["admin"], "headers": body["admin_headers"]}
    return partner, data


async def _issue_and_pay(client: AsyncClient, owner: dict, data: dict, months: int = 3) -> dict:
    issued = await _issue(client, data, months=months)
    assert issued.status_code == 201, issued.text
    paid = await _pay(client, owner["headers"], issued.json())
    assert paid.status_code == 201, paid.text
    return paid.json()


async def _commissions_for_school(school_id: str) -> list[PartnerCommission]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = await db.execute(
            select(PartnerCommission).where(PartnerCommission.school_id == uuid.UUID(school_id)).order_by(PartnerCommission.created_at)
        )
        return list(rows.scalars())


async def _set_partner_status(partner: dict, status_value: str) -> None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(text("UPDATE partners SET status = :s WHERE id = :p"), {"s": status_value, "p": uuid.UUID(partner["partner"]["id"])})
        await db.commit()


# --- Calcul ---------------------------------------------------------------------------------------
def test_commission_is_computed_on_the_amount_excluding_vat() -> None:
    assert pricing.amount_excl_vat(Decimal("35400"), Decimal("18")) == Decimal("30000")
    assert pricing.amount_excl_vat(Decimal("30000"), None) == Decimal("30000")
    assert pricing.amount_excl_vat(Decimal("100"), Decimal("18")) == Decimal("85")  # 84,75 arrondi au franc
    assert commission_amount(Decimal("30000"), Decimal("20")) == Decimal("6000")
    assert commission_amount(Decimal("25424"), Decimal("20")) == Decimal("5085")  # 5 084,8 arrondi
    assert commission_amount(Decimal("30000"), Decimal("12.5")) == Decimal("3750")


# --- Création -------------------------------------------------------------------------------------
async def test_manual_payment_accrues_20_percent_for_the_partner(client: AsyncClient) -> None:
    owner = await _owner(client, "comman")
    await _active_grid(client, owner["headers"])
    partner, data = await _partner_school(client, owner, "comman")
    invoice = await _issue_and_pay(client, owner, data)

    commissions = await _commissions_for_school(data["school"]["id"])
    assert len(commissions) == 1
    commission = commissions[0]
    assert commission.partner_id == uuid.UUID(partner["partner"]["id"]) and commission.status == "DUE"
    assert commission.invoice_id == uuid.UUID(invoice["id"])
    assert commission.base_amount_excl_vat == Decimal(BASES[3]) and commission.rate == Decimal("20")
    assert commission.amount == Decimal(BASES[3]) * Decimal("0.20")
    assert "partner_commission.accrued" in await _audit_actions(data["school"]["id"])

    own = await client.get(f"{API}/partner/commissions", headers=partner["headers"])
    assert own.status_code == 200, own.text
    body = own.json()
    assert Decimal(body["commission_rate"]) == Decimal("20")
    assert [item["id"] for item in body["items"]] == [str(commission.id)]
    assert Decimal(body["totals"]["due_amount"]) == commission.amount and body["totals"]["paid_count"] == 0

    listed = await client.get(f"{API}/platform/partner-commissions?partner_id={partner['partner']['id']}", headers=owner["headers"])
    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert listed.json()["items"][0]["invoice_number"] == invoice["number"]


async def test_no_commission_for_a_school_enrolled_by_the_platform(client: AsyncClient) -> None:
    owner = await _owner(client, "comdirect")
    await _active_grid(client, owner["headers"])
    direct = await register_school(client, "comdirect")
    direct["headers"] = auth(direct["tokens"]["access_token"])
    await _issue_and_pay(client, owner, direct)
    assert await _commissions_for_school(direct["school"]["id"]) == []


async def test_no_commission_while_the_partner_is_suspended(client: AsyncClient) -> None:
    owner = await _owner(client, "comsusp")
    await _active_grid(client, owner["headers"])
    partner, data = await _partner_school(client, owner, "comsusp")
    await _set_partner_status(partner, "SUSPENDED")
    await _issue_and_pay(client, owner, data)
    assert await _commissions_for_school(data["school"]["id"]) == []

    # Réactivé : la facture suivante (renouvellement) ouvre de nouveau droit à commission.
    await _set_partner_status(partner, "ACTIVE")
    await _issue_and_pay(client, owner, data)
    assert len(await _commissions_for_school(data["school"]["id"])) == 1


async def test_rate_is_per_partner_and_frozen_on_each_commission(client: AsyncClient) -> None:
    owner = await _owner(client, "comrate")
    await _active_grid(client, owner["headers"])
    partner, data = await _partner_school(client, owner, "comrate")
    url = f"{API}/platform/partners/{partner['partner']['id']}/commission-rate"
    changed = await client.put(url, json={"rate": "15"}, headers=owner["headers"])
    assert changed.status_code == 200, changed.text
    assert (await client.put(url, json={"rate": "120"}, headers=owner["headers"])).status_code == 422
    await _issue_and_pay(client, owner, data)

    assert (await client.put(url, json={"rate": "25"}, headers=owner["headers"])).status_code == 200
    await _issue_and_pay(client, owner, data)  # renouvellement au nouveau taux
    first, second = await _commissions_for_school(data["school"]["id"])
    assert (first.rate, first.amount) == (Decimal("15"), Decimal(BASES[3]) * Decimal("0.15"))
    assert (second.rate, second.amount) == (Decimal("25"), Decimal(BASES[3]) * Decimal("0.25"))
    partners = (await client.get(f"{API}/platform/partners?page_size=100", headers=owner["headers"])).json()["items"]
    assert any(p["id"] == partner["partner"]["id"] and Decimal(p["commission_rate"]) == Decimal("25") for p in partners)


async def test_vat_rate_is_frozen_on_the_invoice_and_the_commission_uses_the_amount_excluding_vat(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner = await _owner(client, "comvat")
    await _active_grid(client, owner["headers"], base_delta=5400)  # 3 mois : 35 400 TTC = 30 000 HT + 18 %
    monkeypatch.setattr(settings, "subscription_vat_rate", Decimal("18"))
    _, data = await _partner_school(client, owner, "comvat")
    invoice = await _issue_and_pay(client, owner, data)
    assert Decimal(invoice["total_amount"]) == Decimal("35400")
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        vat_rate = await db.scalar(text("SELECT vat_rate FROM subscription_invoices WHERE id = :i"), {"i": uuid.UUID(invoice["id"])})
    assert vat_rate == Decimal("18.00")
    (commission,) = await _commissions_for_school(data["school"]["id"])
    assert commission.base_amount_excl_vat == Decimal("30000") and commission.amount == Decimal("6000")


async def test_online_payment_confirmation_accrues_exactly_one_commission(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "subscription_online_payment_enabled", True)
    monkeypatch.setattr(settings, "payment_online_provider", "fake")
    fake: FakeOnlinePaymentProvider = fake_online_payment_provider
    fake.next_initiation = None
    owner = await _owner(client, "comonline")
    await _active_grid(client, owner["headers"])
    _, data = await _partner_school(client, owner, "comonline")
    invoice = (await _issue(client, data)).json()
    started = await client.post(
        f"{API}/school-subscription/invoices/{invoice['id']}/payments",
        json={"network": "FLOOZ", "phone_number": PHONE, "idempotency_key": f"com-{uuid.uuid4().hex}"},
        headers=data["headers"],
    )
    assert started.status_code == 201, started.text
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        identifier = await db.scalar(select(SubscriptionPayment.identifier).where(SubscriptionPayment.id == uuid.UUID(started.json()["id"])))
        await db.execute(
            text("UPDATE subscription_payments SET created_at = created_at - interval '2 minutes' WHERE id = :p"),
            {"p": uuid.UUID(started.json()["id"])},
        )
        await db.commit()
    fake.set_status(identifier, "SUCCEEDED")

    async def reconcile() -> None:
        async with AsyncSessionLocal() as db:
            await reconcile_online_payments(db)

    callback = {"identifier": identifier, "tx_reference": "PG-COM", "amount": "30000", "payment_method": "FLOOZ"}
    await asyncio.gather(
        client.post(f"{API}/payment-providers/paygate/callback", json=callback),
        client.post(f"{API}/payment-providers/paygate/callback", json=callback),
        reconcile(),
    )
    commissions = await _commissions_for_school(data["school"]["id"])
    assert len(commissions) == 1 and commissions[0].payment_id == uuid.UUID(started.json()["id"])


# --- Versement et annulation -----------------------------------------------------------------------
async def test_manual_settlement_and_cancellation(client: AsyncClient) -> None:
    owner = await _owner(client, "comsettle")
    await _active_grid(client, owner["headers"])
    partner, data = await _partner_school(client, owner, "comsettle")
    _, other_data = await _partner_school(client, owner, "comsettle2", partner=partner)
    await _issue_and_pay(client, owner, data)
    await _issue_and_pay(client, owner, data)
    await _issue_and_pay(client, owner, other_data)
    first, second = await _commissions_for_school(data["school"]["id"])
    (third,) = await _commissions_for_school(other_data["school"]["id"])

    settle = {"commission_ids": [str(first.id), str(second.id)], "method": "MOBILE_MONEY", "reference": "TMONEY-REF-1"}
    paid = await client.post(f"{API}/platform/partner-commissions/mark-paid", json=settle, headers=owner["headers"])
    assert paid.status_code == 200, paid.text
    again = await client.post(f"{API}/platform/partner-commissions/mark-paid", json=settle, headers=owner["headers"])
    assert again.status_code == 200  # même versement renvoyé (double clic) : sans effet
    other_reference = {**settle, "reference": "AUTRE"}
    assert (await client.post(f"{API}/platform/partner-commissions/mark-paid", json=other_reference, headers=owner["headers"])).status_code == 409
    cancel_paid = await client.post(
        f"{API}/platform/partner-commissions/{first.id}/cancel", json={"reason": "erreur"}, headers=owner["headers"]
    )
    assert cancel_paid.status_code == 409

    cancelled = await client.post(
        f"{API}/platform/partner-commissions/{third.id}/cancel", json={"reason": "école remboursée"}, headers=owner["headers"]
    )
    assert cancelled.status_code == 200, cancelled.text
    late = {"commission_ids": [str(third.id)], "method": "CASH", "reference": "X"}
    assert (await client.post(f"{API}/platform/partner-commissions/mark-paid", json=late, headers=owner["headers"])).status_code == 409

    body = (await client.get(f"{API}/partner/commissions", headers=partner["headers"])).json()
    statuses = {item["id"]: item["status"] for item in body["items"]}
    assert statuses == {str(first.id): "PAID", str(second.id): "PAID", str(third.id): "CANCELLED"}
    assert body["totals"]["paid_count"] == 2 and body["totals"]["due_count"] == 0
    assert "partner_commission.paid" in await _audit_actions(data["school"]["id"])
    assert "partner_commission.cancelled" in await _audit_actions(other_data["school"]["id"])


async def test_a_settlement_covers_a_single_partner(client: AsyncClient) -> None:
    owner = await _owner(client, "comsingle")
    await _active_grid(client, owner["headers"])
    _, data_a = await _partner_school(client, owner, "comsinglea")
    _, data_b = await _partner_school(client, owner, "comsingleb")
    await _issue_and_pay(client, owner, data_a)
    await _issue_and_pay(client, owner, data_b)
    (a,) = await _commissions_for_school(data_a["school"]["id"])
    (b,) = await _commissions_for_school(data_b["school"]["id"])
    mixed = {"commission_ids": [str(a.id), str(b.id)], "method": "BANK_TRANSFER", "reference": "VIR-1"}
    assert (await client.post(f"{API}/platform/partner-commissions/mark-paid", json=mixed, headers=owner["headers"])).status_code == 409


# --- Droits et isolation -------------------------------------------------------------------------------
async def test_partners_see_only_their_own_commissions_and_schools_see_none(client: AsyncClient) -> None:
    owner = await _owner(client, "comiso")
    await _active_grid(client, owner["headers"])
    partner_a, data_a = await _partner_school(client, owner, "comisoa")
    partner_b, data_b = await _partner_school(client, owner, "comisob")
    await _issue_and_pay(client, owner, data_a)
    await _issue_and_pay(client, owner, data_b)

    seen_by_b = (await client.get(f"{API}/partner/commissions", headers=partner_b["headers"])).json()
    assert {item["school_id"] for item in seen_by_b["items"]} == {data_b["school"]["id"]}

    for headers in (data_a["headers"], partner_a["headers"]):
        assert (await client.get(f"{API}/platform/partner-commissions", headers=headers)).status_code == 403
        settle = {"commission_ids": [str(uuid.uuid4())], "method": "CASH", "reference": "X"}
        assert (await client.post(f"{API}/platform/partner-commissions/mark-paid", json=settle, headers=headers)).status_code == 403
        rate_url = f"{API}/platform/partners/{partner_a['partner']['id']}/commission-rate"
        assert (await client.put(rate_url, json={"rate": "50"}, headers=headers)).status_code == 403
    assert (await client.get(f"{API}/partner/commissions", headers=data_a["headers"])).status_code == 403

    # RLS : même en requête directe, l'école ne lit aucune commission (table « plateforme seulement »).
    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(data_a["user"]["id"]))
        assert await db.scalar(text("SELECT count(*) FROM partner_commissions")) == 0
