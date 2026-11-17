"""Notifications téléphone (Web Push) — 2026-11-17.

Une annonce prévient ses destinataires même quand EduLinkage est fermé sur leur téléphone :
- chaque navigateur qui accepte les notifications s'enregistre (`register_device`) ;
- à la publication d'une annonce, le serveur envoie une notification chiffrée à chaque appareil des
  destinataires (`send_push_to_users`), APRÈS la réponse à l'administrateur (tâche de fond) ;
- un appareil que le service de notification déclare disparu (404/410) est retiré.

Sécurité :
- l'adresse d'envoi d'un appareil n'est acceptée que chez les services de notification connus, en
  HTTPS : le serveur ne peut jamais être poussé à appeler une adresse quelconque ;
- les adresses d'envoi ne sont jamais journalisées (ce sont des secrets de l'appareil) ;
- sans paire de clés VAPID configurée, rien n'est envoyé.
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.tenancy import set_platform_wide_context
from app.db.session import AsyncSessionLocal
from app.modules.notifications.models import PushDevice

logger = logging.getLogger(__name__)

# Services de notification des navigateurs : Chrome/Edge/Opera/Samsung (Google), Firefox (Mozilla),
# Safari et iPhone (Apple), Edge sous Windows (Microsoft).
ALLOWED_PUSH_HOST_SUFFIXES: tuple[str, ...] = (
    "fcm.googleapis.com",
    "android.googleapis.com",
    "push.services.mozilla.com",
    "push.apple.com",
    "notify.windows.com",
)
PUSH_TTL_SECONDS = 7 * 24 * 60 * 60  # gardée par le service jusqu'à 7 jours si le téléphone est éteint
PUSH_TIMEOUT_SECONDS = 10
PUSH_CONCURRENCY = 8
PUSH_BODY_MAX_CHARS = 180
_GONE_STATUSES = {404, 410}


def is_allowed_push_endpoint(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password or parts.port not in (None, 443):
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in ALLOWED_PUSH_HOST_SUFFIXES)


def _subject() -> str:
    subject = settings.web_push_subject.strip() or settings.public_web_base_url.strip()
    return subject


async def register_device(
    db: AsyncSession, user_id: uuid.UUID, endpoint: str, p256dh: str, auth: str, user_agent: str | None
) -> None:
    """Enregistre (ou ré-enregistre) l'appareil pour ce compte. Un même navigateur ne sert qu'un
    compte à la fois : s'il était enregistré pour un autre compte (poste partagé), il lui est
    retiré — d'où le contexte plateforme pour cette seule opération, l'adresse d'envoi (secret détenu
    par ce navigateur) prouvant qu'il s'agit bien de cet appareil."""
    await set_platform_wide_context(db)
    await db.execute(delete(PushDevice).where(PushDevice.endpoint == endpoint))
    db.add(
        PushDevice(
            id=uuid.uuid4(),
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_agent=(user_agent or "")[:255] or None,
        )
    )
    try:
        await db.commit()
    except IntegrityError:
        # Deux enregistrements simultanés du même appareil : le premier arrivé suffit.
        await db.rollback()


async def forget_device(db: AsyncSession, user_id: uuid.UUID, endpoint: str) -> None:
    """Retire l'appareil de CE compte (déconnexion, désactivation). Sans effet sinon."""
    await db.execute(delete(PushDevice).where(PushDevice.endpoint == endpoint, PushDevice.user_id == user_id))
    await db.commit()


def _deliver(endpoint: str, p256dh: str, auth: str, data: str) -> int | None:
    """Envoi d'UNE notification (bibliothèque synchrone, exécutée dans un fil). Statut HTTP du
    service de notification, ou None si aucune réponse."""
    from pywebpush import WebPushException, webpush

    try:
        response = webpush(
            subscription_info={"endpoint": endpoint, "keys": {"p256dh": p256dh, "auth": auth}},
            data=data,
            vapid_private_key=settings.web_push_vapid_private_key.strip(),
            vapid_claims={"sub": _subject()},
            ttl=PUSH_TTL_SECONDS,
            timeout=PUSH_TIMEOUT_SECONDS,
        )
        return int(getattr(response, "status_code", 201))
    except WebPushException as exc:
        return exc.response.status_code if exc.response is not None else None
    except Exception:  # réseau, clé invalide… : jamais d'erreur remontée à l'annonce
        logger.warning("Notification téléphone non envoyée (erreur d'envoi).")
        return None


def announcement_payload(school_name: str, title: str, body: str) -> dict[str, Any]:
    text = f"{title} — {body}".replace("\n", " ").strip()
    if len(text) > PUSH_BODY_MAX_CHARS:
        text = text[: PUSH_BODY_MAX_CHARS - 1].rstrip() + "…"
    return {
        "title": f"Nouvelle annonce — {school_name}",
        "body": text,
        "url": "/open-notifications",
        "tag": "edulinkage-announcement",
    }


async def send_push_to_users(user_ids: set[uuid.UUID], payload: dict[str, Any]) -> dict[str, int]:
    """Envoie `payload` à tous les appareils de `user_ids`. Tâche de fond : ne lève jamais
    d'erreur. Renvoie le décompte (envoyées, retirées, échecs) pour le journal et les tests."""
    summary = {"sent": 0, "removed": 0, "failed": 0}
    if not settings.web_push_enabled or not user_ids:
        return summary
    try:
        async with AsyncSessionLocal() as db:
            await set_platform_wide_context(db)
            rows = (
                await db.execute(
                    select(PushDevice.id, PushDevice.endpoint, PushDevice.p256dh, PushDevice.auth).where(
                        PushDevice.user_id.in_(user_ids)
                    )
                )
            ).all()
        if not rows:
            return summary
        data = json.dumps(payload, ensure_ascii=False)
        semaphore = asyncio.Semaphore(PUSH_CONCURRENCY)

        async def one(endpoint: str, p256dh: str, auth: str) -> int | None:
            async with semaphore:
                return await asyncio.to_thread(_deliver, endpoint, p256dh, auth, data)

        statuses = await asyncio.gather(*(one(row.endpoint, row.p256dh, row.auth) for row in rows))
        sent_ids = [row.id for row, code in zip(rows, statuses) if code is not None and 200 <= code < 300]
        gone_ids = [row.id for row, code in zip(rows, statuses) if code in _GONE_STATUSES]
        summary = {"sent": len(sent_ids), "removed": len(gone_ids), "failed": len(rows) - len(sent_ids) - len(gone_ids)}
        async with AsyncSessionLocal() as db:
            await set_platform_wide_context(db)
            if gone_ids:
                await db.execute(delete(PushDevice).where(PushDevice.id.in_(gone_ids)))
            if sent_ids:
                await db.execute(
                    update(PushDevice).where(PushDevice.id.in_(sent_ids)).values(last_sent_at=datetime.now(timezone.utc))
                )
            await db.commit()
        logger.info(
            "Notifications téléphone : %s envoyée(s), %s appareil(s) retiré(s), %s échec(s).",
            summary["sent"],
            summary["removed"],
            summary["failed"],
        )
    except Exception:
        logger.exception("Envoi des notifications téléphone interrompu.")
    return summary
