from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.patient_access.domain.enums import PatientAccountStatus


@dataclass(frozen=True, slots=True)
class PatientAccount:
    id: UUID
    subject: str
    patient_identity_id: UUID
    status: PatientAccountStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PatientPrincipal:
    account: PatientAccount
    canonical_patient_identity_id: UUID
    cluster_identity_ids: frozenset[UUID]
    permission_codes: frozenset[str]

    @property
    def subject(self) -> str:
        return self.account.subject
