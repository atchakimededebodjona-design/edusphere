"""Sprint 1.2 — rappels automatiques de frais scolaires impayés/échus.

Un seul rappel par (StudentFee, tuteur avec compte) — voir
`notifications/service.py::notify_fee_overdue` pour la base structurelle de l'idempotence.
Traite TOUTES les organisations en une seule exécution (job batch plateforme, pas une requête
utilisateur scopée) : le contexte tenant est explicitement élargi via `set_platform_wide_context`
avant toute lecture, motif déjà utilisé par `notifications/service.py::list_school_announcements`.

Règle d'éligibilité (voir Discovery, état production validé) :
- `status != 'CANCELLED'` ;
- `due_date` non nul et strictement dans le passé (`< date.today()`) ;
- solde réel (`amount_due` - paiements `COMPLETED` alloués, jamais le seul champ `status` mis en
  cache — voir `fees/service.py::compute_remaining_balances`) strictement positif.

Ne cible que les tuteurs dont `Guardian.user_id` est renseigné (réutilise
`notifications/service.py::resolve_guardian_user_ids_for_student`, déjà utilisé par
`notify_payment_recorded`/`notify_report_card_published`/`notify_student_absent` — même règle,
aucune logique nouvelle). Un même élève peut avoir plusieurs tuteurs avec compte : chacun reçoit
sa propre notification.

Sprint 1.3 — canal EMAIL, en complément du canal in-app ci-dessus, réservé aux tuteurs SANS
compte utilisateur (`Guardian.user_id IS NULL`) mais avec une adresse email renseignée. Un tuteur
avec compte ne reçoit jamais d'email en plus de sa notification in-app — les deux canaux sont
mutuellement exclusifs par construction (`resolve_guardian_user_ids_for_student` vs
`resolve_guardian_emails_without_account_for_student`, voir notifications/service.py). Idempotence
par tuteur (`fee_overdue_email_reminders`, unique par `(student_fee_id, guardian_id)`), pas par
adresse email — au maximum UN email par (StudentFee, tuteur), jamais renvoyé même si le frais
reste impayé (pas de relance J+7/J+30 dans ce sprint).

Sprint 1.6 — `send_overdue_fee_reminder_emails` enregistre désormais le résultat RÉEL du
transport SMTP (`TRANSPORT_ACCEPTED`/`TRANSPORT_FAILED`) sur la ligne de suivi déjà créée
(`ATTEMPTED` à la préparation), une ligne à la fois, chacune avec son propre commit — jamais un
commit unique pour tout le lot, pour qu'une interruption n'affecte jamais plus d'UNE ligne (voir
SPRINT 1.6 IMPLEMENTATION PLAN §7/§8). Aucun retry automatique, aucune queue : un
`TRANSPORT_FAILED` reste tel quel jusqu'à une décision produit explicite et distincte (non prise
dans ce sprint)."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.email import send_email_best_effort
from app.core.tenancy import set_platform_wide_context
from app.modules.fees.models import FeeOverdueEmailReminder, FeeSchedule, StudentFee
from app.modules.fees.service import compute_remaining_balances
from app.modules.notifications.service import (
    existing_fee_overdue_emailed_guardian_ids,
    notify_fee_overdue,
    resolve_guardian_emails_without_account_for_student,
)
from app.modules.students.models import Student

logger = logging.getLogger(__name__)


@dataclass
class OverdueReminderRunResult:
    eligible_fees: int
    notifications_created: int
    fees_with_new_notifications: int
    # Sprint 1.3 — emails prêts à envoyer, déjà enregistrés comme tentés (voir
    # `_prepare_overdue_emails` ci-dessous) au moment où cette liste est renvoyée : l'envoi réseau
    # proprement dit reste la responsabilité de l'appelant, APRÈS son commit (voir
    # `send_overdue_fee_reminder_emails`). Sprint 1.6 — `reminder_id` ajouté (identifiant de la
    # ligne `FeeOverdueEmailReminder` déjà créée) pour que l'appelant puisse y reporter le
    # résultat réel du transport une fois l'envoi tenté.
    emails: list[tuple[uuid.UUID, str, str, str]] = field(default_factory=list)


async def _list_eligible_overdue_fees(db: AsyncSession) -> list[tuple[StudentFee, str, str]]:
    """`StudentFee` en retard, avec le nom et la devise de leur barème (une seule requête,
    jamais de N+1 — même exigence que `fees/service.py::_allocations_by_fee`)."""
    today = date.today()
    result = await db.execute(
        select(StudentFee, FeeSchedule.name, FeeSchedule.currency)
        .join(FeeSchedule, FeeSchedule.id == StudentFee.fee_schedule_id)
        .where(
            StudentFee.status != "CANCELLED",
            StudentFee.due_date.isnot(None),
            StudentFee.due_date < today,
        )
    )
    return [(row[0], row[1], row[2]) for row in result.all()]


def _format_reminder_body(student: Student, schedule_name: str, balance: Decimal, currency: str) -> str:
    return (
        f"Le paiement de {student.first_name} {student.last_name} pour « {schedule_name} » "
        f"est en retard. Montant restant : {balance} {currency}."
    )


async def _prepare_overdue_emails(
    db: AsyncSession, *, student: Student, fee: StudentFee, reminder_body: str
) -> list[tuple[uuid.UUID, str, str, str]]:
    """Sprint 1.3 — LECTURE + enregistrement du suivi d'idempotence (dans la transaction en
    cours), pour les tuteurs SANS compte utilisateur de cet élève. L'envoi réseau réel n'a lieu
    qu'après le commit de l'appelant (voir `send_overdue_fee_reminder_emails`) — même découplage
    que `report_cards/service.py::prepare_report_card_published_notifications` /
    `send_report_card_published_notifications`.

    Chaque ligne de suivi est écrite dans un SAVEPOINT dédié (`db.begin_nested`) : une exécution
    réellement concurrente du job (hors usage normal — un seul timer, séquentiel) qui gagnerait la
    course sur la contrainte unique `(student_fee_id, guardian_id)` ne doit annuler que CET envoi,
    jamais la transaction entière (qui contient aussi les notifications in-app déjà `flush`ées pour
    d'autres frais).

    Sprint 1.6 — `transport_status="ATTEMPTED"` est renseigné explicitement dès la création (déjà
    la valeur par défaut en base, mais explicite ici pour rester lisible sans consulter le
    modèle) ; l'identifiant de la ligne (déjà généré, nécessaire pour l'idempotence) est renvoyé
    avec chaque email pour que l'appelant puisse y reporter le résultat réel du transport après
    la tentative d'envoi (voir `send_overdue_fee_reminder_emails`)."""
    candidates = await resolve_guardian_emails_without_account_for_student(db, student.id, fee.school_id)
    if not candidates:
        return []

    already_emailed = await existing_fee_overdue_emailed_guardian_ids(db, fee.id)
    subject = f"Paiement en retard — {student.first_name} {student.last_name}"

    emails: list[tuple[uuid.UUID, str, str, str]] = []
    for guardian_id, full_name, email in candidates:
        if guardian_id in already_emailed:
            continue
        reminder_id = uuid.uuid4()
        try:
            async with db.begin_nested():
                db.add(
                    FeeOverdueEmailReminder(
                        id=reminder_id,
                        school_id=fee.school_id,
                        organization_id=fee.organization_id,
                        student_fee_id=fee.id,
                        guardian_id=guardian_id,
                        transport_status="ATTEMPTED",
                    )
                )
                await db.flush()
        except IntegrityError:
            logger.warning(
                "overdue_fee_reminders: email déjà tracé pour (student_fee_id=%s, guardian_id=%s), ignoré.",
                fee.id,
                guardian_id,
            )
            continue
        emails.append((reminder_id, email, subject, f"Bonjour {full_name},\n\n{reminder_body}\n\n— EduLinkage"))

    return emails


