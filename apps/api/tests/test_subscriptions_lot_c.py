"""Phase 29, lot C — rappels d'abonnement, expiration automatique des factures, reçus PDF.

Écrit pour fonctionner aussi bien dans l'environnement isolé (base vidée entre les tests) que dans
la CI (base partagée par toute la suite) : chaque test cible ses propres écoles.
"""

import uuid
from datetime import date, datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select, text, update

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.subscriptions.models import SchoolSubscriptionPeriod, SubscriptionInvoice, SubscriptionReminder
from app.modules.subscriptions.reminders import run_subscription_reminders
from tests.test_fees import _create_user_with_role
from tests.test_subscriptions import API, _active_grid, _audit_actions, _issue, _owner, _pay, _school, _subscription


async def _run(*schools: dict) -> None:
    async with AsyncSessionLocal() as db:
        await run_subscription_reminders(db, only_school_ids={uuid.UUID(s["school"]["id"]) for s in schools})


async def _notifications(school_id: str, notification_type: str) -> list[tuple[str, str]]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = await db.execute(
            text(
                "SELECT recipient_user_id::text, title FROM notifications "
                "WHERE school_id = :s AND type = :t ORDER BY created_at"
            ),
            {"s": uuid.UUID(school_id), "t": notification_type},
        )
        return [(row[0], row[1]) for row in rows.all()]


async def _add_trial(data: dict, starts_on: date, ends_on: date) -> uuid.UUID:
    period_id = uuid.uuid4()
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            SchoolSubscriptionPeriod(
                id=period_id,
                school_id=uuid.UUID(data["school"]["id"]),
                organization_id=uuid.UUID(data["organization"]["id"]),
                kind="FREE_TRIAL",
                invoice_id=None,
                starts_on=starts_on,
                ends_on=ends_on,
            )
        )
        await db.commit()
    return period_id


async def _set_period_end(period_id: uuid.UUID, ends_on: date) -> None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(update(SchoolSubscriptionPeriod).where(SchoolSubscriptionPeriod.id == period_id).values(ends_on=ends_on))
        await db.commit()


async def _set_invoice_expiry(invoice_id: str, expires_at: datetime) -> None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(
            update(SubscriptionInvoice).where(SubscriptionInvoice.id == uuid.UUID(invoice_id)).values(expires_at=expires_at)
        )
        await db.commit()


# --- Rappels de fin de couverture --------------------------------------------------------------
async def test_coverage_reminders_reach_admin_and_director_once_per_stage(client: AsyncClient) -> None:
    data = await _school(client, "lotcremind")
    school_id = data["school"]["id"]
    director = await _create_user_with_role(client, data["headers"], school_id, "DIRECTOR", "lotcremind.dir")
    await _create_user_with_role(client, data["headers"], school_id, "TEACHER", "lotcremind.teach")
    today = date.fromisoformat((await _subscription(client, data))["today"])
    period_id = await _add_trial(data, today - timedelta(days=80), today + timedelta(days=10))
    expected_recipients = {data["user"]["id"], director["user"]["id"]}

    await _run(data)
    due = await _notifications(school_id, "SUBSCRIPTION_RENEWAL_DUE")
    assert {recipient for recipient, _ in due} == expected_recipients  # jamais l'enseignant
    assert len(due) == 2 and all("fin le" in title for _, title in due)

    await _run(data)  # idempotent
    assert len(await _notifications(school_id, "SUBSCRIPTION_RENEWAL_DUE")) == 2

    await _set_period_end(period_id, today + timedelta(days=3))  # palier J7
    await _run(data)
    assert len(await _notifications(school_id, "SUBSCRIPTION_RENEWAL_DUE")) == 4

    await _set_period_end(period_id, today - timedelta(days=1))  # couverture terminée : J0
    await _run(data)
    await _run(data)
    expired = await _notifications(school_id, "SUBSCRIPTION_EXPIRED")
    assert len(expired) == 2 and {recipient for recipient, _ in expired} == expected_recipients

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        stages = sorted((await db.execute(select(SubscriptionReminder.stage).where(SubscriptionReminder.period_id == period_id))).scalars())
    assert stages == ["J0", "J30", "J7"]


async def test_no_reminder_far_from_the_end_nor_long_after_it(client: AsyncClient) -> None:
    far = await _school(client, "lotcfar")
    old = await _school(client, "lotcold")
    today = date.fromisoformat((await _subscription(client, far))["today"])
    await _add_trial(far, today, today + timedelta(days=89))
    await _add_trial(old, today - timedelta(days=120), today - timedelta(days=30))
    await _run(far, old)
    for data in (far, old):
        for notification_type in ("SUBSCRIPTION_RENEWAL_DUE", "SUBSCRIPTION_EXPIRED"):
            assert await _notifications(data["school"]["id"], notification_type) == []


# --- Factures : rappel avant expiration, expiration automatique ----------------------------------
async def test_invoice_reminder_then_automatic_expiry(client: AsyncClient) -> None:
    owner = await _owner(client, "lotcinv")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "lotcinv")
    invoice = (await _issue(client, data)).json()

    await _set_invoice_expiry(invoice["id"], datetime.now(timezone.utc) + timedelta(days=2))
    await _run(data)
    await _run(data)
    due = await _notifications(data["school"]["id"], "SUBSCRIPTION_INVOICE_DUE")
    assert len(due) == 1 and invoice["number"] in due[0][1]

    await _set_invoice_expiry(invoice["id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    await _run(data)
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        stored = await db.scalar(select(SubscriptionInvoice.status).where(SubscriptionInvoice.id == uuid.UUID(invoice["id"])))
    assert stored == "EXPIRED"
    assert "subscription_invoice.expired" in await _audit_actions(data["school"]["id"])


# --- Reçus PDF ----------------------------------------------------------------------------------
async def test_receipt_pdf_only_for_paid_invoices_and_properly_scoped(client: AsyncClient) -> None:
    owner = await _owner(client, "lotcrecu")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "lotcrecu")
    other = await _school(client, "lotcrecuother")
    teacher = await _create_user_with_role(client, data["headers"], data["school"]["id"], "TEACHER", "lotcrecu.teach")
    invoice = (await _issue(client, data)).json()
    school_url = f"{API}/school-subscription/invoices/{invoice['id']}/receipt.pdf"
    platform_url = f"{API}/platform/subscription-invoices/{invoice['id']}/receipt.pdf"

    assert (await client.get(school_url, headers=data["headers"])).status_code == 409  # pas encore payée
    assert (await _pay(client, owner["headers"], invoice)).status_code == 201

    response = await client.get(school_url, headers=data["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF")
    assert invoice["number"] in response.headers["content-disposition"]

    platform = await client.get(platform_url, headers=owner["headers"])
    assert platform.status_code == 200 and platform.content.startswith(b"%PDF")

    assert (await client.get(school_url, headers=teacher["headers"])).status_code == 403
    assert (await client.get(school_url, headers=other["headers"])).status_code == 404
    assert (await client.get(platform_url, headers=data["headers"])).status_code == 403
