from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.correlation import get_correlation_id
from app.core.errors import error_body


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, max_bytes: int) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.max_bytes = max_bytes

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        length = request.headers.get("content-length")
        if length is not None:
            try:
                size = int(length)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content=error_body(
                        "invalid_content_length",
                        "Invalid Content-Length",
                        get_correlation_id(request),
                    ),
                )
            if size > self.max_bytes:
                return JSONResponse(
                    status_code=413,
                    content=error_body(
                        "payload_too_large",
                        "Request body exceeds the configured limit",
                        get_correlation_id(request),
                    ),
                )
        return await call_next(request)


def apply_cors(app: object, settings: Settings) -> None:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    if not isinstance(app, FastAPI):
        raise TypeError("CORS can only be applied to a FastAPI app")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
    )
