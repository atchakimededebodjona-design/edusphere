"""Rate limiting du login (Phase 7.2 — durcissement pré-pilote).

Compteur Redis par email (pas par IP — une école entière peut partager une IP derrière un même
réseau, un compteur par IP bloquerait des utilisateurs légitimes ; le compteur par email cible
précisément le brute-force d'un compte donné, la menace explicitement demandée). Appliqué sur la
chaîne email brute, avant toute vérification d'existence du compte : un email inexistant accumule
un compteur identique à un email réel, donc le comportement de limitation ne révèle jamais si un
compte existe.

"Fail open" si Redis est injoignable : Redis n'était utilisé nulle part avant cette phase — en
faire une dépendance dure du login transformerait une panne Redis (jusqu'ici sans impact) en panne
d'authentification totale, un changement de surface de risque plus large que ce qui est demandé.
Le rate limiting est alors simplement désactivé le temps de l'indisponibilité, journalisé en
warning ; l'authentification elle-même (bcrypt, JWT) n'en dépend à aucun moment.
"""

import logging
import uuid

from fastapi import HTTPException, status
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def _get_client() -> Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _redis_client


def _key(email: str) -> str:
    return f"login_attempts:{email.strip().lower()}"


async def ensure_login_not_rate_limited(email: str) -> None:
    """À appeler AVANT toute tentative d'authentification. Lève 429 si le compte (au sens de la
    chaîne email fournie) a dépassé `login_rate_limit_max_attempts` échecs dans la fenêtre
    glissante `login_rate_limit_window_seconds`."""
    try:
        client = _get_client()
        count = await client.get(_key(email))
        if count is not None and int(count) >= settings.login_rate_limit_max_attempts:
            ttl = await client.ttl(_key(email))
            retry_after = max(ttl, 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many login attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — vérification ignorée pour cette requête.")


async def register_failed_login_attempt(email: str) -> None:
    """À appeler après un échec d'authentification (mauvais mot de passe OU compte inexistant —
    même traitement dans les deux cas, pour ne jamais révéler l'existence d'un compte)."""
    try:
        client = _get_client()
        key = _key(email)
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, settings.login_rate_limit_window_seconds)
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — échec de connexion non comptabilisé.")


async def reset_login_attempts(email: str) -> None:
    """À appeler après une authentification réussie — une connexion légitime ne doit pas rester
    pénalisée par des essais précédents."""
    try:
        client = _get_client()
        await client.delete(_key(email))
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — compteur non réinitialisé.")


# --- Mot de passe oublié (Phase 10.1) -------------------------------------------------------
#
# Même principe que le login ci-dessus (compteur Redis par email, fail-open si Redis est
# injoignable, jamais de distinction compte existant/inexistant), fonctions dédiées plutôt que
# généralisation des fonctions login ci-dessus : `POST /auth/login` reste inchangé au caractère
# près (aucune régression possible sur un chemin de sécurité déjà testé), au prix d'une petite
# duplication délibérée. Nécessaire depuis la Phase 9 : cet endpoint déclenche désormais un vrai
# envoi d'email (voir app/core/email.py) — sans limite, il devient un vecteur d'abus (email
# bombing) contre un utilisateur réel, pas seulement une ligne en base comme avant.


def _forgot_password_key(email: str) -> str:
    return f"forgot_password_attempts:{email.strip().lower()}"


async def ensure_forgot_password_not_rate_limited(email: str) -> None:
    """À appeler AVANT `auth/service.py::request_password_reset`. Lève 429 si l'email a dépassé
    `forgot_password_rate_limit_max_attempts` demandes dans la fenêtre
    `forgot_password_rate_limit_window_seconds` — que le compte existe ou non."""
    try:
        client = _get_client()
        key = _forgot_password_key(email)
        count = await client.get(key)
        if count is not None and int(count) >= settings.forgot_password_rate_limit_max_attempts:
            ttl = await client.ttl(key)
            retry_after = max(ttl, 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many password reset requests. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — vérification ignorée pour cette requête (forgot-password).")


async def register_forgot_password_attempt(email: str) -> None:
    """À appeler après CHAQUE demande de réinitialisation (contrairement au login, il n'y a pas
    de distinction échec/succès à ce niveau — la réponse est toujours 202 — donc la demande
    elle-même est comptée, pour limiter l'abus d'envoi d'email plutôt qu'un brute-force)."""
    try:
        client = _get_client()
        key = _forgot_password_key(email)
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, settings.forgot_password_rate_limit_window_seconds)
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — demande non comptabilisée (forgot-password).")


