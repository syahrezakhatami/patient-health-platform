import logging
import sys
from collections.abc import MutableMapping
from typing import Any

import structlog

from app.core.config import Settings

_REDACT_KEYS = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "apikey",
        "database_url",
        "database_migration_url",
        "object_storage_access_key",
        "object_storage_secret_key",
        "auth_dev_hs256_secret",
        "nik",
        "note_text",
        "clinical_note",
        "body_text",
        "code_display",
        "value_text",
        "value_numeric",
        "value_boolean",
        "value_code",
        "value_code_system",
        "value_code_display",
        "value_coded",
        "reference_range_low",
        "reference_range_high",
        "document_bytes",
        "dose_numeric",
        "dose_unit",
        "dose",
        "reaction",
        "reaction_display",
        "reaction_code",
        "reaction_code_system",
        "reaction_code_display",
        "severity",
        "criticality",
        "note",
        "consent_note",
        "vaccine_display",
        "vaccine_code",
        "immunization_note",
    }
)


def _redact_secrets(
    _logger: logging.Logger, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    for key in list(event_dict):
        if key.lower() in _REDACT_KEYS:
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging(settings: Settings) -> None:
    """JSON logs in production-like environments; console renderer for local debug."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    shared: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        _redact_secrets,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: structlog.types.Processor
    if settings.app_debug and not settings.is_production:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
