"""Observabilité minimale (Phase 16) — un seul `logging.basicConfig`, aucune plateforme externe.

Objectif explicite de cette phase : suffisamment de logs pour diagnostiquer un incident, jamais
plus. Pas d'ELK/Grafana/Prometheus/OpenTelemetry — seulement un format cohérent et un niveau
configurable via `LOG_LEVEL` (déjà présent dans `.env`/`config.py` depuis la Phase 0, jusqu'ici
jamais réellement appliqué : `logging.getLogger(__name__)` sans `basicConfig` conservait le
niveau par défaut de la bibliothèque standard (WARNING) quel que soit `LOG_LEVEL`).

Règle absolue, appliquée dans tout ce module et ses appelants : jamais de mot de passe, token,
secret JWT, ou identifiant SMTP dans un message de log — seuls des identifiants non sensibles
(adresse email destinataire, type d'exception, nom de la vérification en échec) apparaissent.
"""

import logging

from app.core.config import settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging() -> None:
    logging.basicConfig(level=settings.log_level.upper(), format=LOG_FORMAT)
