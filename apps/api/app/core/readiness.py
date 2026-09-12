"""Vérification de readiness (Phase 16) — dépendances nécessaires au fonctionnement normal.

Distinct de `/health` (`app/api/v1/health.py`) : `/health` répond que le processus API tourne,
sans toucher à aucune dépendance externe — c'est ce que Docker doit interroger pour décider de
redémarrer le conteneur (voir `docker-compose.yml`). `/ready` vérifie réellement PostgreSQL,
Redis et le stockage fichiers — c'est ce qu'un opérateur/orchestrateur doit interroger pour
savoir si le service peut effectivement traiter une requête, pas pour décider de le redémarrer
(une base de données momentanément indisponible ne doit pas faire redémarrer l'API, qui n'y peut
rien).

Chaque vérification est isolée : l'échec de l'une n'empêche jamais les autres de s'exécuter, et
aucune exception ne doit jamais fuiter en dehors de `check_readiness` (elle doit toujours pouvoir
répondre, même si tout le reste est en panne).
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.rate_limit import _get_client
from app.core.storage import storage

logger = logging.getLogger(__name__)

_STORAGE_PROBE_PATH = "_health/probe.txt"


async def _check_database(db: AsyncSession) -> str:
    try:
        await db.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        # Type d'exception loggé, jamais la chaîne de connexion ni les identifiants (déjà
        # exclus : cette exception ne les contient pas, contrairement à un message d'erreur brut
        # qui pourrait apparaître dans une réponse HTTP — voir app/main.py pour ce dernier point).
        logger.error("Readiness check: base de données indisponible", exc_info=True)
        return "error"


async def _check_redis() -> str:
    try:
        await _get_client().ping()
        return "ok"
    except Exception:
        logger.error("Readiness check: Redis indisponible", exc_info=True)
        return "error"


async def _check_storage() -> str:
    try:
        # Écriture réelle via l'abstraction StorageProvider (pas un raccourci spécifique à
        # LocalStorageProvider) — même chemin de sonde réutilisé à chaque appel, pas un nouveau
        # fichier par vérification.
        await storage.upload(_STORAGE_PROBE_PATH, b"ok")
        return "ok"
    except Exception:
        logger.error("Readiness check: stockage fichiers indisponible", exc_info=True)
        return "error"


async def _check_email() -> str:
    """Sprint 1.5 — vérification de CONFIGURATION, jamais une connexion SMTP réelle à chaque
    appel de `/ready` (coûteux, et risqué vis-à-vis d'un vrai fournisseur qui pourrait considérer
    des connexions répétées et rapprochées comme un abus). `EMAIL_PROVIDER=local` est une
    configuration valide et auto-cohérente (voir `app/core/email.py`) — jamais "error" ici, un
    opérateur souhaitant savoir si la production utilise encore ce provider consulte le champ
    `email_provider` de la réponse (voir `app/api/v1/health.py`), qui n'affecte jamais le statut
    global. Seul un `EMAIL_PROVIDER=smtp` sans identifiants est un état réellement cassé — tout
    envoi échouerait à coup sûr — même sévérité que `_check_database`/`_check_redis` ci-dessus, et
    déjà signalé par un `logger.critical` isolé au démarrage (`validate_production_config`), mais
    jamais visible depuis un `GET /ready` jusqu'ici."""
    if settings.email_provider == "smtp" and (not settings.smtp_username or not settings.smtp_password):
        logger.error("Readiness check: EMAIL_PROVIDER=smtp sans SMTP_USERNAME/SMTP_PASSWORD configurés")
        return "error"
    return "ok"


async def check_readiness(db: AsyncSession) -> dict[str, str]:
    return {
        "database": await _check_database(db),
        "redis": await _check_redis(),
        "storage": await _check_storage(),
        "email": await _check_email(),
    }