async def send_overdue_fee_reminders(db: AsyncSession) -> OverdueReminderRunResult:
    """Point d'entrée unique du job (voir `app/jobs/overdue_fee_reminders.py`). Commit sa propre
    transaction en fin d'exécution — même convention que `notifications/service.py::
    create_announcement` — l'appelant n'a qu'à ouvrir la session et gérer le rollback en cas
    d'exception non atteinte jusqu'ici."""
    await set_platform_wide_context(db)

    rows = await _list_eligible_overdue_fees(db)
    balances = await compute_remaining_balances(db, [row[0] for row in rows])
    overdue_rows = [(fee, schedule_name, currency) for fee, schedule_name, currency in rows if balances[fee.id] > 0]

    if not overdue_rows:
        await db.commit()
        return OverdueReminderRunResult(eligible_fees=0, notifications_created=0, fees_with_new_notifications=0)

    student_ids = {fee.student_id for fee, _, _ in overdue_rows}
    students_result = await db.execute(select(Student).where(Student.id.in_(student_ids)))
    students_by_id = {student.id: student for student in students_result.scalars().all()}

    notifications_created = 0
    fees_with_new_notifications = 0
    emails: list[tuple[uuid.UUID, str, str, str]] = []
    for fee, schedule_name, currency in overdue_rows:
        student = students_by_id.get(fee.student_id)
        if student is None:
            continue
        balance = balances[fee.id]
        reminder_body = _format_reminder_body(student, schedule_name, balance, currency)
        created = await notify_fee_overdue(
            db,
            organization_id=fee.organization_id,
            school_id=fee.school_id,
            student_id=student.id,
            student_fee_id=fee.id,
            title="Paiement en retard",
            body=reminder_body,
        )
        notifications_created += created
        if created > 0:
            fees_with_new_notifications += 1

        emails.extend(await _prepare_overdue_emails(db, student=student, fee=fee, reminder_body=reminder_body))

    await db.commit()
    return OverdueReminderRunResult(
        eligible_fees=len(overdue_rows),
        notifications_created=notifications_created,
        fees_with_new_notifications=fees_with_new_notifications,
        emails=emails,
    )


