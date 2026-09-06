"""Observabilité minimale (Phase 16), passée en JSON structuré et corrélée par requête (Phase 23).

Toujours un seul handler stdlib (`logging.StreamHandler`, vers stdout — capté par
`docker compose logs`), aucune plateforme externe. Objectif inchangé depuis la Phase 16 :
suffisamment de logs pour diagnostiquer un incident à distance, jamais plus. Pas d'ELK/Grafana/
Prometheus/OpenTelemetry — seulement un format structuré, cohérent, et désormais corrélable via
`request_id` (voir log_context.py) pour qu'un identifiant fourni par une école pilote
("Request ID : ABC123") retrouve la ligne exacte correspondante sans avoir à reproduire le
problème.

Règle absolue, appliquée dans tout ce module et ses appelants : jamais de mot de passe, token,
secret JWT, ou identifiant SMTP dans un message de log — seuls des identifiants non sensibles
(adresse email destinataire, type d'exception, nom de la vérification en échec) apparaissent.
Cette règle s'étend maintenant explicitement aux champs de contexte injectés par
`RequestContextFilter` : ils ne portent jamais que des identifiants techniques (request_id,
user_id, organization_id, school_id), jamais une valeur métier confidentielle.
"""

import json
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.core.log_context import RequestContextFilter

_CONTEXT_FIELDS = ("request_id", "user_id", "organization_id", "school_id")


class JsonFormatter(logging.Formatter):
    """Une ligne JSON par évènement — volontairement quelques champs simples seulement (pas un
    détail interne par log) : timestamp, level, logger, message, plus le contexte de corrélation
    quand il est disponible, plus la trace d'exception le cas échéant."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in _CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())
