from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.shared.enums import AuthorshipKind, InformationSource, VerificationStatus


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    """Shared provenance envelope for future clinical resources. Not a table in Wave 0."""

    authorship_kind: AuthorshipKind
    information_source: InformationSource
    verification_status: VerificationStatus
    source_organization_id: UUID | None = None
    source_facility_id: UUID | None = None
    source_system_id: UUID | None = None
    source_record_id: str | None = None
    authored_by: UUID | None = None
    authored_at: datetime | None = None
    recorded_at: datetime | None = None
    imported_at: datetime | None = None
    clinical_effective_at: datetime | None = None
