from fastapi import APIRouter

from app.core.dependencies import CurrentAuth, CurrentPDP
from app.modules.authorization.domain.models import AuthorizationContext
from app.shared.enums import PrincipalType

router = APIRouter(tags=["auth"])


@router.get("/auth/context")
async def auth_context(auth: CurrentAuth, pdp: CurrentPDP) -> dict[str, object]:
    """Protected introspection. Confirms token validation. Not a clinical API."""
    decision = pdp.evaluate(
        AuthorizationContext(
            actor_id=None,
            principal_type=PrincipalType.SYSTEM,
            organization_id=None,
            facility_id=None,
            roles=(),
            scopes=(),
            patient_id=None,
            purpose="platform_introspection",
            emergency_access_id=None,
            resource_type="AuthContext",
            action="read",
        )
    )
    return {
        "subject": auth.subject,
        "issuer": auth.issuer,
        "audience": auth.audience,
        "authorization": {
            "allowed": decision.allowed,
            "reason": decision.reason,
            "policy_reference": decision.policy_reference,
        },
    }