async def send_overdue_fee_reminder_emails(db: AsyncSession, emails: list[tuple[uuid.UUID, str, str, str]]) -> None:
    """Étape d'ENVOI, à appeler APRÈS le commit de `send_overdue_fee_reminders` (voir
    `report_cards/service.py::send_report_card_published_notifications`, même motif de
    découplage) : la transaction métier (frais, notifications in-app, lignes de suivi créées à
    `ATTEMPTED`) est déjà close et ne dépend jamais du résultat de ce qui suit.

    Sprint 1.6 — `db` sert uniquement à reporter, ligne par ligne, le résultat RÉEL du transport
    SMTP (`TRANSPORT_ACCEPTED`/`TRANSPORT_FAILED`) sur la ligne `FeeOverdueEmailReminder` déjà
    créée — jamais à rouvrir ou modifier quoi que ce soit d'autre. Un commit PAR LIGNE (jamais un
    commit unique pour tout le lot) : une interruption du processus n'affecte donc jamais plus
    d'UNE ligne, qui reste alors à `ATTEMPTED` (jamais reportée comme un succès qu'elle n'a pas
    prouvé). `send_email_best_effort` ne lève jamais — un échec d'envoi n'affecte donc jamais les
    notifications in-app ni les lignes de suivi déjà committées, seul le report du résultat en
    tient compte ici. Aucun retry automatique : un `TRANSPORT_FAILED` reste tel quel jusqu'à une
    décision produit explicite, hors périmètre de ce sprint.

    `db` est une session neuve (voir `app/jobs/overdue_fee_reminders.py::_run`), sans contexte
    tenant encore posé sur CETTE session — `fee_overdue_email_reminders` a la policy RLS
    générique par organisation (migration 0014) : sans élargissement, l'UPDATE ci-dessous
    affecterait silencieusement 0 ligne (jamais une erreur). Même motif que
    `send_overdue_fee_reminders` : job plateforme entière, pas une requête utilisateur scopée."""
    await set_platform_wide_context(db)
    for reminder_id, to, subject, body in emails:
        accepted = await send_email_best_effort(to, subject, body)
        await db.execute(
            update(FeeOverdueEmailReminder)
            .where(FeeOverdueEmailReminder.id == reminder_id)
            .values(
                transport_status="TRANSPORT_ACCEPTED" if accepted else "TRANSPORT_FAILED",
                transport_checked_at=datetime.now(timezone.utc),
            )
        )
        await db.commit()
