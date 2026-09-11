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
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.modules.fees.models import FeeSchedule, StudentFee
from app.modules.fees.service import compute_remaining_balances
from app.modules.notifications.service import notify_fee_overdue
from app.modules.students.models import Student


@dataclass
class OverdueReminderRunResult:
    eligible_fees: int
    notifications_created: int
    fees_with_new_notifications: int


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
    for fee, schedule_name, currency in overdue_rows:
        student = students_by_id.get(fee.student_id)
        if student is None:
            continue
        balance = balances[fee.id]
        created = await notify_fee_overdue(
            db,
            organization_id=fee.organization_id,
            school_id=fee.school_id,
            student_id=student.id,
            student_fee_id=fee.id,
            title="Paiement en retard",
            body=_format_reminder_body(student, schedule_name, balance, currency),
        )
        notifications_created += created
        if created > 0:
            fees_with_new_notifications += 1

    await db.commit()
    return OverdueReminderRunResult(
        eligible_fees=len(overdue_rows),
        notifications_created=notifications_created,
        fees_with_new_notifications=fees_with_new_notifications,
    )
