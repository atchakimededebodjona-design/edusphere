"""Trimestre gratuit (Phase 29, lot A — cadrage §5.4 bis, décision du 2026-11-12).

Chaque école reçoit UNE SEULE FOIS une première période gratuite de 3 mois, sans facture :
- école déjà en service : à partir de la date de lancement de la facturation
  (`SUBSCRIPTION_LAUNCH_DATE`) ;
- école créée après : à partir de sa date de création (dans son fuseau horaire).

Attribution par une commande idempotente (`app/jobs/grant_free_quarters.py`), plutôt que dans
chacun des chemins de création d'école (plateforme, partenaire, organisation multi-écoles), qui
restent inchangés. La date de début ne dépend jamais du moment de l'exécution : relancer la
commande ne change rien (contrôle sous verrou + index unique partiel, période jamais modifiée).
"""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.tenancy import set_platform_wide_context
from app.modules.audit import service as audit_service
from app.modules.cash.service import business_date
from app.modules.schools.models import School
from app.modules.subscriptions import pricing
from app.modules.subscriptions.models import SchoolSubscriptionPeriod
from app.modules.subscriptions.service import lock_school_subscription, school_periods, spans, utc_now


@dataclass(frozen=True)
class GrantResult:
    granted: int
    schools_considered: int


def _has_free_trial():
    return exists().where(
        and_(
            SchoolSubscriptionPeriod.school_id == School.id,
            SchoolSubscriptionPeriod.kind == pricing.PERIOD_KIND_FREE_TRIAL,
        )
    )


async def grant_free_quarters(db: AsyncSession, launch_date: date | None, now: datetime | None = None) -> GrantResult:
    """Attribue le trimestre gratuit à toute école qui ne l'a pas encore. Ne fait rien sans date
    de lancement. Une seule transaction : succès complet, ou rien (même contrat que le job des
    rappels de frais)."""
    if launch_date is None:
        return GrantResult(granted=0, schools_considered=0)
    now = now or utc_now()
    # Opération système sans utilisateur authentifié (app/core/tenancy.py) : lecture de toutes les
    # écoles. L'autorisation réelle reste la requête explicite ci-dessous (écoles sans trimestre).
    await set_platform_wide_context(db)
    schools = list(
        (await db.execute(select(School).where(~_has_free_trial()).order_by(School.created_at, School.id))).scalars()
    )

    granted = 0
    for school in schools:
        await lock_school_subscription(db, school.id)
        # Nouveau contrôle SOUS VERROU : une exécution concurrente a pu l'attribuer entre-temps.
        already = (
            await db.execute(
                select(SchoolSubscriptionPeriod.id).where(
                    SchoolSubscriptionPeriod.school_id == school.id,
                    SchoolSubscriptionPeriod.kind == pricing.PERIOD_KIND_FREE_TRIAL,
                )
            )
        ).first()
        if already is not None:
            continue
        periods = await school_periods(db, school.id)
        start = pricing.free_quarter_start(launch_date, business_date(school, school.created_at), spans(periods))
        period = SchoolSubscriptionPeriod(
            id=uuid.uuid4(),
            school_id=school.id,
            organization_id=school.organization_id,
            kind=pricing.PERIOD_KIND_FREE_TRIAL,
            invoice_id=None,
            starts_on=start,
            ends_on=pricing.period_end(start, pricing.FREE_QUARTER_MONTHS),
        )
        db.add(period)
        await db.flush()
        await audit_service.record_audit_event(
            db,
            school_id=school.id,
            organization_id=school.organization_id,
            actor_user_id=None,
            action=audit_service.ACTION_SUBSCRIPTION_FREE_QUARTER_GRANTED,
            entity_type=audit_service.ENTITY_SUBSCRIPTION_PERIOD,
            entity_id=period.id,
            summary=f"Trimestre gratuit attribué du {period.starts_on.isoformat()} au {period.ends_on.isoformat()}",
            metadata={
                "starts_on": period.starts_on.isoformat(),
                "ends_on": period.ends_on.isoformat(),
                "launch_date": launch_date.isoformat(),
            },
        )
        granted += 1

    await db.commit()
    return GrantResult(granted=granted, schools_considered=len(schools))
