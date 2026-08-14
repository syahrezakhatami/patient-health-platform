from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.shared.enums import AuditResult


@dataclass(frozen=True, slots=True)
class AuditEvent:
    action: str
    resource_type: str
    result: AuditResult
    actor_id: UUID | None = None
    organization_id: UUID | None = None
    facility_id: UUID | None = None
    resource_id: UUID | None = None
    patient_id: UUID | None = None
    purpose: str | None = None
    correlation_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
