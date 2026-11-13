"""Phase 29, lot A — abonnements des écoles : grille, factures figées, devis, paiement manuel,
périodes, trimestre gratuit, RBAC, isolation (applicative et RLS), idempotence, concurrence, audit.

Le paiement en ligne (PayGate) relève du lot B : aucun test ici.
"""

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from app.core.tenancy import apply_tenant_context, set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.schools.models import School
from app.modules.students.models import Student
from app.modules.subscriptions import pricing
from app.modules.subscriptions.free_quarters import grant_free_quarters
from app.modules.subscriptions.models import SchoolSubscriptionPeriod, SubscriptionInvoice
from tests.conftest import register_school
from tests.pr17_helpers import auth, create_platform_owner
from tests.test_fees import _create_user_with_role

API = "/api/v1"
BASES = {3: 30000, 6: 55000, 12: 100000}
SUPPLEMENTS = {3: (10000, 20000, 30000), 6: (18000, 36000, 54000), 12: (35000, 70000, 105000)}


# --- Helpers -----------------------------------------------------------------------------------
def _grid_payload(label: str = "Grille test", base_delta: int = 0) -> dict:
    return {
        "label": label,
        "periods": [
            {
                "period_months": months,
                "base_amount": str(BASES[months] + base_delta),
                "supplement_tier_1": str(SUPPLEMENTS[months][0]),
                "supplement_tier_2": str(SUPPLEMENTS[months][1]),
                "supplement_tier_3": str(SUPPLEMENTS[months][2]),
            }
            for months in (3, 6, 12)
        ],
    }


async def _owner(client: AsyncClient, prefix: str) -> dict:
    return await create_platform_owner(client, prefix)


async def _active_grid(client: AsyncClient, owner_headers: dict, base_delta: int = 0) -> dict:
    created = await client.post(f"{API}/platform/subscription-grids", json=_grid_payload(base_delta=base_delta), headers=owner_headers)
    assert created.status_code == 201, created.text
    activated = await client.post(f"{API}/platform/subscription-grids/{created.json()['id']}/activate", headers=owner_headers)
    assert activated.status_code == 200, activated.text
    return activated.json()


async def _school(client: AsyncClient, prefix: str) -> dict:
    data = await register_school(client, prefix)
    data["headers"] = auth(data["tokens"]["access_token"])
    return data


async def _add_students(data: dict, count: int, status: str = "ACTIVE") -> None:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add_all(
            [
                Student(
                    id=uuid.uuid4(),
                    school_id=uuid.UUID(data["school"]["id"]),
                    organization_id=uuid.UUID(data["organization"]["id"]),
                    matricule=f"S{uuid.uuid4().hex[:12]}",
                    first_name="Eleve",
                    last_name="Test",
                    date_of_birth=date(2015, 1, 1),
                    sex="F",
                    status=status,
                )
                for _ in range(count)
            ]
        )
        await db.commit()


def _key() -> str:
    return f"sub-{uuid.uuid4().hex}"


async def _issue(client: AsyncClient, data: dict, months: int = 3, key: str | None = None):
    return await client.post(
        f"{API}/school-subscription/invoices",
        json={"school_id": data["school"]["id"], "period_months": months, "idempotency_key": key or _key()},
        headers=data["headers"],
    )


async def _pay(client: AsyncClient, owner_headers: dict, invoice: dict, key: str | None = None, **overrides):
    body = {
        "method": "BANK_TRANSFER",
        "amount": invoice["total_amount"],
        "reference": "VIR-123",
        "idempotency_key": key or _key(),
        **overrides,
    }
    return await client.post(
        f"{API}/platform/subscription-invoices/{invoice['id']}/manual-payments", json=body, headers=owner_headers
    )


async def _subscription(client: AsyncClient, data: dict) -> dict:
    response = await client.get(f"{API}/school-subscription?school_id={data['school']['id']}", headers=data["headers"])
    assert response.status_code == 200, response.text
    return response.json()


async def _audit_actions(school_id: str) -> list[str]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = await db.execute(
            text("SELECT action FROM audit_logs WHERE school_id = :s ORDER BY created_at"), {"s": uuid.UUID(school_id)}
        )
        return [row[0] for row in rows.all()]


