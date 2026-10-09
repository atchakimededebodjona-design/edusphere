"""PR #15 — cadence des relances de frais en retard (paliers J0 / J7 / J30).

Complète `test_overdue_fee_reminders.py` (canal in-app, Sprint 1.2) et
`test_overdue_fee_reminders_email.py` (canal email, Sprint 1.3) sans les modifier — ces deux
fichiers couvrent déjà l'éligibilité de base (non échu / payé / annulé / plusieurs tuteurs /
isolation tenant / RBAC), toujours valable et inchangée par ce PR. Ce fichier couvre
spécifiquement ce qui est NOUVEAU : la progression entre paliers, son impossibilité avant
l'échéance de chacun, son arrêt après paiement complet, sa poursuite après paiement partiel, son
recalcul si `due_date` est modifiée, son indépendance par destinataire, et sa sûreté face à un
redémarrage ou une exécution concurrente du job.

Convention délibérée (voir `tests/test_overdue_fee_reminders.py::PAST_DUE_DATE` pour la même
remarque) : les échéances sont TOUJOURS calculées relativement à `date.today()`, jamais une date
fixe lointaine — un frais "en retard depuis 35 jours" fixé à une date calendaire absolue
deviendrait, d'une exécution de la suite de tests à l'autre (le job est plateforme entière,
jamais scopé à une seule école), une source infinie de nouveaux paliers « rattrapés » par
N'IMPORTE QUEL autre test de ce fichier appelant le job. Les assertions ci-dessous ne lisent
JAMAIS un cumul global (ex. tout le contenu d'un répertoire d'emails, ou le compteur agrégé
renvoyé par le job) : toujours une ligne précise, filtrée par le `student_fee_id`/
`guardian_id`/`recipient_user_id` créés par CE test, par construction unique et donc jamais
pollués par l'historique accumulé d'autres tests.
"""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient
from sqlalchemy import select

import app.core.email as email_module
from app.core.email import LocalEmailProvider
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.fees.models import FeeOverdueEmailReminder
from app.modules.fees.overdue_reminders import send_overdue_fee_reminder_emails, send_overdue_fee_reminders
from app.modules.notifications.models import Notification
from tests.test_overdue_fee_reminders import (
    _create_guardian_without_account,
    _create_student_fee,
    _link_parent,
    _pay,
    _run_job,
    _setup_student,
)
from tests.test_overdue_fee_reminders_email import _create_guardian_with_email


def _days_ago(n: int) -> date:
    return date.today() - timedelta(days=n)


async def _notification_rows_for_recipient(school_id: str, fee_id: str, recipient_id: str) -> list[Notification]:
    """Lecture directe, triée, de TOUTES les notifications FEE_OVERDUE d'un (frais, destinataire)
    précis — jamais un cumul global : `fee_id`/`recipient_id` sont créés par CE test, uniques,
    donc par construction jamais pollués par un autre test ayant appelé le même job."""
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(Notification)
            .where(
                Notification.school_id == uuid.UUID(school_id),
                Notification.student_fee_id == uuid.UUID(fee_id),
                Notification.recipient_user_id == uuid.UUID(recipient_id),
                Notification.type == "FEE_OVERDUE",
            )
            .order_by(Notification.created_at.asc())
        )
        return list(result.scalars().all())


async def _email_rows_for_guardian(school_id: str, fee_id: str, guardian_id: str) -> list[FeeOverdueEmailReminder]:
    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        result = await db.execute(
            select(FeeOverdueEmailReminder)
            .where(
                FeeOverdueEmailReminder.school_id == uuid.UUID(school_id),
                FeeOverdueEmailReminder.student_fee_id == uuid.UUID(fee_id),
                FeeOverdueEmailReminder.guardian_id == uuid.UUID(guardian_id),
            )
            .order_by(FeeOverdueEmailReminder.sent_at.asc())
        )
        return list(result.scalars().all())


# --- 1. J7 effectif, jamais avant, jamais avec J0 dans le même passage --------------------------
async def test_j7_sent_only_on_a_later_run_once_its_threshold_is_reached(client: AsyncClient) -> None:
    env = await _setup_student(client, "stagej7")
    parent = await _link_parent(client, env, "parent.stagej7")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job()
    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"], "le premier passage ne doit produire QUE J0, jamais J7 en plus"

    await _run_job()
    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]


