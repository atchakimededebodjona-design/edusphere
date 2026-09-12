"""Sprint 1.4 — vue opérationnelle staff des frais scolaires en retard (lecture seule).

Une ligne par `StudentFee` en retard (jamais par tuteur), réutilisant les fixtures déjà établies
par les Sprints 1.2/1.3 (`test_overdue_fee_reminders.py`/`test_overdue_fee_reminders_email.py`)
pour construire les scénarios de contact tuteur plutôt que de dupliquer un nouveau jeu de
helpers — mêmes conventions que `test_overdue_fee_reminders_standalone.py`.

`_run_job_with_emails()` (Sprint 1.3) est réutilisé partout ici : un seul passage du job produit
à la fois les notifications in-app (tuteurs avec compte) et les lignes de suivi email (tuteurs
sans compte avec email), exactement ce dont ces tests ont besoin pour peupler IN_APP_SENT et
EMAIL_SENT sans dupliquer la logique des deux sprints précédents.
"""

import uuid
from datetime import date

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.fees.service import list_overdue_fees
from tests.test_fees import _create_user_with_role
from tests.test_overdue_fee_reminders import (
    FUTURE_DUE_DATE,
    PAST_DUE_DATE,
    _cancel_fee_directly,
    _create_guardian_without_account,
    _create_student_fee,
    _link_parent,
    _pay,
    _setup_student,
)
from tests.test_overdue_fee_reminders_email import _create_guardian_with_email, _run_job_with_emails


