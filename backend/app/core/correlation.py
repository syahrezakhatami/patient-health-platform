import re
from collections.abc import Awaitable, Callable
from uuid import uuid4

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

CORRELATION_HEADER = "X-Correlation-ID"
_CORRELATION_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
)


def new_correlation_id() -> str:
    return str(uuid4())


def normalize_correlation_id(value: str | None) -> str:
    if value is None:
        return new_correlation_id()
    candidate = value.strip()
    if not candidate or not _CORRELATION_PATTERN.fullmatch(candidate):
        return new_correlation_id()
    return candidate


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        correlation_id = normalize_correlation_id(request.headers.get(CORRELATION_HEADER))
        request.state.correlation_id = correlation_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            request_id=correlation_id,
            service="patient-health-platform",
        )
        response = await call_next(request)
        response.headers[CORRELATION_HEADER] = correlation_id
        return response


def get_correlation_id(request: Request) -> str:
    value = getattr(request.state, "correlation_id", None)
    if isinstance(value, str) and value:
        return value
    return new_correlation_id()
