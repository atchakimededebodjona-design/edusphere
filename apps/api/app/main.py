import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.health import router as health_router
from app.core.config import settings
from app.core.logging_config import configure_logging
from app.modules.academics.router import router as academics_router
from app.modules.attendance.router import router as attendance_router
from app.modules.auth.router import router as auth_router
from app.modules.grades.router import router as grades_router
from app.modules.organizations.router import router as organizations_router
from app.modules.parent.router import router as parent_router
from app.modules.rbac.router import router as rbac_router
from app.modules.report_cards.router import router as report_cards_router
from app.modules.schools.router import router as schools_router
from app.modules.students.router import router as students_router
from app.modules.users.router import router as users_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 16 — observabilité minimale : sans ce basicConfig, LOG_LEVEL (présent depuis la
    # Phase 0) n'était jamais réellement appliqué et les logger.warning() existants (email.py,
    # rate_limit.py) dépendaient du comportement par défaut non configuré de la bibliothèque
    # standard.
    configure_logging()
    logger.info("EduSphere API démarrée (environment=%s)", settings.environment)
    yield


app = FastAPI(title="EduSphere API", version="0.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Phase 16 — garantit une ligne de log exploitable pour toute exception qui échapperait
    encore à la gestion explicite d'un module (ex. IntegrityError non interceptée, findings déjà
    documentés en Phase 14/15 Discovery), sans jamais exposer de trace technique au client.
    N'intercepte PAS HTTPException (401/403/404/409...) : FastAPI lui garde son propre
    gestionnaire, plus spécifique, qui reste prioritaire — comportement de ces réponses
    inchangé."""
    logger.error("Exception non gérée sur %s %s", request.method, request.url.path, exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error"})


app.include_router(health_router, prefix=settings.api_v1_prefix, tags=["health"])
app.include_router(auth_router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])
app.include_router(organizations_router, prefix=f"{settings.api_v1_prefix}/organizations", tags=["organizations"])
app.include_router(schools_router, prefix=f"{settings.api_v1_prefix}/schools", tags=["schools"])
app.include_router(rbac_router, prefix=settings.api_v1_prefix, tags=["rbac"])
app.include_router(academics_router, prefix=settings.api_v1_prefix, tags=["academics"])
app.include_router(students_router, prefix=settings.api_v1_prefix, tags=["students"])
app.include_router(grades_router, prefix=settings.api_v1_prefix, tags=["grades"])
app.include_router(report_cards_router, prefix=settings.api_v1_prefix, tags=["report_cards"])
app.include_router(users_router, prefix=f"{settings.api_v1_prefix}/users", tags=["users"])
app.include_router(attendance_router, prefix=settings.api_v1_prefix, tags=["attendance"])
app.include_router(parent_router, prefix=settings.api_v1_prefix, tags=["parent"])