# --- Grille de prix ----------------------------------------------------------------------------
async def test_grid_lifecycle_draft_update_activate_archive(client: AsyncClient) -> None:
    owner = await _owner(client, "subgrid")
    created = await client.post(f"{API}/platform/subscription-grids", json=_grid_payload("V1"), headers=owner["headers"])
    assert created.status_code == 201, created.text
    grid = created.json()
    assert grid["status"] == "DRAFT" and grid["currency"] == "XOF" and len(grid["periods"]) == 3

    updated = await client.put(
        f"{API}/platform/subscription-grids/{grid['id']}", json=_grid_payload("V1 bis", base_delta=1000), headers=owner["headers"]
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["label"] == "V1 bis"
    three = next(p for p in updated.json()["periods"] if p["period_months"] == 3)
    assert float(three["base_amount"]) == BASES[3] + 1000

    first = await client.post(f"{API}/platform/subscription-grids/{grid['id']}/activate", headers=owner["headers"])
    assert first.status_code == 200 and first.json()["status"] == "ACTIVE"
    # Une grille active ne se modifie plus.
    refused = await client.put(f"{API}/platform/subscription-grids/{grid['id']}", json=_grid_payload(), headers=owner["headers"])
    assert refused.status_code == 409

    second = await _active_grid(client, owner["headers"], base_delta=5000)
    grids = {g["id"]: g for g in (await client.get(f"{API}/platform/subscription-grids", headers=owner["headers"])).json()}
    assert grids[grid["id"]]["status"] == "ARCHIVED" and grids[grid["id"]]["archived_at"] is not None
    assert grids[second["id"]]["status"] == "ACTIVE"
    assert sum(1 for g in grids.values() if g["status"] == "ACTIVE") == 1
    # Une grille archivée ne revient jamais.
    again = await client.post(f"{API}/platform/subscription-grids/{grid['id']}/activate", headers=owner["headers"])
    assert again.status_code == 409


async def test_grid_validation_rejects_incomplete_or_fractional_prices(client: AsyncClient) -> None:
    owner = await _owner(client, "subgridval")
    missing = _grid_payload()
    missing["periods"] = missing["periods"][:2]
    assert (await client.post(f"{API}/platform/subscription-grids", json=missing, headers=owner["headers"])).status_code == 422
    fractional = _grid_payload()
    fractional["periods"][0]["base_amount"] = "30000.50"
    assert (await client.post(f"{API}/platform/subscription-grids", json=fractional, headers=owner["headers"])).status_code == 422
    zero_base = _grid_payload()
    zero_base["periods"][0]["base_amount"] = "0"
    assert (await client.post(f"{API}/platform/subscription-grids", json=zero_base, headers=owner["headers"])).status_code == 422


# --- Émission de facture -----------------------------------------------------------------------
async def _archive_active_grids() -> None:
    """Indépendance vis-à-vis de l'ordre d'exécution : sans vidage de la base entre les tests
    (CI), une grille activée par un test précédent resterait active."""
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(
            text("UPDATE subscription_price_grids SET status = 'ARCHIVED', archived_at = now() WHERE status = 'ACTIVE'")
        )
        await db.commit()


async def test_invoice_requires_an_active_grid(client: AsyncClient) -> None:
    await _archive_active_grids()
    data = await _school(client, "subnogrid")
    response = await _issue(client, data)
    assert response.status_code == 409
    subscription = await _subscription(client, data)
    assert subscription["grid_available"] is False
    assert all(offer["total_amount"] is None for offer in subscription["offers"])


async def test_invoice_is_priced_by_tier_and_frozen(client: AsyncClient) -> None:
    owner = await _owner(client, "subprice")
    await _active_grid(client, owner["headers"])
    small = await _school(client, "subsmall")
    await _add_students(small, 3)
    await _add_students(small, 200, status="INACTIVE")  # seuls les élèves ACTIFS comptent
    big = await _school(client, "subbig")
    await _add_students(big, 101)

    preview = await _subscription(client, big)
    assert preview["active_student_count"] == 101 and preview["tier"] == 1 and preview["quote_required"] is False
    offers = {offer["period_months"]: float(offer["total_amount"]) for offer in preview["offers"]}
    assert offers == {m: BASES[m] + SUPPLEMENTS[m][0] for m in (3, 6, 12)}

    small_invoice = await _issue(client, small, months=6)
    assert small_invoice.status_code == 201, small_invoice.text
    small_json = small_invoice.json()
    assert small_json["status"] == "ISSUED" and small_json["tier"] == 0 and small_json["student_count"] == 3
    assert float(small_json["total_amount"]) == BASES[6] and float(small_json["supplement_amount"]) == 0

    big_invoice = (await _issue(client, big, months=12)).json()
    assert big_invoice["tier"] == 1
    assert float(big_invoice["total_amount"]) == BASES[12] + SUPPLEMENTS[12][0]

    # Numérotation séquentielle sans trou.
    year = datetime.now(timezone.utc).year
    first_seq = int(small_json["number"].rsplit("-", 1)[1])
    assert small_json["number"] == pricing.format_invoice_number(year, first_seq)
    assert big_invoice["number"] == pricing.format_invoice_number(year, first_seq + 1)

    # Figée : ajouter des élèves après l'émission ne change rien à la facture.
    await _add_students(small, 300)
    detail = await client.get(f"{API}/school-subscription/invoices/{small_json['id']}", headers=small["headers"])
    assert detail.status_code == 200
    assert detail.json()["student_count"] == 3 and detail.json()["total_amount"] == small_json["total_amount"]
    assert "subscription_invoice.issued" in await _audit_actions(small["school"]["id"])


async def test_one_open_invoice_per_school_and_idempotency(client: AsyncClient) -> None:
    owner = await _owner(client, "subidem")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subidem")
    key = _key()
    first = await _issue(client, data, months=3, key=key)
    assert first.status_code == 201
    replay = await _issue(client, data, months=3, key=key)
    assert replay.status_code == 201 and replay.json()["id"] == first.json()["id"]
    assert (await _issue(client, data, months=6, key=key)).status_code == 409  # même clé, autre durée
    assert (await _issue(client, data, months=6)).status_code == 409  # une facture déjà ouverte
    invoices = (await client.get(f"{API}/school-subscription/invoices?school_id={data['school']['id']}", headers=data["headers"])).json()
    assert len(invoices) == 1


async def test_concurrent_invoice_requests_create_a_single_invoice(client: AsyncClient) -> None:
    owner = await _owner(client, "subconc")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subconc")
    responses = await asyncio.gather(*[_issue(client, data, months=3) for _ in range(4)])
    assert sorted(r.status_code for r in responses) == [201, 409, 409, 409]


# --- Devis au-delà de 1 000 élèves --------------------------------------------------------------
async def test_quote_required_above_one_thousand_students(client: AsyncClient) -> None:
    owner = await _owner(client, "subquote")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subquote")
    await _add_students(data, 1001)
    preview = await _subscription(client, data)
    assert preview["quote_required"] is True and preview["tier"] is None
    assert all(offer["total_amount"] is None for offer in preview["offers"])

    created = await _issue(client, data, months=12)
    assert created.status_code == 201
    invoice = created.json()
    assert invoice["status"] == "QUOTE_REQUIRED" and invoice["number"] is None and invoice["total_amount"] is None
    # Pas payable tant que le montant n'est pas saisi.
    assert (await _pay(client, owner["headers"], {**invoice, "total_amount": "500000"})).status_code == 409

    quoted = await client.post(
        f"{API}/platform/subscription-invoices/{invoice['id']}/quote", json={"total_amount": "750000"}, headers=owner["headers"]
    )
    assert quoted.status_code == 200, quoted.text
    assert quoted.json()["status"] == "ISSUED" and quoted.json()["number"] and float(quoted.json()["total_amount"]) == 750000
    paid = await _pay(client, owner["headers"], quoted.json())
    assert paid.status_code == 201 and paid.json()["status"] == "PAID"
    actions = await _audit_actions(data["school"]["id"])
    assert "subscription_invoice.quote_requested" in actions and "subscription_invoice.quote_set" in actions


# --- Paiement manuel et périodes ---------------------------------------------------------------
async def test_manual_payment_creates_the_paid_period_and_renewal_continues(client: AsyncClient) -> None:
    owner = await _owner(client, "subpay")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subpay")
    invoice = (await _issue(client, data, months=3)).json()

    wrong = await _pay(client, owner["headers"], invoice, amount="1000")
    assert wrong.status_code == 422
    key = _key()
    paid = await _pay(client, owner["headers"], invoice, key=key)
    assert paid.status_code == 201, paid.text
    body = paid.json()
    today = date.fromisoformat((await _subscription(client, data))["today"])
    assert body["status"] == "PAID" and len(body["payments"]) == 1
    assert body["period"]["starts_on"] == today.isoformat()
    assert body["period"]["ends_on"] == pricing.period_end(today, 3).isoformat()

    # Rejeu identique : même résultat, aucun second paiement. Même clé, autres données : conflit.
    assert (await _pay(client, owner["headers"], invoice, key=key)).status_code == 201
    assert (await _pay(client, owner["headers"], invoice, key=key, reference="AUTRE")).status_code == 409
    assert (await _pay(client, owner["headers"], invoice)).status_code == 409  # déjà payée
    detail = (await client.get(f"{API}/school-subscription/invoices/{invoice['id']}", headers=data["headers"])).json()
    assert len(detail["payments"]) == 1

    state = await _subscription(client, data)
    assert state["state"] == "ACTIVE" and state["current_period"]["kind"] == "PAID"

    # Renouvellement anticipé : la nouvelle période commence le lendemain de la précédente.
    renewal = (await _issue(client, data, months=6)).json()
    renewed = (await _pay(client, owner["headers"], renewal)).json()
    first_end = pricing.period_end(today, 3)
    assert renewed["period"]["starts_on"] == (first_end + timedelta(days=1)).isoformat()
    assert renewed["period"]["ends_on"] == pricing.period_end(first_end + timedelta(days=1), 6).isoformat()
    assert "subscription_payment.manual_recorded" in await _audit_actions(data["school"]["id"])


async def test_expired_invoice_is_not_payable_and_frees_the_slot(client: AsyncClient) -> None:
    owner = await _owner(client, "subexp")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subexp")
    invoice = (await _issue(client, data, months=3)).json()
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        await db.execute(
            update(SubscriptionInvoice)
            .where(SubscriptionInvoice.id == uuid.UUID(invoice["id"]))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        )
        await db.commit()

    assert (await _subscription(client, data))["open_invoice"] is None
    assert (await _pay(client, owner["headers"], invoice)).status_code == 409
    fresh = await _issue(client, data, months=3)
    assert fresh.status_code == 201
    listed = {i["id"]: i["status"] for i in (await client.get(f"{API}/school-subscription/invoices?school_id={data['school']['id']}", headers=data["headers"])).json()}
    assert listed[invoice["id"]] == "EXPIRED" and listed[fresh.json()["id"]] == "ISSUED"
    assert "subscription_invoice.expired" in await _audit_actions(data["school"]["id"])


async def test_cancel_open_invoice_but_never_a_paid_one(client: AsyncClient) -> None:
    owner = await _owner(client, "subcancel")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subcancel")
    invoice = (await _issue(client, data)).json()
    url = f"{API}/platform/subscription-invoices/{invoice['id']}/cancel"
    assert (await client.post(url, json={"reason": " "}, headers=owner["headers"])).status_code == 422
    cancelled = await client.post(url, json={"reason": "Erreur de durée"}, headers=owner["headers"])
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert (await _pay(client, owner["headers"], invoice)).status_code == 409

    paid_invoice = (await _issue(client, data)).json()
    assert (await _pay(client, owner["headers"], paid_invoice)).status_code == 201
    refused = await client.post(
        f"{API}/platform/subscription-invoices/{paid_invoice['id']}/cancel", json={"reason": "Trop tard"}, headers=owner["headers"]
    )
    assert refused.status_code == 409


# --- RBAC et isolation -------------------------------------------------------------------------
async def test_school_roles_and_platform_roles_are_strictly_separated(client: AsyncClient) -> None:
    owner = await _owner(client, "subrbac")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subrbac")
    school_id = data["school"]["id"]
    director = await _create_user_with_role(client, data["headers"], school_id, "DIRECTOR", "subrbac.dir")
    teacher = await _create_user_with_role(client, data["headers"], school_id, "TEACHER", "subrbac.teach")

    assert (await client.get(f"{API}/school-subscription?school_id={school_id}", headers=director["headers"])).status_code == 200
    assert (await _issue(client, {**data, "headers": director["headers"]})).status_code == 403
    assert (await client.get(f"{API}/school-subscription?school_id={school_id}", headers=teacher["headers"])).status_code == 403
    # PLATFORM_OWNER : aucune permission du domaine scolaire, même s'il voit les lignes (RLS).
    assert (await client.get(f"{API}/school-subscription?school_id={school_id}", headers=owner["headers"])).status_code == 403
    assert (await _issue(client, {**data, "headers": owner["headers"]})).status_code == 403
    # Les endpoints plateforme refusent tout compte d'école.
    for method, path in (
        ("GET", "/platform/subscription-grids"),
        ("POST", "/platform/subscription-grids"),
        ("GET", "/platform/subscriptions"),
        ("GET", "/platform/subscription-invoices"),
    ):
        response = await client.request(method, f"{API}{path}", json=_grid_payload(), headers=data["headers"])
        assert response.status_code == 403, (method, path)


async def test_other_organization_cannot_read_invoices_and_rls_blocks_grid_writes(client: AsyncClient) -> None:
    owner = await _owner(client, "subiso")
    await _active_grid(client, owner["headers"])
    school_a = await _school(client, "subisoa")
    school_b = await _school(client, "subisob")
    invoice = (await _issue(client, school_a)).json()

    assert (await client.get(f"{API}/school-subscription/invoices/{invoice['id']}", headers=school_b["headers"])).status_code == 404
    assert (await client.get(f"{API}/school-subscription?school_id={school_a['school']['id']}", headers=school_b["headers"])).status_code == 404

    async with AsyncSessionLocal() as db:
        await apply_tenant_context(db, uuid.UUID(school_b["user"]["id"]))
        visible = await db.scalar(
            text("SELECT count(*) FROM subscription_invoices WHERE school_id = :s"), {"s": uuid.UUID(school_a["school"]["id"])}
        )
        assert visible == 0
        # La grille est lisible par une école (aperçu des prix)...
        assert await db.scalar(text("SELECT count(*) FROM subscription_price_grids WHERE status = 'ACTIVE'")) == 1
        # ... mais jamais modifiable hors contexte plateforme.
        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    "INSERT INTO subscription_price_grids (id, label, currency, status, created_by) "
                    "VALUES (:id, 'Intrus', 'XOF', 'DRAFT', :u)"
                ),
                {"id": uuid.uuid4(), "u": uuid.UUID(school_b["user"]["id"])},
            )
        await db.rollback()


