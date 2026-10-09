"""PR #16 — canal SMS des rappels de frais en retard (cadence J0/J7/J30 héritée de PR #15).

Complète `test_overdue_fee_reminders.py`/`test_overdue_fee_reminders_email.py`/
`test_fee_reminder_stages.py` sans les modifier. Même convention anti-contamination que
`test_fee_reminder_stages.py` (voir son en-tête) : échéances relatives à `date.today()`,
assertions TOUJOURS scopées par `student_fee_id`/`guardian_id` propres à chaque test, jamais un
cumul global (le job reste plateforme entière).

`SMS_ENABLED` est activé explicitement par chaque test qui en a besoin (monkeypatch de
`app.core.config.settings`), jamais globalement — la valeur par défaut (`false`) reste celle de
tous les autres fichiers de tests de ce dépôt, aucune contamination croisée possible.
"""

import asyncio
import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

import app.core.sms as sms_module
from app.core.config import settings
from app.core.sms import LocalSmsProvider
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.fees.models import FeeOverdueSmsReminder
from app.modules.fees.overdue_reminders import send_overdue_fee_reminder_sms, send_overdue_fee_reminders
from tests.test_overdue_fee_reminders import (
    _create_guardian_without_account,
    _create_student_fee,
    _link_parent,
    _pay,
    _setup_student,
)
from tests.test_overdue_fee_reminders_email import _create_guardian_with_email


def _days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


