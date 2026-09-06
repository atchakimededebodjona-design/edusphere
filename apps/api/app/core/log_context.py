"""Phase 23 — corrélation des requêtes (request-id) et contexte de log.

Objectif unique : permettre de retrouver, à partir d'un identifiant fourni par une école
("Request ID : ABC123"), la trace exacte correspondante dans les logs — sans reproduire le
problème, sans fouiller manuellement des logs non corrélés.

Utilise exclusivement `contextvars` (bibliothèque standard) : chaque requête HTTP s'exécute dans
sa propre tâche asyncio, qui reçoit une COPIE du contexte au moment de sa création — une valeur
posée ici pendant une requête ne fuite jamais vers une requête concurrente (propriété standard de
`contextvars`, c'est précisément sa raison d'être pour un serveur asynchrone). Aucun état partagé,
aucun verrou, aucune nouvelle dépendance.

Le `RequestContextFilter` est attaché au(x) handler(s) de logging (voir logging_config.py) : il
enrichit CHAQUE LogRecord qui transite par ce handler avec request_id/user_id/organization_id/
school_id s'ils sont disponibles pour la requête en cours, sans qu'aucun appelant (rate_limit.py,
email.py, main.py...) n'ait à les passer explicitement à chaque appel `logger.xxx(...)`.

Règle absolue reprise de logging_config.py : ne jamais poser ici de valeur sensible (JWT, mot de
passe, jeton, secret) dans une de ces variables de contexte.
"""

import contextvars
import logging
import re
import secrets

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("log_user_id", default=None)
organization_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("log_organization_id", default=None)
school_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("log_school_id", default=None)

# Un request-id entrant (en-tête X-Request-Id fourni par un client/reverse proxy) n'est réutilisé
# que s'il a une forme raisonnable — jamais copié tel quel dans les logs/réponses sinon. Alphanum
# + tiret/underscore, borné à 100 caractères : évite l'injection de retours à la ligne dans un
# format de log qui ne serait pas du JSON (défense en profondeur, même si le formatteur JSON de
# logging_config.py échappe de toute façon correctement ce genre de valeur), et évite qu'un client
# impose un identifiant arbitrairement long ou vide.
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


def is_acceptable_request_id(value: str) -> bool:
    return bool(_REQUEST_ID_PATTERN.match(value))


def generate_request_id() -> str:
    """Identifiant cryptographiquement sûr (`secrets`, jamais `random`/`uuid4` construit à la
    main) — jamais prévisible, jamais dérivé d'un compteur ou d'un timestamp."""
    return secrets.token_hex(16)


class RequestContextFilter(logging.Filter):
    """Attaché à un handler ou un logger : enrichit chaque LogRecord avec le contexte de la
    requête HTTP en cours, s'il existe. Ne modifie jamais le message lui-même — seulement des
    attributs additionnels, lus par `JsonFormatter` (logging_config.py)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.organization_id = organization_id_var.get()
        record.school_id = school_id_var.get()
        return True