# --- Trimestre gratuit -------------------------------------------------------------------------
async def _school_created_on(data: dict) -> date:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        school = await db.get(School, uuid.UUID(data["school"]["id"]))
        assert school is not None
        from app.modules.cash.service import business_date

        return business_date(school, school.created_at)


async def _free_trials(school_id: str) -> list[SchoolSubscriptionPeriod]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        rows = await db.execute(
            text("SELECT starts_on, ends_on FROM school_subscription_periods WHERE school_id = :s AND kind = 'FREE_TRIAL'"),
            {"s": uuid.UUID(school_id)},
        )
        return list(rows.all())


async def test_free_quarter_is_granted_once_from_launch_or_creation_date(client: AsyncClient) -> None:
    data = await _school(client, "subtrial")
    created_on = await _school_created_on(data)

    async with AsyncSessionLocal() as db:
        assert (await grant_free_quarters(db, None)).granted == 0
    assert await _free_trials(data["school"]["id"]) == []

    # École déjà en service au lancement : début = date de lancement (ici dans le futur).
    launch = created_on + timedelta(days=10)
    async with AsyncSessionLocal() as db:
        assert (await grant_free_quarters(db, launch)).granted >= 1
    trials = await _free_trials(data["school"]["id"])
    assert trials == [(launch, pricing.period_end(launch, 3))]
    assert (await _subscription(client, data))["state"] == "SCHEDULED"

    # Idempotent : jamais un second trimestre gratuit.
    async with AsyncSessionLocal() as db:
        await grant_free_quarters(db, launch)
    assert len(await _free_trials(data["school"]["id"])) == 1
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        with pytest.raises(DBAPIError):
            await db.execute(
                text(
                    "INSERT INTO school_subscription_periods (id, school_id, organization_id, kind, starts_on, ends_on) "
                    "VALUES (:id, :s, :o, 'FREE_TRIAL', :d, :d)"
                ),
                {
                    "id": uuid.uuid4(),
                    "s": uuid.UUID(data["school"]["id"]),
                    "o": uuid.UUID(data["organization"]["id"]),
                    "d": launch,
                },
            )
        await db.rollback()
    assert "subscription_period.free_quarter_granted" in await _audit_actions(data["school"]["id"])

    # École créée APRÈS le lancement : début = sa date de création.
    newer = await _school(client, "subtrialnew")
    newer_created = await _school_created_on(newer)
    async with AsyncSessionLocal() as db:
        await grant_free_quarters(db, newer_created - timedelta(days=30))
    assert await _free_trials(newer["school"]["id"]) == [(newer_created, pricing.period_end(newer_created, 3))]
    assert (await _subscription(client, newer))["state"] == "TRIAL"