async def _get_overdue(client: AsyncClient, headers: dict, school_id: str, **params) -> dict:
    response = await client.get(
        "/api/v1/fees/overdue", params={"school_id": school_id, **params}, headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def _item_for_fee(payload: dict, fee_id: str) -> dict:
    return next(item for item in payload["items"] if item["student_fee_id"] == fee_id)


# --- A : un frais réellement en retard apparaît -------------------------------------------------
async def test_overdue_fee_appears_in_view(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-a")
    await _link_parent(client, env, "parent.overdueview-a")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    item = _item_for_fee(payload, fee["id"])
    assert item["student_id"] == env["student"]["id"]
    assert item["student_matricule"] == env["student"]["matricule"]
    assert item["student_first_name"] == "Koffi"
    assert item["student_last_name"] == "Test"
    assert item["remaining_balance"] == "50000.00"
    assert item["due_date"] == str(PAST_DUE_DATE)


# --- B : frais payé intégralement -> absent -----------------------------------------------------
async def test_fully_paid_fee_absent_from_view(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-b")
    await _link_parent(client, env, "parent.overdueview-b")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")
    await _pay(client, env, fee["id"], "50000")
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    assert all(item["student_fee_id"] != fee["id"] for item in payload["items"])


# --- C : frais annulé -> absent -------------------------------------------------------------------
async def test_cancelled_fee_absent_from_view(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-c")
    await _link_parent(client, env, "parent.overdueview-c")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _cancel_fee_directly(fee["id"])
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    assert all(item["student_fee_id"] != fee["id"] for item in payload["items"])


# --- D : échéance future -> absent -----------------------------------------------------------------
async def test_future_due_date_fee_absent_from_view(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-d")
    await _link_parent(client, env, "parent.overdueview-d")
    fee = await _create_student_fee(client, env, FUTURE_DUE_DATE)
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    assert all(item["student_fee_id"] != fee["id"] for item in payload["items"])


# --- E : paiement partiel -> solde restant correct ---------------------------------------------------
async def test_partial_payment_shows_correct_remaining_balance(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-e")
    await _link_parent(client, env, "parent.overdueview-e")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")
    await _pay(client, env, fee["id"], "20000")
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    item = _item_for_fee(payload, fee["id"])
    assert item["remaining_balance"] == "30000.00"
    assert item["amount_due"] == "50000.00"


# --- F : nombre de jours de retard correct -----------------------------------------------------------
async def test_overdue_days_is_correct(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-f")
    await _link_parent(client, env, "parent.overdueview-f")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    item = _item_for_fee(payload, fee["id"])
    assert item["overdue_days"] == (date.today() - PAST_DUE_DATE).days


# --- G : tuteur avec notification in-app -> IN_APP_SENT -----------------------------------------------
async def test_guardian_with_in_app_notification_has_in_app_sent_status(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-g")
    parent = await _link_parent(client, env, "parent.overdueview-g")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    item = _item_for_fee(payload, fee["id"])
    contact = next(g for g in item["guardians"] if g["guardian_id"] == parent["guardian"]["id"])
    assert contact["has_user_account"] is True
    assert contact["statuses"] == ["IN_APP_SENT"]


# --- H : tuteur sans compte avec email + rappel email -> EMAIL_SENT ------------------------------------
async def test_guardian_without_account_with_email_has_email_sent_status(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-h")
    guardian = await _create_guardian_with_email(client, env, "guardian.overdueview-h")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    item = _item_for_fee(payload, fee["id"])
    contact = next(g for g in item["guardians"] if g["guardian_id"] == guardian["guardian"]["id"])
    assert contact["has_user_account"] is False
    assert contact["email"] == guardian["email"]
    assert contact["statuses"] == ["EMAIL_SENT"]


# --- I : tuteur sans compte ni email -> NO_CHANNEL ------------------------------------------------------
async def test_guardian_without_account_or_email_has_no_channel_status(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-i")
    await _create_guardian_without_account(client, env)
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    item = _item_for_fee(payload, fee["id"])
    assert len(item["guardians"]) == 1
    contact = item["guardians"][0]
    assert contact["has_user_account"] is False
    assert contact["email"] is None
    assert contact["statuses"] == ["NO_CHANNEL"]


# --- J : plusieurs tuteurs -> statuts indépendants -------------------------------------------------------
async def test_multiple_guardians_have_independent_statuses(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-j")
    parent = await _link_parent(client, env, "parent.overdueview-j")
    email_guardian = await _create_guardian_with_email(client, env, "guardian.overdueview-j")
    no_channel_guardian = await _create_guardian_without_account(client, env)
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _run_job_with_emails()

    payload = await _get_overdue(client, env["admin_headers"], env["school_id"])
    item = _item_for_fee(payload, fee["id"])
    assert len(item["guardians"]) == 3

    by_id = {g["guardian_id"]: g for g in item["guardians"]}
    assert by_id[parent["guardian"]["id"]]["statuses"] == ["IN_APP_SENT"]
    assert by_id[email_guardian["guardian"]["id"]]["statuses"] == ["EMAIL_SENT"]
    assert by_id[no_channel_guardian["id"]]["statuses"] == ["NO_CHANNEL"]


# --- K : isolation tenant -------------------------------------------------------------------------------
async def test_admin_a_cannot_read_overdue_fees_of_school_b(client: AsyncClient) -> None:
    env_a = await _setup_student(client, "overdueview-k-a")
    env_b = await _setup_student(client, "overdueview-k-b")
    await _link_parent(client, env_b, "parent.overdueview-k-b")
    await _create_student_fee(client, env_b, PAST_DUE_DATE)
    await _run_job_with_emails()

    response = await client.get(
        "/api/v1/fees/overdue", params={"school_id": env_b["school_id"]}, headers=env_a["admin_headers"]
    )
    assert response.status_code in (403, 404)


# --- L : RBAC — un rôle sans fees.read est refusé ------------------------------------------------------
async def test_teacher_without_fees_permission_is_forbidden(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-l")
    teacher = await _create_user_with_role(client, env["admin_headers"], env["school_id"], "TEACHER", "teacher.overdueview")

    response = await client.get(
        "/api/v1/fees/overdue", params={"school_id": env["school_id"]}, headers=teacher["headers"]
    )
    assert response.status_code == 403


# --- M : pagination ------------------------------------------------------------------------------------
async def test_pagination_splits_results_across_pages(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-m")
    await _link_parent(client, env, "parent.overdueview-m")
    fee_ids = set()
    for i in range(3):
        fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount=str(10000 + i))
        fee_ids.add(fee["id"])
    await _run_job_with_emails()

    page1 = await _get_overdue(client, env["admin_headers"], env["school_id"], page=1, page_size=2)
    assert page1["total"] == 3
    assert page1["total_pages"] == 2
    assert page1["page"] == 1
    assert page1["page_size"] == 2
    assert len(page1["items"]) == 2

    page2 = await _get_overdue(client, env["admin_headers"], env["school_id"], page=2, page_size=2)
    assert page2["page"] == 2
    assert len(page2["items"]) == 1

    seen_ids = {item["student_fee_id"] for item in page1["items"] + page2["items"]}
    assert seen_ids == fee_ids


# --- N : aucun N+1 (le nombre de requêtes SQL ne doit pas croître avec le nombre de lignes) --------------
async def test_list_overdue_fees_does_not_scale_query_count_with_row_count(client: AsyncClient, monkeypatch) -> None:
    env = await _setup_student(client, "overdueview-n")
    await _link_parent(client, env, "parent.overdueview-n")
    await _create_guardian_with_email(client, env, "guardian.overdueview-n")
    await _create_guardian_without_account(client, env)
    for i in range(5):
        await _create_student_fee(client, env, PAST_DUE_DATE, amount=str(10000 + i))
    await _run_job_with_emails()

    call_count = 0
    original_execute = AsyncSession.execute

    async def counting_execute(self, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return await original_execute(self, *args, **kwargs)

    async with AsyncSessionLocal() as db:
        # Priming du contexte tenant AVANT d'activer le compteur : une session brute (hors
        # requête HTTP authentifiée) n'a par défaut aucun contexte RLS ; ce n'est pas une requête
        # de `list_overdue_fees` elle-même et ne doit donc pas être comptée.
        await set_platform_wide_context(db)
        monkeypatch.setattr(AsyncSession, "execute", counting_execute)
        result = await list_overdue_fees(
            db, school_id=uuid.UUID(env["school_id"]), academic_year_id=None, page=1, page_size=20
        )

    assert len(result.items) == 5
    # Comptage + page + tuteurs + élargissement RLS notifications + notifications + rappels email :
    # 6 requêtes fixes, jamais une par ligne ni par tuteur (5 frais x 3 tuteurs chacun aurait donné
    # bien plus de 6 appels avec du N+1 réel).
    assert call_count <= 6, f"{call_count} requêtes SQL exécutées pour 5 frais — suspicion de N+1"


# --- Lecture seule : aucune écriture n'est produite par l'endpoint ---------------------------------------
async def test_endpoint_produces_no_write(client: AsyncClient) -> None:
    env = await _setup_student(client, "overdueview-nowrite")
    await _link_parent(client, env, "parent.overdueview-nowrite")
    await _create_student_fee(client, env, PAST_DUE_DATE)
    await _run_job_with_emails()

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        before = (await db.execute(text("SELECT count(*) FROM notifications"))).scalar_one()
        before_email = (await db.execute(text("SELECT count(*) FROM fee_overdue_email_reminders"))).scalar_one()

    await _get_overdue(client, env["admin_headers"], env["school_id"])

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        after = (await db.execute(text("SELECT count(*) FROM notifications"))).scalar_one()
        after_email = (await db.execute(text("SELECT count(*) FROM fee_overdue_email_reminders"))).scalar_one()

    assert after == before
    assert after_email == before_email
