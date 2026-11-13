"""Phase 29, lot C — tâche quotidienne des abonnements : expiration des factures et rappels.

Pour chaque école ayant au moins une période ou une facture émise, dans SA PROPRE transaction et
sous le verrou de l'école (`service.lock_school_subscription`, même ordre de verrouillage que le
lot A) :
1. les factures `ISSUED` dont la validité est dépassée passent en `EXPIRED` (audit, acteur système) ;
2. un rappel de fin de couverture est envoyé au palier applicable (J30, J7 ou J0, voir
   `pricing.coverage_reminder_stage`), une seule fois par période et par palier ;
3. un rappel est envoyé 3 jours avant la fin de validité d'une facture émise et non payée.

Destinataires : les comptes actifs SCHOOL_ADMIN et DIRECTOR de l'école (rôle scopé à l'école, ou
rôle d'organisation sans école). Canal : notification interne uniquement — aucun e-mail ni SMS
dans ce lot. Aucun blocage d'accès (décision « rappels seulement »).

Idempotence : table `subscription_reminders` (index uniques partiels) — relancer la tâche ne crée
jamais un second rappel pour le même palier.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import cast

from sqlalchemy import and_, or_, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.modules.cash.service import school_today
from app.modules.notifications.schemas import NotificationType
from app.modules.notifications.service import create_notifications
from app.modules.rbac.models import Role, UserRole
from app.modules.schools.models import School
from app.modules.subscriptions import pricing
from app.modules.subscriptions.models import (
    INVOICE_STATUS_ISSUED,
    SUBSCRIPTION_CURRENCY,
    SchoolSubscriptionPeriod,
    SubscriptionInvoice,
    SubscriptionReminder,
)
from app.modules.subscriptions.service import (
    expire_stale_invoices_for_school,
    lock_school_subscription,
    school_periods,
    spans,
    utc_now,
)
from app.modules.users.models import User

REMINDER_ROLE_CODES = ("SCHOOL_ADMIN", "DIRECTOR")


@dataclass
class ReminderRunResult:
    schools_considered: int = 0
    invoices_expired: int = 0
    reminders_created: int = 0
    notifications_created: int = 0
    by_stage: dict[str, int] = field(default_factory=dict)


async def reminder_recipient_ids(db: AsyncSession, school: School) -> set[uuid.UUID]:
    result = await db.execute(
        select(UserRole.user_id.distinct())
        .join(Role, Role.id == UserRole.role_id)
        .join(User, User.id == UserRole.user_id)
        .where(
            Role.code.in_(REMINDER_ROLE_CODES),
            User.is_active.is_(True),
            or_(
                UserRole.school_id == school.id,
                and_(UserRole.organization_id == school.organization_id, UserRole.school_id.is_(None)),
            ),
        )
    )
    return {row[0] for row in result.all()}


def _date_fr(value) -> str:
    return value.strftime("%d/%m/%Y")


def _coverage_message(school: School, period: SchoolSubscriptionPeriod, stage: str, days_left: int) -> tuple[str, str, str]:
    what = "Le trimestre gratuit" if period.kind == pricing.PERIOD_KIND_FREE_TRIAL else "L'abonnement"
    end = _date_fr(period.ends_on)
    if stage == pricing.REMINDER_STAGE_J0:
        when = "se termine aujourd'hui" if days_left == 0 else f"a pris fin le {end}"
        return (
            "SUBSCRIPTION_EXPIRED",
            f"Abonnement EduLinkage : {when}",
            f"{what} EduLinkage de {school.name} {when}. Vous pouvez le renouveler à tout moment depuis la page Abonnement.",
        )
    return (
        "SUBSCRIPTION_RENEWAL_DUE",
        f"Abonnement EduLinkage : fin le {end}",
        f"{what} EduLinkage de {school.name} est couvert jusqu'au {end} ({days_left} jour{'s' if days_left > 1 else ''}). "
        "Vous pouvez le renouveler dès maintenant depuis la page Abonnement, sans perdre les jours restants.",
    )


def _invoice_message(invoice: SubscriptionInvoice) -> tuple[str, str, str]:
    end = _date_fr(invoice.expires_at) if invoice.expires_at else "—"
    return (
        "SUBSCRIPTION_INVOICE_DUE",
        f"Facture d'abonnement {invoice.number} à régler",
        f"La facture d'abonnement {invoice.number} ({invoice.total_amount} {SUBSCRIPTION_CURRENCY}, "
        f"{invoice.period_months} mois) est valable jusqu'au {end}. Passé ce délai, une nouvelle facture sera nécessaire.",
    )


async def _reminder_exists(db: AsyncSession, *, period_id=None, invoice_id=None, stage: str) -> bool:
    query = select(SubscriptionReminder.id).where(SubscriptionReminder.stage == stage)
    query = query.where(
        SubscriptionReminder.period_id == period_id if period_id is not None else SubscriptionReminder.invoice_id == invoice_id
    )
    return (await db.execute(query)).first() is not None


async def _send(
    db: AsyncSession,
    school: School,
    recipients: set[uuid.UUID],
    stage: str,
    message: tuple[str, str, str],
    *,
    period_id=None,
    invoice_id=None,
) -> int:
    type_, title, body = message
    db.add(
        SubscriptionReminder(
            id=uuid.uuid4(),
            school_id=school.id,
            organization_id=school.organization_id,
            period_id=period_id,
            invoice_id=invoice_id,
            stage=stage,
            recipients_count=len(recipients),
        )
    )
    await db.flush()
    return await create_notifications(
        db,
        organization_id=school.organization_id,
        school_id=school.id,
        recipient_user_ids=recipients,
        type_=cast(NotificationType, type_),
        title=title,
        body=body,
    )


async def _process_school(db: AsyncSession, school: School, now: datetime, result: ReminderRunResult) -> None:
    await lock_school_subscription(db, school.id)
    result.invoices_expired += await expire_stale_invoices_for_school(db, school.id, now)
    recipients = await reminder_recipient_ids(db, school)

    # Fin de couverture.
    periods = await school_periods(db, school.id)
    today = school_today(school, now)
    state = pricing.compute_state(spans(periods), today)
    if state.state not in (pricing.STATE_NONE, pricing.STATE_SCHEDULED) and state.covered_until is not None:
        target = next((p for p in periods if p.ends_on == state.covered_until), None)
        days_left = (state.covered_until - today).days
        stage = pricing.coverage_reminder_stage(days_left)
        if target is not None and stage is not None and not await _reminder_exists(db, period_id=target.id, stage=stage):
            result.notifications_created += await _send(
                db, school, recipients, stage, _coverage_message(school, target, stage, days_left), period_id=target.id
            )
            result.reminders_created += 1
            result.by_stage[stage] = result.by_stage.get(stage, 0) + 1

    # Facture émise bientôt expirée.
    soon = now + timedelta(days=pricing.INVOICE_REMINDER_DAYS)
    invoices = (
        await db.execute(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.school_id == school.id,
                SubscriptionInvoice.status == INVOICE_STATUS_ISSUED,
                SubscriptionInvoice.expires_at > now,
                SubscriptionInvoice.expires_at <= soon,
            )
        )
    ).scalars()
    for invoice in invoices:
        stage = pricing.REMINDER_STAGE_INVOICE_J3
        if not await _reminder_exists(db, invoice_id=invoice.id, stage=stage):
            result.notifications_created += await _send(
                db, school, recipients, stage, _invoice_message(invoice), invoice_id=invoice.id
            )
            result.reminders_created += 1
            result.by_stage[stage] = result.by_stage.get(stage, 0) + 1


async def run_subscription_reminders(
    db: AsyncSession, now: datetime | None = None, only_school_ids: set[uuid.UUID] | None = None
) -> ReminderRunResult:
    """Une transaction par école : un échec laisse les écoles déjà traitées valides (idempotence).
    `only_school_ids` restreint le passage à ces écoles (exploitation ciblée, tests)."""
    now = now or utc_now()
    result = ReminderRunResult()
    # Opération système sans utilisateur authentifié (app/core/tenancy.py) : l'autorisation réelle
    # reste la sélection explicite des écoles ayant une période ou une facture émise.
    await set_platform_wide_context(db)
    candidates = union(
        select(SchoolSubscriptionPeriod.school_id),
        select(SubscriptionInvoice.school_id).where(SubscriptionInvoice.status == INVOICE_STATUS_ISSUED),
    ).subquery()
    school_ids = [row[0] for row in (await db.execute(select(candidates.c.school_id))).all()]
    if only_school_ids is not None:
        school_ids = [school_id for school_id in school_ids if school_id in only_school_ids]
    await db.commit()

    for school_id in school_ids:
        await set_platform_wide_context(db)
        school = await db.get(School, school_id)
        if school is None:
            await db.rollback()
            continue
        await _process_school(db, school, now, result)
        await db.commit()
        result.schools_considered += 1
    return result