# --- 2. J30 effectif, atteint progressivement (jamais directement) ------------------------------
async def test_j30_reached_progressively_never_skipping_j7(client: AsyncClient) -> None:
    env = await _setup_student(client, "stagej30")
    parent = await _link_parent(client, env, "parent.stagej30")
    fee = await _create_student_fee(client, env, _days_ago(35), amount="50000")

    await _run_job()
    await _run_job()
    await _run_job()

    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7", "J30"]

    # Un quatrième passage ne doit plus jamais rien ajouter — les trois paliers sont épuisés.
    await _run_job()
    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert len(rows) == 3


# --- 3. J7 impossible avant son seuil ------------------------------------------------------------
async def test_j7_impossible_before_its_own_threshold(client: AsyncClient) -> None:
    env = await _setup_student(client, "stagenoj7")
    parent = await _link_parent(client, env, "parent.stagenoj7")
    # 3 jours de retard : J0 éligible, J7 (seuil 7 jours) ne l'est PAS encore.
    fee = await _create_student_fee(client, env, _days_ago(3), amount="50000")

    await _run_job()
    await _run_job()  # un second passage le même jour ne doit rien changer

    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


# --- 4. Paiement complet avant J7 -> plus aucun palier suivant ----------------------------------
async def test_full_payment_before_j7_stops_the_cadence(client: AsyncClient) -> None:
    env = await _setup_student(client, "stagepaidstop")
    parent = await _link_parent(client, env, "parent.stagepaidstop")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job()  # J0
    await _pay(client, env, fee["id"], "50000")
    await _run_job()  # devrait vouloir émettre J7, mais le solde est désormais nul

    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


# --- 5. Paiement partiel -> la cadence continue, avec le solde réel à jour -----------------------
async def test_partial_payment_continues_cadence_with_updated_balance(client: AsyncClient) -> None:
    env = await _setup_student(client, "stagepartial")
    parent = await _link_parent(client, env, "parent.stagepartial")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job()  # J0 — solde encore 50000
    await _pay(client, env, fee["id"], "20000")
    await _run_job()  # J7 — solde désormais 30000

    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]
    assert "30000" in rows[1].body
    assert "50000" not in rows[1].body


# --- 6. due_date modifiée -> les paliers se recalculent depuis la NOUVELLE date -------------------
async def test_due_date_change_recomputes_stages_from_the_new_date(client: AsyncClient) -> None:
    env = await _setup_student(client, "stageduedate")
    parent = await _link_parent(client, env, "parent.stageduedate")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job()  # J0, élève en retard de 10 jours

    # Échéance repoussée : plus que 2 jours de retard -> J7 (seuil 7) ne doit plus être atteint,
    # même s'il l'était avant ce changement.
    patch = await client.patch(
        f"/api/v1/student-fees/{fee['id']}", json={"due_date": str(_days_ago(2))}, headers=env["admin_headers"]
    )
    assert patch.status_code == 200, patch.text
    await _run_job()
    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"], "due_date repoussée : J7 ne doit plus être dû"

    # Échéance avancée bien plus loin dans le passé : J7 redevient (et devient même) éligible —
    # mais un seul palier à la fois reste la règle, jamais un saut direct à J30.
    patch = await client.patch(
        f"/api/v1/student-fees/{fee['id']}", json={"due_date": str(_days_ago(40))}, headers=env["admin_headers"]
    )
    assert patch.status_code == 200, patch.text
    await _run_job()
    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]


# --- 7. NO_CHANNEL : jamais rien, à aucun palier -------------------------------------------------
async def test_guardian_with_no_channel_never_receives_anything_at_any_stage(client: AsyncClient) -> None:
    env = await _setup_student(client, "stagenochannel")
    await _create_guardian_without_account(client, env)  # ni compte, ni email
    fee = await _create_student_fee(client, env, _days_ago(35), amount="50000")

    await _run_job()
    await _run_job()
    await _run_job()

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        notif_count = (
            await db.execute(select(Notification).where(Notification.student_fee_id == uuid.UUID(fee["id"])))
        ).scalars().all()
        email_count = (
            await db.execute(
                select(FeeOverdueEmailReminder).where(FeeOverdueEmailReminder.student_fee_id == uuid.UUID(fee["id"]))
            )
        ).scalars().all()
    assert notif_count == []
    assert email_count == []


