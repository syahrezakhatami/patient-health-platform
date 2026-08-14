from collections.abc import Awaitable, Callable
from time import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.correlation import get_correlation_id
from app.core.errors import error_body
from app.infra.redis_client import RedisClient


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window IP limiter. Redis is preferred; process memory is a local fallback."""

    def __init__(self, app: object, redis: RedisClient | None, limit_per_minute: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._redis = redis
        self._limit = limit_per_minute
        self._local: dict[str, tuple[int, int]] = {}

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.endswith("/health/live"):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        allowed = await self._allow(client)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content=error_body(
                    "rate_limited",
                    "Too many requests",
                    get_correlation_id(request),
                ),
            )
        return await call_next(request)

    async def _allow(self, client: str) -> bool:
        window = int(time() // 60)
        key = f"rl:{client}:{window}"
        if self._redis is not None:
            try:
                count = await self._redis.incr(key)
                if count == 1:
                    await self._redis.expire(key, 120)
                return int(count) <= self._limit
            except Exception:
                return True
        stored_window, count = self._local.get(client, (window, 0))
        if stored_window != window:
            count = 0
        count += 1
        self._local[client] = (window, count)
        return count <= self._limit
