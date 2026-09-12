"""Job standalone — Sprint 1.2 (rappels automatiques de frais impayés/échus).

Usage manuel :
    docker compose exec -T api python -m app.jobs.overdue_fee_reminders

Aucun Celery/RQ, aucun nouveau service Docker permanent (voir Discovery — pas de
scheduler/worker métier dans ce dépôt) : un simple script Python exécuté ponctuellement, par un
timer systemd en production (voir deploy/systemd/) ou manuellement en développement. N'appelle
jamais de route HTTP interne — ouvre directement une session DB et établit le contexte tenant
nécessaire (`app/modules/fees/overdue_reminders.py::send_overdue_fee_reminders` élargit ce
contexte lui-même, motif déjà utilisé par les annonces plateforme).

Code de sortie : 0 en cas de succès, 1 en cas d'échec (transaction annulée, rien n'est commité
partiellement) — exploitable par systemd (`OnFailure=`) ou toute supervision externe.
"""

import asyncio
import logging
import sys

from app.core.logging_config import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.fees.overdue_reminders import send_overdue_fee_reminder_emails, send_overdue_fee_reminders

logger = logging.getLogger(__name__)


async def _run() -> int:
    configure_logging()
    async with AsyncSessionLocal() as db:
        try:
            result = await send_overdue_fee_reminders(db)
        except Exception:
            await db.rollback()
            logger.exception("overdue_fee_reminders: échec du job, transaction annulée.")
            return 1

    # Sprint 1.3 — envoi réseau pur, APRÈS le commit ci-dessus (déjà effectué à l'intérieur de
    # send_overdue_fee_reminders) : un échec d'envoi ne peut plus jamais affecter les notifications
    # in-app ni les lignes de suivi email déjà committées.
    await send_overdue_fee_reminder_emails(result.emails)

    logger.info(
        "overdue_fee_reminders: terminé — %d frais éligibles, %d notification(s) créée(s) pour %d frais distinct(s), "
        "%d email(s) préparé(s) pour les tuteurs sans compte.",
        result.eligible_fees,
        result.notifications_created,
        result.fees_with_new_notifications,
        len(result.emails),
    )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
