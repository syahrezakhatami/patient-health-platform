from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.domain.events import AuditEvent
from app.modules.audit.infrastructure.models import AuditEventModel


class SqlAlchemyAuditSink:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def record(self, event: AuditEvent) -> None:
        self._session.add(
            AuditEventModel(
                id=event.id,
                actor_id=event.actor_id,
                organization_id=event.organization_id,
                facility_id=event.facility_id,
                action=event.action,
                resource_type=event.resource_type,
                resource_id=event.resource_id,
                patient_id=event.patient_id,
                purpose=event.purpose,
                result=event.result.value,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
                event_metadata=event.metadata,
            )
        )
        await self._session.flush()
