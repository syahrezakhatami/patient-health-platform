from dataclasses import dataclass
from uuid import UUID

from app.shared.enums import PrincipalType


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    actor_id: UUID | None
    principal_type: PrincipalType
    organization_id: UUID | None
    facility_id: UUID | None
    roles: tuple[str, ...]
    scopes: tuple[str, ...]
    patient_id: UUID | None
    purpose: str | None
    emergency_access_id: UUID | None
    resource_type: str
    action: str
    actor_organization_ids: tuple[UUID, ...] = ()
    actor_facility_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    allowed: bool
    reason: str
    policy_reference: str
    obligations: tuple[str, ...] = ()