# --- 8. SMTP échoué à J0 n'empêche jamais J7 ------------------------------------------------------
async def test_smtp_failure_at_j0_does_not_block_j7(client: AsyncClient, monkeypatch, tmp_path) -> None:
    class FailingProvider:
        async def send(self, to: str, subject: str, body: str, *, from_name=None, reply_to=None) -> None:
            raise RuntimeError("SMTP down (simulé)")

    env = await _setup_student(client, "stagesmtpfail")
    guardian = await _create_guardian_with_email(client, env, "guardian.stagesmtpfail")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    monkeypatch.setattr(email_module, "email_provider", FailingProvider())
    async with AsyncSessionLocal() as db:
        result = await send_overdue_fee_reminders(db)
    async with AsyncSessionLocal() as send_db:
        await send_overdue_fee_reminder_emails(send_db, result.emails)

    rows = await _email_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]
    assert rows[0].transport_status == "TRANSPORT_FAILED"

    # Le palier suivant est tenté normalement malgré l'échec du précédent — provider fonctionnel.
    monkeypatch.setattr(email_module, "email_provider", LocalEmailProvider(str(tmp_path)))
    async with AsyncSessionLocal() as db:
        result = await send_overdue_fee_reminders(db)
    async with AsyncSessionLocal() as send_db:
        await send_overdue_fee_reminder_emails(send_db, result.emails)

    rows = await _email_rows_for_guardian(env["school_id"], fee["id"], guardian["guardian"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]
    assert rows[0].transport_status == "TRANSPORT_FAILED"  # jamais réessayé
    assert rows[1].transport_status == "TRANSPORT_ACCEPTED"  # jamais affecté par l'échec précédent


# --- 9. Redémarrage du job (deux sessions fraîches successives) -> aucune duplication ------------
async def test_job_restart_between_two_runs_never_duplicates(client: AsyncClient) -> None:
    env = await _setup_student(client, "stagerestart")
    parent = await _link_parent(client, env, "parent.stagerestart")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    # Chaque appel à `_run_job()` ouvre sa PROPRE session fraîche (AsyncSessionLocal) — simule
    # exactement un redémarrage du processus entre deux exécutions du timer systemd.
    await _run_job()
    await _run_job()

    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


# --- 10. Exécution concurrente -> au maximum une ligne par (frais, destinataire, palier) ----------
async def test_concurrent_job_executions_never_duplicate_a_stage(client: AsyncClient) -> None:
    import asyncio

    env = await _setup_student(client, "stageconcurrent")
    parent = await _link_parent(client, env, "parent.stageconcurrent")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    async def _run() -> None:
        async with AsyncSessionLocal() as db:
            await send_overdue_fee_reminders(db)

    # Deux exécutions réellement concurrentes (sessions/connexions distinctes) ciblant le MÊME
    # frais : l'index unique partiel (migration 0021) + le SAVEPOINT par ligne
    # (`_create_overdue_in_app_notifications`) doivent garantir qu'une seule gagne la course.
    await asyncio.gather(_run(), _run())

    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0"]


# --- 11. Deux tuteurs du même frais progressent indépendamment -------------------------------------
async def test_two_guardians_of_the_same_fee_progress_independently(client: AsyncClient) -> None:
    env = await _setup_student(client, "stageindependent")
    parent_a = await _link_parent(client, env, "parent.stageindependenta")
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    await _run_job()  # tuteur A : J0 uniquement pour l'instant

    # Tuteur B rattaché APRÈS ce premier passage — jamais vu par le job avant maintenant.
    parent_b = await _link_parent(client, env, "parent.stageindependentb")
    await _run_job()  # tuteur A -> J7 (son prochain palier) ; tuteur B -> J0 (son premier)

    rows_a = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent_a["user"]["id"])
    rows_b = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent_b["user"]["id"])
    assert [r.reminder_stage for r in rows_a] == ["J0", "J7"]
    assert [r.reminder_stage for r in rows_b] == ["J0"]