async def _create_guardian_with_phone(client: AsyncClient, env: dict, phone: str) -> dict:
    """Tuteur SANS compte utilisateur mais avec un numéro de téléphone — cible du canal SMS."""
    guardian = (
        await client.post(
            "/api/v1/guardians",
            json={
                "school_id": env["school_id"],
                "full_name": "Tuteur SMS Test",
                "relationship_type": "father",
                "phone": phone,
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
    return {"guardian": guardian}


async def _set_guardian_phone(client: AsyncClient, env: dict, guardian_id: str, phone: str | None) -> None:
    response = await client.patch(
        f"/api/v1/guardians/{guardian_id}", json={"phone": phone}, headers=env["admin_headers"]
    )
    assert response.status_code == 200, response.text


async def _run_job_with_sms() -> None:
    """Même séquence que `app/jobs/overdue_fee_reminders.py::_run` pour le canal SMS : commit
    d'abord (dans `send_overdue_fee_reminders`), envoi réseau + report du transport ensuite, dans
    une session neuve (même découplage que pour l'email)."""
    async with AsyncSessionLocal() as db:
        result = await send_overdue_fee_reminders(db)
    async with AsyncSessionLocal() as send_db:
        await send_overdue_fee_reminder_sms(send_db, result.sms)


async def _sms_rows_for_guardian(school_id: str, fee_id: str, guardian_id: str) -> list[FeeOverdueSmsReminder]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(FeeOverdueSmsReminder)
            .where(
                FeeOverdueSmsReminder.school_id == uuid.UUID(school_id),
                FeeOverdueSmsReminder.student_fee_id == uuid.UUID(fee_id),
                FeeOverdueSmsReminder.guardian_id == uuid.UUID(guardian_id),
            )
            .order_by(FeeOverdueSmsReminder.created_at.asc())
        )
        return list(result.scalars().all())


@pytest.fixture(autouse=True)
def _enable_sms(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Activé pour CHAQUE test de ce fichier — jamais globalement (voir en-tête). Chaque test
    obtient son propre répertoire `LocalSmsProvider` isolé (fixture `tmp_path` standard de
    pytest), même motif que `test_email.py`."""
    monkeypatch.setattr(settings, "sms_enabled", True)
    monkeypatch.setattr(sms_module, "sms_provider", LocalSmsProvider(str(tmp_path)))


# --- C. Cadence (via le canal SMS) ---------------------------------------------------------------
async def test_sms_j0_effective_for_guardian_with_valid_phone(client: AsyncClient) -> None:
    env = await _setup_student(client, "smscadencej0")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]
    assert rows[0].transport_status == "TRANSPORT_ACCEPTED"
    assert rows[0].provider_message_id is not None


async def test_sms_j7_effective_only_on_a_later_run(client: AsyncClient) -> None:
    env = await _setup_student(client, "smscadencej7")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job_with_sms()
    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"], "jamais deux paliers à la même exécution"

    await _run_job_with_sms()
    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]


async def test_sms_j30_reached_progressively(client: AsyncClient) -> None:
    env = await _setup_student(client, "smscadencej30")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(35), amount="50000")

    await _run_job_with_sms()
    await _run_job_with_sms()
    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7", "J30"]

    await _run_job_with_sms()  # un 4e passage ne doit plus rien ajouter
    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert len(rows) == 3


async def test_sms_idempotent_on_repeated_run_same_day(client: AsyncClient) -> None:
    env = await _setup_student(client, "smsidempotent")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    await _run_job_with_sms()
    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


async def test_sms_concurrent_job_executions_never_duplicate_a_stage(client: AsyncClient) -> None:
    env = await _setup_student(client, "smsconcurrent")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await send_overdue_fee_reminders(db)

    await asyncio.gather(_run(), _run())

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


async def test_sms_full_payment_stops_cadence(client: AsyncClient) -> None:
    env = await _setup_student(client, "smspaidstop")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job_with_sms()
    await _pay(client, env, fee["id"], "50000")
    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


async def test_sms_partial_payment_continues_cadence(client: AsyncClient) -> None:
    env = await _setup_student(client, "smspartial")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job_with_sms()
    await _pay(client, env, fee["id"], "20000")
    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]


async def test_sms_due_date_moved_recomputes_from_new_date(client: AsyncClient) -> None:
    env = await _setup_student(client, "smsduedate")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job_with_sms()  # J0

    patch = await client.patch(
        f"/api/v1/student-fees/{fee['id']}", json={"due_date": str(_days_ago(2))}, headers=env["admin_headers"]
    )
    assert patch.status_code == 200, patch.text
    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"], "J7 ne doit plus être dû après le report d'échéance"


async def test_pre_pr16_fee_with_no_sms_history_starts_cleanly(client: AsyncClient) -> None:
    """Un frais déjà en retard avant l'activation du canal SMS (aucune ligne
    `fee_overdue_sms_reminders` du tout, table nouvellement créée par la migration 0022, jamais
    de back-fill nécessaire) démarre simplement sa cadence SMS normalement, sans aucun traitement
    spécial ni erreur."""
    env = await _setup_student(client, "smslegacyfee")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    await _run_job_with_sms()  # ne doit jamais lever

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


# --- B. Numéros ------------------------------------------------------------------------------------
async def test_guardian_with_invalid_phone_falls_back_to_no_channel_without_crashing(client: AsyncClient) -> None:
    env = await _setup_student(client, "smsinvalid")
    guardian = await _create_guardian_with_phone(client, env, "123")  # jamais un numéro valide
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    await _run_job_with_sms()  # ne doit jamais lever, même avec un numéro invalide en base

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert rows == []


async def test_guardian_with_missing_phone_but_email_falls_back_to_email(client: AsyncClient, monkeypatch, tmp_path) -> None:
    import app.core.email as email_module
    from app.core.email import LocalEmailProvider

    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "smsnophoneemail")
    guardian = await _create_guardian_with_email(client, env, "guardian.smsnophoneemail")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    async with AsyncSessionLocal() as db:
        result = await send_overdue_fee_reminders(db)
    async with AsyncSessionLocal() as send_db:
        await send_overdue_fee_reminder_sms(send_db, result.sms)
    from app.modules.fees.overdue_reminders import send_overdue_fee_reminder_emails

    async with AsyncSessionLocal() as send_db2:
        await send_overdue_fee_reminder_emails(send_db2, result.emails)

    sms_rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert sms_rows == []

    from app.modules.fees.models import FeeOverdueEmailReminder

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        email_rows = (
            await db.execute(
                select(FeeOverdueEmailReminder).where(
                    FeeOverdueEmailReminder.student_fee_id == uuid.UUID(fee["id"]),
                    FeeOverdueEmailReminder.guardian_id == uuid.UUID(guardian["guardian"]["id"]),
                )
            )
        ).scalars().all()
    assert len(email_rows) == 1


async def test_phone_change_between_runs_does_not_break_idempotence(client: AsyncClient) -> None:
    """Cahier des charges PR #16 §11.B : l'identité reste `guardian_id`, jamais le numéro — un
    tuteur qui corrige son numéro entre deux exécutions reste le même destinataire pour la
    cadence (jamais un "nouveau" J0 pour le nouveau numéro, jamais un blocage de J7)."""
    env = await _setup_student(client, "smsphonechange")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job_with_sms()  # J0 envoyé au premier numéro

    await _set_guardian_phone(client, env, guardian["guardian"]["id"], "91234567")
    await _run_job_with_sms()  # J7 attendu, jamais un second J0

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]


# --- D. Routage -------------------------------------------------------------------------------------
async def test_guardian_with_account_never_receives_sms_even_with_phone(client: AsyncClient) -> None:
    """Cahier des charges §7 : un tuteur AVEC compte reçoit uniquement sa notification in-app,
    jamais de SMS, même si `Guardian.phone` est renseigné."""
    env = await _setup_student(client, "smsaccountonly")
    parent = await _link_parent(client, env, "parent.smsaccountonly")
    await _set_guardian_phone(client, env, parent["guardian"]["id"], "90123456")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], parent["guardian"]["id"])
    assert rows == []


async def test_multiple_guardians_sms_and_email_and_in_app_never_mixed(client: AsyncClient, monkeypatch, tmp_path) -> None:
    import app.core.email as email_module
    from app.core.email import LocalEmailProvider

    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    env = await _setup_student(client, "smsmultichannel")
    parent = await _link_parent(client, env, "parent.smsmultichannel")
    sms_guardian = await _create_guardian_with_phone(client, env, "90123456")
    email_guardian = await _create_guardian_with_email(client, env, "guardian.smsmultichannel")
    no_channel_guardian = await _create_guardian_without_account(client, env)
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    async with AsyncSessionLocal() as db:
        result = await send_overdue_fee_reminders(db)
    async with AsyncSessionLocal() as send_db:
        await send_overdue_fee_reminder_sms(send_db, result.sms)
    from app.modules.fees.overdue_reminders import send_overdue_fee_reminder_emails

    async with AsyncSessionLocal() as send_db2:
        await send_overdue_fee_reminder_emails(send_db2, result.emails)

    sms_rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], sms_guardian["guardian"]["id"])
    assert [r.reminder_stage for r in sms_rows] == ["J0"]

    from app.modules.fees.models import FeeOverdueEmailReminder
    from app.modules.notifications.models import Notification

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        email_rows = (
            await db.execute(
                select(FeeOverdueEmailReminder).where(
                    FeeOverdueEmailReminder.guardian_id == uuid.UUID(email_guardian["guardian"]["id"])
                )
            )
        ).scalars().all()
        assert len(email_rows) == 1

        notif_rows = (
            await db.execute(
                select(Notification).where(
                    Notification.recipient_user_id == uuid.UUID(parent["user"]["id"]), Notification.type == "FEE_OVERDUE"
                )
            )
        ).scalars().all()
        assert len(notif_rows) == 1

        no_channel_sms = await _sms_rows_for_guardian(env["school_id"], fee["id"], no_channel_guardian["id"])
        assert no_channel_sms == []


# --- E. Isolation -----------------------------------------------------------------------------------
async def test_sms_never_crosses_schools_or_organizations(client: AsyncClient) -> None:
    env_a = await _setup_student(client, "smsisoa")
    env_b = await _setup_student(client, "smsisob")
    guardian_a = await _create_guardian_with_phone(client, env_a, "90111111")
    guardian_b = await _create_guardian_with_phone(client, env_b, "90222222")
    fee_a = await _create_student_fee(client, env_a, _days_ago(1), amount="10000")
    fee_b = await _create_student_fee(client, env_b, _days_ago(1), amount="20000")

    await _run_job_with_sms()

    rows_a = await _sms_rows_for_guardian(env_a["school_id"], fee_a["id"], guardian_a["guardian"]["id"])
    rows_b = await _sms_rows_for_guardian(env_b["school_id"], fee_b["id"], guardian_b["guardian"]["id"])
    assert len(rows_a) == 1 and rows_a[0].school_id == uuid.UUID(env_a["school_id"])
    assert len(rows_b) == 1 and rows_b[0].school_id == uuid.UUID(env_b["school_id"])
    # Jamais la ligne de l'école A visible en interrogeant l'école B et inversement.
    cross_a = await _sms_rows_for_guardian(env_b["school_id"], fee_a["id"], guardian_a["guardian"]["id"])
    assert cross_a == []


# --- F. Résilience ----------------------------------------------------------------------------------
async def test_one_failing_sms_does_not_block_others_in_the_same_run(client: AsyncClient, monkeypatch) -> None:
    env = await _setup_student(client, "smsresilience")
    failing_guardian = await _create_guardian_with_phone(client, env, "90111111")
    ok_guardian = await _create_guardian_with_phone(client, env, "90222222")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    class PartiallyFailingProvider:
        async def send(self, to: str, body: str) -> str | None:
            if to == "+22890111111":
                raise RuntimeError("Panne simulée pour ce seul numéro")
            return "fake-message-id"

    monkeypatch.setattr(sms_module, "sms_provider", PartiallyFailingProvider())

    await _run_job_with_sms()  # ne doit jamais lever malgré l'échec partiel

    failing_rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], failing_guardian["guardian"]["id"])
    ok_rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], ok_guardian["guardian"]["id"])
    assert failing_rows[0].transport_status == "TRANSPORT_FAILED"
    assert ok_rows[0].transport_status == "TRANSPORT_ACCEPTED"


async def test_sms_transport_failed_at_j0_never_retried_but_j7_proceeds(client: AsyncClient, monkeypatch) -> None:
    """Décision retry explicite (cahier des charges §8, cohérente avec l'email depuis PR #15) :
    un SMS `TRANSPORT_FAILED` au palier J0 n'est jamais réessayé automatiquement pour CE palier —
    seul le palier suivant (J7) est tenté normalement, indépendamment de l'échec précédent."""
    env = await _setup_student(client, "smsretryrule")
    guardian = await _create_guardian_with_phone(client, env, "90123456")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    class FailingProvider:
        async def send(self, to: str, body: str) -> str | None:
            raise RuntimeError("Panne SMS simulée")

    monkeypatch.setattr(sms_module, "sms_provider", FailingProvider())
    await _run_job_with_sms()  # J0 -> échec

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]
    assert rows[0].transport_status == "TRANSPORT_FAILED"

    # Fournisseur réparé : J7 doit être tenté normalement, jamais un nouveau J0.
    import tempfile

    monkeypatch.setattr(sms_module, "sms_provider", LocalSmsProvider(tempfile.mkdtemp()))
    await _run_job_with_sms()

    rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]
    assert rows[0].transport_status == "TRANSPORT_FAILED"  # jamais réessayé
    assert rows[1].transport_status == "TRANSPORT_ACCEPTED"  # jamais affecté par l'échec précédent


async def test_channel_switch_after_email_history_starts_fresh_sms_cadence(
    client: AsyncClient, monkeypatch, tmp_path
) -> None:
    """Documente le comportement exact du cas limite décrit dans
    `fees/overdue_reminders.py::_route_guardians_without_account` : un tuteur déjà relancé par
    EMAIL (SMS désactivé lors de ce premier passage) qui bascule ensuite vers le canal SMS (numéro
    ajouté, SMS activé) démarre sa PROPRE cadence SMS depuis J0, indépendamment de l'historique
    email — comportement délibéré (trois tables de suivi indépendantes), pas une fusion
    automatique entre canaux."""
    import app.core.email as email_module
    from app.core.email import LocalEmailProvider

    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    monkeypatch.setattr(settings, "sms_enabled", False)  # SMS désactivé lors du premier passage
    env = await _setup_student(client, "smschannelswitch")
    guardian = await _create_guardian_with_email(client, env, "guardian.smschannelswitch")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    async with AsyncSessionLocal() as db:
        result = await send_overdue_fee_reminders(db)
    from app.modules.fees.overdue_reminders import send_overdue_fee_reminder_emails

    async with AsyncSessionLocal() as send_db:
        await send_overdue_fee_reminder_emails(send_db, result.emails)

    from app.modules.fees.models import FeeOverdueEmailReminder

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        email_rows = (
            await db.execute(
                select(FeeOverdueEmailReminder).where(
                    FeeOverdueEmailReminder.guardian_id == uuid.UUID(guardian["guardian"]["id"])
                )
            )
        ).scalars().all()
        assert [r.reminder_stage for r in email_rows] == ["J0"]

    # Bascule : numéro ajouté, SMS réactivé (fixture autouse) pour le passage suivant.
    monkeypatch.setattr(settings, "sms_enabled", True)
    await _set_guardian_phone(client, env, guardian["guardian"]["id"], "90123456")
    await _run_job_with_sms()

    sms_rows = await _sms_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in sms_rows] == ["J0"], "la cadence SMS démarre à J0, indépendante de l'historique email"