async def test_payment_during_free_quarter_starts_after_it(client: AsyncClient) -> None:
    owner = await _owner(client, "subtrialpay")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subtrialpay")
    created_on = await _school_created_on(data)
    async with AsyncSessionLocal() as db:
        await grant_free_quarters(db, created_on)
    trial_end = pricing.period_end(created_on, 3)

    invoice = (await _issue(client, data, months=12)).json()
    paid = (await _pay(client, owner["headers"], invoice)).json()
    assert paid["period"]["starts_on"] == (trial_end + timedelta(days=1)).isoformat()
    state = await _subscription(client, data)
    assert state["state"] == "TRIAL"
    assert state["covered_until"] == pricing.period_end(trial_end + timedelta(days=1), 12).isoformat()


# --- Vue plateforme ----------------------------------------------------------------------------
async def test_platform_lists_school_states_and_invoices(client: AsyncClient) -> None:
    owner = await _owner(client, "subplat")
    await _active_grid(client, owner["headers"])
    data = await _school(client, "subplat")
    invoice = (await _issue(client, data)).json()

    # Parcours de TOUTES les pages : sans vidage de la base entre les tests (CI), l'école peut se
    # trouver au-delà de la première page (tri par nom).
    row = None
    page = 1
    while row is None:
        states = await client.get(f"{API}/platform/subscriptions?page={page}&page_size=100", headers=owner["headers"])
        assert states.status_code == 200
        body = states.json()
        row = next((item for item in body["items"] if item["school_id"] == data["school"]["id"]), None)
        assert row is not None or page < body["total_pages"], "école absente de la vue plateforme"
        page += 1
    assert row["state"] == "NONE" and row["open_invoice_status"] == "ISSUED" and row["has_free_trial"] is False
    filtered = await client.get(f"{API}/platform/subscriptions?state=ACTIVE&page_size=100", headers=owner["headers"])
    assert all(item["state"] == "ACTIVE" for item in filtered.json()["items"])

    issued = await client.get(f"{API}/platform/subscription-invoices?status=ISSUED&page_size=100", headers=owner["headers"])
    assert issued.status_code == 200
    ids = {item["id"]: item for item in issued.json()["items"]}
    assert invoice["id"] in ids and ids[invoice["id"]]["school_name"] == data["school"]["name"]
