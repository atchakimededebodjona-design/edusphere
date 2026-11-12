"""Job standalone — Phase 29, lot A : attribution du trimestre gratuit des écoles.

Usage manuel :
    docker compose exec -T api python -m app.jobs.grant_free_quarters

Même principe que `app/jobs/overdue_fee_reminders.py` : simple script exécuté au déploiement du
lot A puis toutes les heures par un timer systemd (deploy/systemd/), sans worker ni file de
messages. Idempotent : relancé, il n'attribue jamais un second trimestre gratuit
(voir app/modules/subscriptions/free_quarters.py).

Sans `SUBSCRIPTION_LAUNCH_DATE`, ne fait rien et sort avec le code 0 (réglage pas encore décidé).

Code de sortie : 0 en cas de succès, 1 en cas d'échec — exploitable par systemd (`OnFailure=`) ou
toute supervision externe. Une transaction par école : en cas d'échec, les attributions déjà faites
restent valides, et la relance (idempotente) termine le travail.
"""

import asyncio
import logging
import sys

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.subscriptions.free_quarters import grant_free_quarters

logger = logging.getLogger(__name__)


async def _run() -> int:
    configure_logging()
    if settings.subscription_launch_date is None:
        logger.info("grant_free_quarters: SUBSCRIPTION_LAUNCH_DATE non défini — aucune attribution.")
        return 0
    async with AsyncSessionLocal() as db:
        try:
            result = await grant_free_quarters(db, settings.subscription_launch_date)
        except Exception:
            await db.rollback()
            logger.exception("grant_free_quarters: échec du job ; transaction de l'école en cours annulée.")
            return 1
    logger.info(
        "grant_free_quarters: terminé — %d école(s) sans trimestre gratuit examinée(s), %d trimestre(s) attribué(s).",
        result.schools_considered,
        result.granted,
    )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
