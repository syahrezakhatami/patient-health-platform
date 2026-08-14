from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.infra.object_storage import ObjectStorage
from app.infra.redis_client import redis_ping

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    checks: dict[str, str] = {}
    healthy = True

    try:
        async with request.app.state.session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception:
        checks["postgres"] = "error"
        healthy = False

    try:
        await redis_ping(request.app.state.redis)
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"
        healthy = False

    storage: ObjectStorage = request.app.state.object_storage
    try:
        await storage.exists_bucket()
        checks["object_storage"] = "ok"
    except Exception:
        checks["object_storage"] = "error"
        # Object storage is required for readiness in non-test environments.
        if request.app.state.settings.app_env != "test":
            healthy = False

    body: dict[str, Any] = {"status": "ready" if healthy else "not_ready", "checks": checks}
    return JSONResponse(status_code=200 if healthy else 503, content=body)
