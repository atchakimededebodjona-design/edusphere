from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from app.core.config import settings
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
    # Sprint 1.5 — purement informatif, n'affecte jamais `status`/le code HTTP : seul un moyen
    # simple pour un opérateur de confirmer, sans grep les logs de démarrage, quel provider email
    # tourne réellement en production (voir `checks["email"]` pour la seule vérification qui
    # compte pour la disponibilité — un `EMAIL_PROVIDER=local` valide n'est jamais une "erreur").
    email_provider: str


@router.get("/ready", response_model=ReadinessResponse)
async def ready(db: DbSession, response: Response) -> ReadinessResponse:
    """Readiness — vérifie réellement PostgreSQL, Redis, le stockage fichiers, et la cohérence de
    configuration email (Phase 16 puis Sprint 1.5). Aucune information tenant/utilisateur, aucun
    détail d'erreur technique (chaîne de connexion, message d'exception) n'apparaît dans la
    réponse — uniquement "ok"/"error" par dépendance."""
    checks = await check_readiness(db)
    all_ok = all(value == "ok" for value in checks.values())
    if not all_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if all_ok else "not_ready", checks=checks, email_provider=settings.email_provider
    )
