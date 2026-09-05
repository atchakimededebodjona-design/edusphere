from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.permissions import DbSession
from app.core.readiness import check_readiness

router = APIRouter()


class HealthResponse(BaseModel):
    status: str


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness — le processus API répond, rien d'autre. Aucune dépendance externe interrogée :
    c'est cet endpoint que le HEALTHCHECK Docker du service `api` utilise (voir
    docker-compose.yml) pour décider d'un redémarrage, jamais /ready (voir readiness.py)."""
    return HealthResponse(status="ok")


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


@router.get("/ready", response_model=ReadinessResponse)
async def ready(db: DbSession, response: Response) -> ReadinessResponse:
    """Readiness — vérifie réellement PostgreSQL, Redis et le stockage fichiers (Phase 16).
    Aucune information tenant/utilisateur, aucun détail d'erreur technique (chaîne de connexion,
    message d'exception) n'apparaît dans la réponse — uniquement "ok"/"error" par dépendance."""
    checks = await check_readiness(db)
    all_ok = all(value == "ok" for value in checks.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ready" if all_ok else "not_ready", checks=checks)
