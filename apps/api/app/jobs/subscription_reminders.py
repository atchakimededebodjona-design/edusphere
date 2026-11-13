"""Job standalone — Phase 29, lot C : expiration des factures d'abonnement et rappels aux écoles.

Usage manuel :
    docker compose exec -T api python -m app.jobs.subscription_reminders

Même principe que `app/jobs/overdue_fee_reminders.py` : simple script quotidien lancé par un timer
systemd (deploy/systemd/), sans worker ni file de messages. Idempotent : relancé le même jour, il
ne crée aucun rappel en double (voir app/modules/subscriptions/reminders.py).

Code de sortie : 0 en cas de succès, 1 en cas d'échec — exploitable par systemd (`OnFailure=`).
Une transaction par école : en cas d'échec, les écoles déjà traitées restent valides.
"""

import asyncio
import logging
import sys

from app.core.logging_config import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.subscriptions.reminders import run_subscription_reminders

logger = logging.getLogger(__name__)


async def _run() -> int:
    configure_logging()
    async with AsyncSessionLocal() as db:
        try:
            result = await run_subscription_reminders(db)
        except Exception:
            await db.rollback()
            logger.exception("subscription_reminders: échec du job ; transaction de l'école en cours annulée.")
            return 1
    logger.info(
        "subscription_reminders: terminé — %d école(s), %d facture(s) expirée(s), %d rappel(s) (%s), %d notification(s).",
        result.schools_considered,
        result.invoices_expired,
        result.reminders_created,
        ", ".join(f"{stage}={count}" for stage, count in sorted(result.by_stage.items())) or "aucun",
        result.notifications_created,
    )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
