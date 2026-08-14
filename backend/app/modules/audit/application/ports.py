from typing import Protocol

from app.modules.audit.domain.events import AuditEvent


class AuditSink(Protocol):
    async def record(self, event: AuditEvent) -> None:
        """Persist an audit event. Implementations must not update or delete events."""
        ...