# --- 12. Lignes créées sans palier explicite -> J0 par défaut (voir migration 0021) ----------------
async def test_email_reminder_row_defaults_to_j0_when_stage_not_specified(client: AsyncClient) -> None:
    """Reproduit, au niveau du modèle, le back-fill effectué par la migration 0021 sur les lignes
    créées avant ce PR (qui représentaient toutes LE rappel unique, donc "J0" par équivalence)."""
    env = await _setup_student(client, "stagedefault")
    guardian = await _create_guardian_with_email(client, env, "guardian.stagedefault")
    fee = await _create_student_fee(client, env, _days_ago(1), amount="50000")

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        row = FeeOverdueEmailReminder(
            id=uuid.uuid4(),
            school_id=uuid.UUID(env["school_id"]),
            organization_id=uuid.UUID(env["org"]["id"]),
            student_fee_id=uuid.UUID(fee["id"]),
            guardian_id=uuid.UUID(guardian["guardian"]["id"]),
        )
        db.add(row)
        await db.commit()
        # `set_platform_wide_context` pose un `SET LOCAL`, effacé par le commit ci-dessus (même
        # piège que Sprint 1.8.1, voir fees/overdue_reminders.py) — à réappliquer avant de relire.
        await set_platform_wide_context(db)
        await db.refresh(row)
        assert row.reminder_stage == "J0"


# --- 13. Scénario migration 0021 : une ancienne relance unique (back-fillée à "J0") n'est jamais
# renvoyée à J0, et autorise bien la progression vers J7/J30 si le frais reste impayé -------------
async def test_pre_pr15_reminder_backfilled_to_j0_unblocks_j7_never_resends_j0(client: AsyncClient) -> None:
    """Reproduit exactement l'état produit par la migration 0021 sur une installation existante :
    un tuteur avait déjà reçu L'UNIQUE rappel (avant ce PR, un seul rappel existait jamais) ; la
    migration a converti cette ligne en `reminder_stage='J0'` (voir sa docstring : "c'est
    exactement ce qu'elle représentait"). Le frais est resté impayé depuis — largement plus de 7
    jours avant même la création de cette ligne historique. Ce test construit directement cet état
    (plutôt que de rejouer la migration SQL elle-même, déjà vérifiée par
    `test_fees_overdue_view.py`/les tests RLS existants) et vérifie le comportement du JOB face à
    lui : jamais un second J0, et J7 bien autorisé dès le prochain passage."""
    env = await _setup_student(client, "stagemigrated")
    parent = await _link_parent(client, env, "parent.stagemigrated")
    # 10 jours de retard : J0 ET J7 sont déjà franchissables au moment de ce test — représente un
    # frais resté impayé depuis bien avant la mise en service de ce PR.
    fee = await _create_student_fee(client, env, _days_ago(10), amount="50000")

    async with AsyncSessionLocal() as db:
        await set_platform_wide_context(db)
        db.add(
            Notification(
                id=uuid.uuid4(),
                school_id=uuid.UUID(env["school_id"]),
                organization_id=uuid.UUID(env["org"]["id"]),
                recipient_user_id=uuid.UUID(parent["user"]["id"]),
                type="FEE_OVERDUE",
                title="Paiement en retard",
                body="Ancien rappel unique, antérieur à PR #15 (simulé déjà back-fillé par la migration 0021).",
                student_fee_id=uuid.UUID(fee["id"]),
                reminder_stage="J0",  # exactement ce que produit la migration 0021 pour ces lignes
            )
        )
        await db.commit()

    await _run_job()
    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"], (
        "le job doit respecter le J0 historique (jamais un second) et autoriser J7 puisque son "
        "seuil est déjà dépassé et qu'aucune ligne J7 n'existe encore"
    )
    assert rows[0].body == "Ancien rappel unique, antérieur à PR #15 (simulé déjà back-fillé par la migration 0021)."

    # Un second passage ne doit plus jamais recréer J0, et respecte J7 déjà envoyé (pas de doublon).
    await _run_job()
    rows = await _notification_rows_for_recipient(env["school_id"], fee["id"], parent["user"]["id"])
    assert [r.reminder_stage for r in rows] == ["J0", "J7"]
