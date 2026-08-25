from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.core.config import settings
from app.modules.academics.router import router as academics_router
from app.modules.auth.router import router as auth_router
from app.modules.grades.router import router as grades_router
from app.modules.organizations.router import router as organizations_router
from app.modules.rbac.router import router as rbac_router
from app.modules.report_cards.router import router as report_cards_router
from app.modules.schools.router import router as schools_router
from app.modules.students.router import router as students_router

app = FastAPI(title="EduSphere API", version="0.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix=settings.api_v1_prefix, tags=["health"])
app.include_router(auth_router, prefix=f"{settings.api_v1_prefix}/auth", tags=["auth"])
app.include_router(organizations_router, prefix=f"{settings.api_v1_prefix}/organizations", tags=["organizations"])
app.include_router(schools_router, prefix=f"{settings.api_v1_prefix}/schools", tags=["schools"])
app.include_router(rbac_router, prefix=settings.api_v1_prefix, tags=["rbac"])
app.include_router(academics_router, prefix=settings.api_v1_prefix, tags=["academics"])
app.include_router(students_router, prefix=settings.api_v1_prefix, tags=["students"])
app.include_router(grades_router, prefix=settings.api_v1_prefix, tags=["grades"])
app.include_router(report_cards_router, prefix=settings.api_v1_prefix, tags=["report_cards"])
