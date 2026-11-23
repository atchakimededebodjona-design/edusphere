"""Photo d'identité d'un compte (2026-11-19, migration 0036).

Même déroulé que la photo d'un élève (students/router.py) : le nouveau fichier est écrit, puis
référencé en base ; l'ancien n'est effacé qu'APRÈS le commit réussi (jamais un compte sans photo
à cause d'un échec). Formats et taille : ceux de la photo élève (`validate_photo_upload` : JPEG,
PNG ou WebP réels, 5 Mio au plus), contrôlés avant tout stockage.

Qui peut la mettre : le compte lui-même (`/auth/me/photo`), ou l'administration de son école
(`/users/{id}/photo`, mêmes règles que la modification d'un compte, voir users/service.py).
"""

import logging
import mimetypes
import uuid

from fastapi import HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import safe_filename, storage
from app.modules.students.service import validate_photo_upload
from app.modules.users.models import User

logger = logging.getLogger(__name__)


async def delete_photo_file_best_effort(path: str) -> None:
    """Fichier qui n'est PLUS référencé en base (commit déjà fait) : un échec laisse au pire un
    fichier orphelin, journalisé, jamais une référence cassée."""
    try:
        await storage.delete(path)
    except Exception:
        logger.error("Échec de suppression d'une photo de compte : path=%s", path, exc_info=True)


async def replace_user_photo(db: AsyncSession, user: User, content: bytes, filename: str | None) -> User:
    validate_photo_upload(content, filename)
    previous = user.photo_path
    path = f"users/{user.id}/photo_{uuid.uuid4().hex}_{safe_filename(filename)}"
    await storage.upload(path, content)
    try:
        user.photo_path = path
        await db.flush()
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        await delete_photo_file_best_effort(path)
        raise
    if previous and previous != path:
        await delete_photo_file_best_effort(previous)
    return user


async def remove_user_photo(db: AsyncSession, user: User) -> None:
    previous = user.photo_path
    if previous is None:
        return  # idempotent
    user.photo_path = None
    await db.flush()
    await db.commit()
    await delete_photo_file_best_effort(previous)


async def user_photo_response(user: User) -> Response:
    if user.photo_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
    content = await storage.download(user.photo_path)
    media_type = mimetypes.guess_type(user.photo_path)[0] or "application/octet-stream"
    # Donnée personnelle : jamais gardée par un cache partagé.
    return Response(content=content, media_type=media_type, headers={"Cache-Control": "private, no-store"})
