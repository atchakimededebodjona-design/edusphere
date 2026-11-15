"""Job standalone — Phase 29, lot B : rapprochement des paiements Mobile Money (PayGate Global).

Usage manuel :
    docker compose exec -T api python -m app.jobs.subscription_payments_reconcile

Même principe que `app/jobs/subscription_reminders.py` : script lancé par un timer systemd
(deploy/systemd/, toutes les 5 minutes), sans worker ni file de messages. Il vérifie auprès de
PayGate les tentatives encore en cours (notification perdue, écran fermé avant la confirmation),
clôt celles restées sans réponse au-delà de `PAYGATE_PENDING_TIMEOUT_MINUTES`, et fait une dernière
vérification à J+1 de ces dernières (succès tardif). Idempotent : la confirmation se fait sous
verrou, une seule période par facture.

Ne fait rien tant que `SUBSCRIPTION_ONLINE_PAYMENT_ENABLED` est faux (code de sortie 0).
Code de sortie : 0 en cas de succès, 1 si au moins une vérification a échoué (une transaction par
tentative : les autres restent traitées).
"""

import asyncio
import logging
import sys

from app.core.logging_config import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.subscriptions.online_payments import reconcile_online_payments

logger = logging.getLogger(__name__)


async def _run() -> int:
    configure_logging()
    async with AsyncSessionLocal() as db:
        try:
            result = await reconcile_online_payments(db)
        except Exception:
            await db.rollback()
            logger.exception("subscription_payments_reconcile: échec du job.")
            return 1
    if not result.enabled:
        logger.info("subscription_payments_reconcile: paiement en ligne désactivé — rien à faire.")
        return 0
    logger.info(
        "subscription_payments_reconcile: terminé — %d tentative(s) vérifiée(s) (%s), %d erreur(s).",
        result.checked,
        ", ".join(f"{status}={count}" for status, count in sorted(result.by_status.items())) or "aucune",
        result.errors,
    )
    return 1 if result.errors else 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