# --- Inscription / création d'organisation (Phase 20) -----------------------------------------
#
# Clé IP, volontairement différente du choix "par email" du login : /auth/register ne représente
# jamais un trafic légitime récurrent partagé par toute une école (contrairement au login, où de
# nombreux utilisateurs réels d'une même école se connectent en continu depuis la même IP) — créer
# une nouvelle organisation est un événement rare, une seule fois par client réel. Une même IP
# dépassant le seuil est donc un signal d'abus (création automatisée de comptes), pas un usage
# scolaire normal. Compte CHAQUE tentative (comme forgot-password), succès ou échec : le volume de
# tentatives est le signal, pas seulement les échecs.


def _register_key(ip: str) -> str:
    return f"register_attempts:{ip}"


async def ensure_register_not_rate_limited(ip: str | None) -> None:
    """À appeler AVANT `auth/service.py::register`."""
    key = _register_key(ip or "unknown")
    try:
        client = _get_client()
        count = await client.get(key)
        if count is not None and int(count) >= settings.register_rate_limit_max_attempts:
            ttl = await client.ttl(key)
            retry_after = max(ttl, 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many registration attempts from this network. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — vérification ignorée pour cette requête (register).")


async def register_registration_attempt(ip: str | None) -> None:
    key = _register_key(ip or "unknown")
    try:
        client = _get_client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, settings.register_rate_limit_window_seconds)
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — tentative non comptabilisée (register).")


# --- Refresh de token (Phase 20) ---------------------------------------------------------------
#
# Clé user_id, PAS le refresh token lui-même : le token tourne à chaque appel (rotation déjà en
# place depuis la Phase 1, `auth/service.py::refresh` révoque l'ancien et en émet un nouveau) —
# une clé basée sur le token ne verrait donc jamais plus d'une requête par fenêtre, quel que soit
# le débit réel d'appels. `user_id` reste stable sur toute la chaîne de rotations et, comme pour le
# login, évite qu'une IP d'école partagée pénalise des utilisateurs légitimes. Vérifié seulement
# APRÈS validation du refresh token présenté (session active, utilisateur trouvé) et AVANT toute
# mutation (révocation/émission) : un jeton invalide ne consomme jamais le compteur d'un vrai
# utilisateur, et une requête rate-limitée ne brûle jamais le jeton encore valide du client.


def _refresh_key(user_id: uuid.UUID) -> str:
    return f"refresh_attempts:{user_id}"


async def ensure_refresh_not_rate_limited(user_id: uuid.UUID) -> None:
    key = _refresh_key(user_id)
    try:
        client = _get_client()
        count = await client.get(key)
        if count is not None and int(count) >= settings.refresh_rate_limit_max_attempts:
            ttl = await client.ttl(key)
            retry_after = max(ttl, 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many refresh attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — vérification ignorée pour cette requête (refresh).")


async def register_refresh_attempt(user_id: uuid.UUID) -> None:
    key = _refresh_key(user_id)
    try:
        client = _get_client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, settings.refresh_rate_limit_window_seconds)
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — tentative non comptabilisée (refresh).")


# --- Vérification publique de bulletin (Phase 20) --------------------------------------------
#
# `GET /report-cards/verify/{code}` (report_cards/router.py) est public, non authentifié : la clé
# IP est la seule disponible. Le code lui-même a 384 bits d'entropie (`generate_opaque_token` =
# `secrets.token_urlsafe(48)`) — le brute-force reste infaisable indépendamment de cette limite ;
# son seul rôle réel est de décourager un scraping automatisé à haut débit. Seuil volontairement
# généreux (voir `config.py`) pour ne jamais bloquer plusieurs parents d'une même école scannant
# chacun leur propre QR le même jour depuis le même réseau.


def _report_card_verify_key(ip: str) -> str:
    return f"report_card_verify_attempts:{ip}"


async def ensure_report_card_verify_not_rate_limited(ip: str | None) -> None:
    key = _report_card_verify_key(ip or "unknown")
    try:
        client = _get_client()
        count = await client.get(key)
        if count is not None and int(count) >= settings.report_card_verify_rate_limit_max_attempts:
            ttl = await client.ttl(key)
            retry_after = max(ttl, 1)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many verification attempts. Please try again later.",
                headers={"Retry-After": str(retry_after)},
            )
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — vérification ignorée pour cette requête (report-card verify).")


async def register_report_card_verify_attempt(ip: str | None) -> None:
    key = _report_card_verify_key(ip or "unknown")
    try:
        client = _get_client()
        count = await client.incr(key)
        if count == 1:
            await client.expire(key, settings.report_card_verify_rate_limit_window_seconds)
    except RedisError:
        logger.warning("Rate limiting Redis indisponible — tentative non comptabilisée (report-card verify).")
