from app.modules.audit.domain.events import AuditEvent


class InMemoryAuditSink:
    """Test sink. Production uses the insert-only SQLAlchemy sink."""

    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)
