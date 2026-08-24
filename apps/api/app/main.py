from fastapi import FastAPI

from app.api.v1.health import router as health_router
from app.core.config import settings

app = FastAPI(title="EduSphere API", version="0.0.0")

app.include_router(health_router, prefix=settings.api_v1_prefix, tags=["health"])
