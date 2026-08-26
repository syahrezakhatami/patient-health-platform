from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import PHI_ACTION_PREFIXES, Permission
from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision
from app.modules.patient_access.application.patient_pdp import PatientSelfAccessPDP
from app.shared.enums import PrincipalType

_STAFF_PRINCIPAL_TYPES = frozenset(
    {
        PrincipalType.STAFF,
        PrincipalType.PRACTITIONER,
        PrincipalType.AUDITOR,
    }
)


class ProductAccessPDP:
    """Dispatches around frozen Wave1PolicyPDP. Does not modify Wave1PolicyPDP."""

    def __init__(self) -> None:
        self._staff = Wave1PolicyPDP()
        self._patient = PatientSelfAccessPDP()

    def evaluate(self, context: AuthorizationContext) -> AuthorizationDecision:
        if context.principal_type is PrincipalType.PATIENT:
            return self._patient.evaluate(context)
        if context.principal_type not in _STAFF_PRINCIPAL_TYPES:
            return AuthorizationDecision(
                allowed=False,
                reason="principal_type_denied",
                policy_reference="pdp.product.unknown_principal",
                obligations=("audit_denial",),
            )
        if _platform_phi_forbidden(context):
            return AuthorizationDecision(
                allowed=False,
                reason="platform_clinical_forbidden",
                policy_reference="pdp.product.platform_phi",
                obligations=("audit_denial",),
            )
        return self._staff.evaluate(context)


def _platform_phi_forbidden(context: AuthorizationContext) -> bool:
    if Permission.IAM_PLATFORM not in context.scopes:
        return False
    return context.action.startswith(PHI_ACTION_PREFIXES)
