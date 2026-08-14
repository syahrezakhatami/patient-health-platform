from uuid import UUID

from app.core.errors import ForbiddenError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision
from app.modules.iam.domain.models import Principal
from app.shared.enums import AuditResult, PrincipalType


async def authorize(
    pdp: PolicyDecisionPoint,
    audit: AuditSink,
    *,
    principal: Principal | None,
    action: str,
    resource_type: str,
    organization_id: UUID | None,
    facility_id: UUID | None = None,
    patient_id: UUID | None = None,
    purpose: str | None = None,
    correlation_id: str | None = None,
) -> AuthorizationDecision:
    context = AuthorizationContext(
        actor_id=None if principal is None else principal.user.id,
        principal_type=PrincipalType.STAFF,
        organization_id=organization_id,
        facility_id=facility_id,
        roles=() if principal is None else tuple(sorted(principal.role_codes)),
        scopes=() if principal is None else tuple(sorted(principal.permission_codes)),
        patient_id=patient_id,
        purpose=purpose,
        emergency_access_id=None,
        resource_type=resource_type,
        action=action,
        actor_organization_ids=() if principal is None else tuple(principal.organization_ids),
        actor_facility_ids=() if principal is None else tuple(principal.facility_ids),
    )
    decision = pdp.evaluate(context)
    if not decision.allowed:
        await audit.record(
            AuditEvent(
                action=action,
                resource_type=resource_type,
                result=AuditResult.DENIED,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization_id,
                facility_id=facility_id,
                patient_id=patient_id,
                purpose=purpose,
                correlation_id=correlation_id,
                metadata={"reason": decision.reason, "policy": decision.policy_reference},
            )
        )
        raise ForbiddenError("Not authorized")
    return decision
