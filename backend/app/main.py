from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.router import build_api_router
from app.core.config import Settings, get_settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.dependencies import default_pdp
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.security import (
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
    apply_cors,
)
from app.db.session import create_engine, create_session_factory
from app.infra.object_storage import InMemoryObjectStorage, ObjectStorage, S3ObjectStorage
from app.infra.rate_limit import RateLimitMiddleware
from app.infra.redis_client import RedisClient, create_redis
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.iam.application.ports import TokenValidator
from app.modules.iam.infrastructure.jwt_oidc_validator import JwtOidcTokenValidator


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    redis: RedisClient | None = getattr(app.state, "redis", None)
    if redis is not None:
        await redis.aclose()  # type: ignore[attr-defined]
    engine: AsyncEngine | None = getattr(app.state, "engine", None)
    if engine is not None:
        await engine.dispose()


def create_app(
    settings: Settings | None = None,
    *,
    token_validator: TokenValidator | None = None,
    pdp: PolicyDecisionPoint | None = None,
    object_storage: ObjectStorage | None = None,
    redis: RedisClient | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    engine: AsyncEngine | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved)

    openapi_url = f"{resolved.api_v1_prefix}/openapi.json" if resolved.expose_openapi else None
    docs_url = f"{resolved.api_v1_prefix}/docs" if resolved.expose_openapi else None

    app = FastAPI(
        title=resolved.app_name,
        version="0.0.0",
        lifespan=lifespan,
        openapi_url=openapi_url,
        docs_url=docs_url,
        redoc_url=None,
    )
    app.state.settings = resolved
    app.state.engine = engine or create_engine(resolved)
    app.state.session_factory = session_factory or create_session_factory(app.state.engine)
    app.state.redis = redis if redis is not None else create_redis(resolved)
    app.state.object_storage = object_storage or (
        InMemoryObjectStorage() if resolved.app_env == "test" else S3ObjectStorage(resolved)
    )
    app.state.token_validator = token_validator or JwtOidcTokenValidator(resolved)
    app.state.pdp = pdp or default_pdp()

    app.add_middleware(
        RateLimitMiddleware,
        redis=app.state.redis,
        limit_per_minute=resolved.rate_limit_per_minute,
    )
    app.add_middleware(RequestSizeLimitMiddleware, max_bytes=resolved.max_request_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    apply_cors(app, resolved)

    register_exception_handlers(app)
    app.include_router(build_api_router(resolved))
    return app


def app_factory() -> FastAPI:
    return create_app()


app = create_app()


def get_app_state(app_obj: FastAPI) -> dict[str, Any]:
    return {
        "env": app_obj.state.settings.app_env,
        "debug": app_obj.state.settings.app_debug,
    }
