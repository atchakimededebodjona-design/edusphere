"""Sprint 1.3 — rappels de frais en retard par EMAIL pour les tuteurs SANS compte utilisateur.

Complète `test_overdue_fee_reminders.py` (canal in-app, Sprint 1.2) sans le modifier : réutilise
ses fixtures/helpers (même convention que `test_overdue_fee_reminders_standalone.py`). Isolation
`LocalEmailProvider` par test via `tmp_path` + `monkeypatch`, même motif que
`test_report_cards_notifications.py`/`test_email.py`.

Un tuteur SANS compte utilisateur (`Guardian.user_id IS NULL`) mais avec une adresse email
renseignée reçoit désormais un email — au maximum UN par (StudentFee, tuteur), jamais un renvoi
quotidien tant que le frais reste impayé (voir `fees/overdue_reminders.py`). Un tuteur AVEC compte
ne reçoit jamais d'email en plus de sa notification in-app existante — canaux mutuellement
exclusifs.
"""

import uuid
from pathlib import Path

from httpx import AsyncClient

import app.core.email as email_module
from app.core.email import LocalEmailProvider
from app.db.session import AsyncSessionLocal
from app.modules.fees.overdue_reminders import send_overdue_fee_reminder_emails, send_overdue_fee_reminders
from tests.conftest import unique_email
from tests.test_overdue_fee_reminders import (
    FUTURE_DUE_DATE,
    PAST_DUE_DATE,
    _cancel_fee_directly,
    _create_guardian_without_account,
    _create_student_fee,
    _link_parent,
    _list_fee_overdue_notifications,
    _pay,
    _setup_student,
)


def _read_emails(directory: Path) -> list[str]:
    return [f.read_text(encoding="utf-8") for f in directory.glob("*.txt")]


def _overdue_reminder_emails(directory: Path) -> list[str]:
    """Filtre les emails de rappel de frais en retard (sujet `Paiement en retard — ...`) parmi
    tous les fichiers écrits dans `directory` — certains helpers partagés (`_link_parent` crée un
    compte, `_pay` enregistre un paiement) déclenchent légitimement leurs propres emails
    (bienvenue, reçu de paiement), sans rapport avec le canal Sprint 1.3 testé ici."""
    return [content for content in _read_emails(directory) if "Subject: Paiement en retard" in content]


async def _run_job_with_emails() -> None:
    """Même séquence que `app/jobs/overdue_fee_reminders.py::_run` : commit d'abord (dans
    `send_overdue_fee_reminders`), envoi réseau ensuite."""
    async with AsyncSessionLocal() as db:
        result = await send_overdue_fee_reminders(db)
    await send_overdue_fee_reminder_emails(result.emails)


async def _create_guardian_with_email(client: AsyncClient, env: dict, email_prefix: str) -> dict:
    """Tuteur SANS compte utilisateur mais avec une adresse email — cible du canal email Sprint 1.3."""
    email = unique_email(email_prefix)
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={
                "school_id": env["school_id"],
                "full_name": "Tuteur Email Test",
                "relationship_type": "mother",
                "email": email,
            },
            headers=env["admin_headers"],
        )
    ).json()
    attach = await client.post(
        f"/api/v1/students/{env['student']['id']}/guardians",
        json={"guardian_id": guardian["id"]},
        headers=env["admin_headers"],
    )
    assert attach.status_code == 201, attach.text
    return {"guardian": guardian, "email": email}


async def _link_parent_with_guardian_email(client: AsyncClient, env: dict, prefix: str) -> dict:
    """Tuteur AVEC compte utilisateur ET une adresse `Guardian.email` renseignée — vérifie que le
    canal email n'intervient jamais pour ce cas (canaux mutuellement exclusifs)."""
    parent = await _link_parent(client, env, prefix)
    guardian_email = unique_email(f"{prefix}.guardianemail")
    update = await client.patch(
        f"/api/v1/guardians/{parent['guardian']['id']}",
        json={"email": guardian_email},
        headers=env["admin_headers"],
    )
    assert update.status_code == 200, update.text
    parent["guardian"] = update.json()
    parent["guardian_email"] = guardian_email
    return parent


# --- A : tuteur sans compte + email + frais en retard -> email envoyé -------------------------------
async def test_guardian_without_account_with_email_receives_reminder_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-a")
    guardian = await _create_guardian_with_email(client, env, "guardian.overduemail-a")
    await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")

    await _run_job_with_emails()

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    assert guardian["email"] in emails[0]
    assert "Koffi Test" in emails[0]
    assert "50000" in emails[0]


# --- B : deux exécutions successives -> un seul email -------------------------------------------------
async def test_running_job_twice_sends_only_one_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-b")
    await _create_guardian_with_email(client, env, "guardian.overduemail-b")
    await _create_student_fee(client, env, PAST_DUE_DATE)

    await _run_job_with_emails()
    await _run_job_with_emails()

    assert len(_read_emails(tmp_path)) == 1


# --- C : tuteur sans compte ET sans email -> aucun email -----------------------------------------------
async def test_guardian_without_account_and_without_email_receives_no_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-c")
    await _create_guardian_without_account(client, env)
    await _create_student_fee(client, env, PAST_DUE_DATE)

    await _run_job_with_emails()

    assert _read_emails(tmp_path) == []


# --- D : tuteur avec compte ET email -> in-app uniquement, aucun email supplémentaire ------------------
async def test_guardian_with_account_and_email_receives_only_in_app_notification(
    client: AsyncClient, monkeypatch, tmp_path
) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-d")
    parent = await _link_parent_with_guardian_email(client, env, "parent.overduemail-d")
    await _create_student_fee(client, env, PAST_DUE_DATE)

    await _run_job_with_emails()

    assert len(await _list_fee_overdue_notifications(client, parent["headers"])) == 1
    assert _overdue_reminder_emails(tmp_path) == []


