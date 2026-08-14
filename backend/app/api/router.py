from fastapi import APIRouter

from app.api.v1.router import api_v1_router
from app.core.config import Settings


def build_api_router(settings: Settings) -> APIRouter:
    router = APIRouter()
    router.include_router(api_v1_router, prefix=settings.api_v1_prefix)
    return router
