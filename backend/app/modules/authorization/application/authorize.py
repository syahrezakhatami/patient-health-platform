from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.facility_scope import facility_tenant_decision
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision
from app.modules.iam.domain.models import Principal
from app.modules.patient_access.domain.models import PatientPrincipal
from app.shared.enums import AuditResult, PrincipalType

_CONCEAL_REASONS = frozenset(
    {
        "patient_identity_mismatch",
        "patient_not_found",
        "facility_not_found",
        "facility_organization_mismatch",
    }
)

AccessPrincipal = Principal | PatientPrincipal | None


async def authorize(
    pdp: PolicyDecisionPoint,
    audit: AuditSink,
    *,
    session: AsyncSession,
    principal: AccessPrincipal,
    action: str,
    resource_type: str,
    organization_id: UUID | None,
    facility_id: UUID | None = None,
    patient_id: UUID | None = None,
    purpose: str | None = None,
    correlation_id: str | None = None,
) -> AuthorizationDecision:
    context = _context(
        principal,
        action=action,
        resource_type=resource_type,
        organization_id=organization_id,
        facility_id=facility_id,
        patient_id=patient_id,
        purpose=purpose,
    )
    decision = pdp.evaluate(context)
    if decision.allowed:
        tenant = await facility_tenant_decision(
            session, facility_id=facility_id, organization_id=organization_id
        )
        if tenant is not None:
            decision = tenant
    if not decision.allowed:
        await audit.record(
            AuditEvent(
                action=action,
                resource_type=resource_type,
                result=AuditResult.DENIED,
                actor_id=_actor_id(principal),
                organization_id=organization_id,
                facility_id=facility_id,
                patient_id=patient_id,
                purpose=purpose,
                correlation_id=correlation_id,
                metadata={"reason": decision.reason, "policy": decision.policy_reference},
            )
        )
        if decision.reason in _CONCEAL_REASONS:
            raise NotFoundError("Resource not found")
        raise ForbiddenError("Not authorized")
    return decision


def _actor_id(principal: AccessPrincipal) -> UUID | None:
    if principal is None:
        return None
    if isinstance(principal, PatientPrincipal):
        return principal.account.id
    return principal.user.id


def _context(
    principal: AccessPrincipal,
    *,
    action: str,
    resource_type: str,
    organization_id: UUID | None,
    facility_id: UUID | None,
    patient_id: UUID | None,
    purpose: str | None,
) -> AuthorizationContext:
    if isinstance(principal, PatientPrincipal):
        return AuthorizationContext(
            actor_id=principal.account.id,
            principal_type=PrincipalType.PATIENT,
            organization_id=organization_id,
            facility_id=facility_id,
            roles=(),
            scopes=tuple(sorted(principal.permission_codes)),
            patient_id=patient_id,
            purpose=purpose,
            emergency_access_id=None,
            resource_type=resource_type,
            action=action,
            actor_organization_ids=(),
            actor_facility_ids=(),
            canonical_patient_identity_id=principal.canonical_patient_identity_id,
            cluster_identity_ids=tuple(sorted(principal.cluster_identity_ids)),
        )
    staff = _staff_for_organization(
        principal if isinstance(principal, Principal) else None,
        organization_id,
    )
    return AuthorizationContext(
        actor_id=None if staff is None else staff.user.id,
        principal_type=PrincipalType.STAFF,
        organization_id=organization_id,
        facility_id=facility_id,
        roles=() if staff is None else tuple(sorted(staff.role_codes)),
        scopes=() if staff is None else tuple(sorted(staff.permission_codes)),
        patient_id=patient_id,
        purpose=purpose,
        emergency_access_id=None,
        resource_type=resource_type,
        action=action,
        actor_organization_ids=() if staff is None else tuple(staff.organization_ids),
        actor_facility_ids=() if staff is None else tuple(staff.facility_ids),
    )


def _staff_for_organization(
    principal: Principal | None, organization_id: UUID | None
) -> Principal | None:
    if principal is None or organization_id is None:
        return principal
    return principal.for_organization(organization_id)