# --- E : plusieurs tuteurs sans compte -> chacun reçoit son propre email -------------------------------
async def test_multiple_guardians_without_accounts_each_receive_own_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-e")
    guardian_1 = await _create_guardian_with_email(client, env, "guardian.overduemail-e1")
    guardian_2 = await _create_guardian_with_email(client, env, "guardian.overduemail-e2")
    await _create_student_fee(client, env, PAST_DUE_DATE)

    await _run_job_with_emails()

    emails = _read_emails(tmp_path)
    assert len(emails) == 2
    assert any(guardian_1["email"] in e for e in emails)
    assert any(guardian_2["email"] in e for e in emails)


# --- F : frais non encore échu -> aucun email ----------------------------------------------------------
async def test_fee_not_yet_due_sends_no_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-f")
    await _create_guardian_with_email(client, env, "guardian.overduemail-f")
    await _create_student_fee(client, env, FUTURE_DUE_DATE)

    await _run_job_with_emails()

    assert _read_emails(tmp_path) == []


# --- G : frais intégralement soldé -> aucun email ------------------------------------------------------
async def test_fully_paid_fee_sends_no_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-g")
    await _create_guardian_with_email(client, env, "guardian.overduemail-g")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE, amount="50000")
    await _pay(client, env, fee["id"], "50000")

    await _run_job_with_emails()

    assert _overdue_reminder_emails(tmp_path) == []


# --- H : frais annulé -> aucun email --------------------------------------------------------------------
async def test_cancelled_fee_sends_no_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-h")
    await _create_guardian_with_email(client, env, "guardian.overduemail-h")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)
    await _cancel_fee_directly(fee["id"])

    await _run_job_with_emails()

    assert _read_emails(tmp_path) == []


# --- J : contenu de l'email limité au strict nécessaire, aucune fuite inter-élève ------------------------
async def test_email_content_never_leaks_another_students_data(client: AsyncClient, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env_a = await _setup_student(client, "overduemail-ja")
    env_b = await _setup_student(client, "overduemail-jb")
    guardian_a = await _create_guardian_with_email(client, env_a, "guardian.overduemail-ja")
    guardian_b = await _create_guardian_with_email(client, env_b, "guardian.overduemail-jb")
    await _create_student_fee(client, env_a, PAST_DUE_DATE, amount="50000")
    await _create_student_fee(client, env_b, PAST_DUE_DATE, amount="75000")

    await _run_job_with_emails()

    emails = _read_emails(tmp_path)
    assert len(emails) == 2
    email_a = next(e for e in emails if guardian_a["email"] in e)
    email_b = next(e for e in emails if guardian_b["email"] in e)

    assert "50000" in email_a and "75000" not in email_a
    assert "75000" in email_b and "50000" not in email_b
    # Un email ne doit jamais être adressé à un autre destinataire que le tuteur concerné.
    assert guardian_b["email"] not in email_a
    assert guardian_a["email"] not in email_b


# --- K : EMAIL_PROVIDER=local écrit correctement l'email (unitaire, sans DB) -----------------------------
async def test_send_overdue_fee_reminder_emails_writes_via_local_provider(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    to = unique_email("directsend.overduemail-k")

    await send_overdue_fee_reminder_emails([(to, "Paiement en retard — Test Eleve", "Corps du message de test.")])

    emails = _read_emails(tmp_path)
    assert len(emails) == 1
    assert to in emails[0]
    assert "Corps du message de test." in emails[0]


# --- Idempotence via la contrainte unique : un guardian_id déjà tracé n'est jamais renvoyé ---------------
async def test_pre_existing_tracking_row_prevents_duplicate_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    """Équivalent, pour le canal email, de `test_overdue_fee_reminders.py::
    test_pre_existing_notification_is_not_duplicated` : une ligne de suivi déjà présente (créée
    hors du job) doit être respectée, jamais recréée ni renvoyée."""
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "overduemail-dup")
    guardian = await _create_guardian_with_email(client, env, "guardian.overduemail-dup")
    fee = await _create_student_fee(client, env, PAST_DUE_DATE)

    from app.core.tenancy import set_platform_wide_context
    from app.modules.fees.models import FeeOverdueEmailReminder

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            FeeOverdueEmailReminder(
                id=uuid.uuid4(),
                school_id=uuid.UUID(env["school_id"]),
                organization_id=uuid.UUID(env["org"]["id"]),
                student_fee_id=uuid.UUID(fee["id"]),
                guardian_id=uuid.UUID(guardian["guardian"]["id"]),
            )
        )
        await db.commit()

    await _run_job_with_emails()

    assert _read_emails(tmp_path) == []


# --- RLS de la nouvelle table (même motif que test_pilot_operations_hardening.py) ------------------------
async def test_fee_overdue_email_reminders_relrowsecurity_and_force_are_set() -> None:
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE relname = 'fee_overdue_email_reminders'"
            )
        )
        row = result.one()
        assert row.relrowsecurity is True
        assert row.relforcerowsecurity is True


async def test_fee_overdue_email_reminders_policy_exists() -> None:
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            text(
                "SELECT polname FROM pg_policy WHERE polrelid = 'fee_overdue_email_reminders'::regclass "
                "AND polname = 'fee_overdue_email_reminders_tenant_isolation'"
            )
        )
        assert result.first() is not None
