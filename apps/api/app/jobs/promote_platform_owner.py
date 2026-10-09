"""PR #17 — promotion explicite d'un compte EXISTANT en PLATFORM_OWNER (procédure opérateur).

Usage (simulation par défaut, rien n'est écrit) :
    docker compose exec -T api python -m app.jobs.promote_platform_owner --email <email>
Application réelle :
    docker compose exec -T api python -m app.jobs.promote_platform_owner --email <email> --apply

L'email est TOUJOURS fourni par l'opérateur à l'exécution — jamais codé en dur. Voir
`app/modules/platform/owner.py` pour les règles exactes (retrait de SUPER_ADMIN/PLATFORM_SUPPORT
globaux, ajout de PLATFORM_OWNER, refus si le compte est rattaché à une école ou partenaire).

Code de sortie : 0 succès (simulation ou application), 1 refus/échec (aucune modification).
"""

import argparse
import asyncio
import logging
import sys

from app.core.logging_config import configure_logging
from app.db.session import AsyncSessionLocal
from app.modules.platform.owner import PromotionRefused, promote_to_platform_owner

logger = logging.getLogger(__name__)


async def _run(email: str, apply: bool) -> int:
    configure_logging()
    async with AsyncSessionLocal() as db:
        try:
            report = await promote_to_platform_owner(db, email, apply=apply)
        except PromotionRefused as exc:
            logger.error("promote_platform_owner: refusé — %s", exc)
            return 1
        except Exception:
            logger.exception("promote_platform_owner: échec, transaction annulée.")
            return 1

    logger.info(
        "promote_platform_owner: %s — utilisateur %s, rôles avant=%s, après=%s, retirés=%s, "
        "PLATFORM_OWNER ajouté=%s, is_platform_admin positionné=%s.",
        "APPLIQUÉ" if report.applied else "SIMULATION (aucune écriture, relancer avec --apply)",
        report.user_id,
        report.roles_before,
        report.roles_after,
        report.removed_role_codes,
        report.added_platform_owner,
        report.set_platform_admin_flag,
    )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Promouvoir un compte existant en PLATFORM_OWNER.")
    parser.add_argument("--email", required=True, help="Email du compte existant à promouvoir.")
    parser.add_argument("--apply", action="store_true", help="Appliquer réellement (sinon simulation).")
    args = parser.parse_args(argv)
    sys.exit(asyncio.run(_run(args.email, args.apply)))


if __name__ == "__main__":
    main()
