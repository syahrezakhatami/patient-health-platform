from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.core.errors import AppError
from app.modules.clinical_read.domain.enums import TimelineSourceType


@dataclass(frozen=True, slots=True)
class ChartCursor:
    occurred_at: datetime
    source_type: str
    source_id: UUID


def encode_cursor(cursor: ChartCursor) -> str:
    payload = {
        "t": cursor.occurred_at.isoformat(),
        "k": cursor.source_type,
        "id": str(cursor.source_id),
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(raw: str) -> ChartCursor:
    try:
        padded = raw + "=" * ((4 - len(raw) % 4) % 4)
        payload = json.loads(urlsafe_b64decode(padded.encode("ascii")))
        if not isinstance(payload, dict) or set(payload) != {"t", "k", "id"}:
            raise AppError("invalid_cursor", "Pagination cursor is invalid", status_code=422)
        occurred_at = datetime.fromisoformat(payload["t"])
        source_type = payload["k"]
        source_id = UUID(payload["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, AppError) as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError("invalid_cursor", "Pagination cursor is invalid", status_code=422) from exc
    if not isinstance(source_type, str) or not source_type:
        raise AppError("invalid_cursor", "Pagination cursor is invalid", status_code=422)
    try:
        TimelineSourceType(source_type)
    except ValueError as exc:
        raise AppError("invalid_cursor", "Pagination cursor is invalid", status_code=422) from exc
    if occurred_at.tzinfo is None:
        raise AppError("invalid_cursor", "Pagination cursor is invalid", status_code=422)
    return ChartCursor(occurred_at=occurred_at, source_type=source_type, source_id=source_id)


def parse_limit(raw: int | None) -> int:
    if raw is None:
        return 50
    if raw < 1 or raw > 100:
        raise AppError("invalid_limit", "limit must be between 1 and 100", status_code=422)
    return raw
