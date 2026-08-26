from app.modules.authorization.domain.catalog import PATIENT_PERMISSIONS, Permission
from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision
from app.modules.authorization.domain.purpose import Purpose
from app.shared.enums import PrincipalType

_CONCEAL_REASONS = ("patient_identity_mismatch",)


class PatientSelfAccessPDP:
    """Patient self-access PDP. Does not evaluate staff Wave1PolicyPDP."""

    def evaluate(self, context: AuthorizationContext) -> AuthorizationDecision:
        if context.principal_type is not PrincipalType.PATIENT:
            return AuthorizationDecision(
                allowed=False,
                reason="principal_type_denied",
                policy_reference="pdp.patient.principal_type",
                obligations=("audit_denial",),
            )
        if context.action not in PATIENT_PERMISSIONS:
            return AuthorizationDecision(
                allowed=False,
                reason="deny_by_default",
                policy_reference="pdp.patient.unknown_action",
                obligations=("audit_denial",),
            )
        if context.action not in context.scopes:
            return AuthorizationDecision(
                allowed=False,
                reason="missing_permission",
                policy_reference="pdp.patient.missing_permission",
                obligations=("audit_denial",),
            )
        if context.purpose != Purpose.PATIENT_ACCESS.value:
            return AuthorizationDecision(
                allowed=False,
                reason="invalid_purpose",
                policy_reference="pdp.patient.purpose",
                obligations=("audit_denial",),
            )
        canonical = context.canonical_patient_identity_id
        if canonical is None or context.patient_id is None:
            return AuthorizationDecision(
                allowed=False,
                reason="patient_identity_mismatch",
                policy_reference="pdp.patient.self",
                obligations=("audit_denial",),
            )
        if context.action == Permission.PATIENT_ACCOUNT_READ:
            if context.patient_id != canonical:
                return AuthorizationDecision(
                    allowed=False,
                    reason="patient_identity_mismatch",
                    policy_reference="pdp.patient.self",
                    obligations=("audit_denial",),
                )
            return AuthorizationDecision(
                allowed=True,
                reason="patient_self_access",
                policy_reference="pdp.patient.self",
                obligations=("audit_success",),
            )
        if context.organization_id is None:
            return AuthorizationDecision(
                allowed=False,
                reason="missing_organization_scope",
                policy_reference="pdp.patient.organization",
                obligations=("audit_denial",),
            )
        allowed_ids = {canonical, *context.cluster_identity_ids}
        if context.patient_id not in allowed_ids:
            return AuthorizationDecision(
                allowed=False,
                reason="patient_identity_mismatch",
                policy_reference="pdp.patient.self",
                obligations=("audit_denial",),
            )
        return AuthorizationDecision(
            allowed=True,
            reason="patient_self_access",
            policy_reference="pdp.patient.self",
            obligations=("audit_success",),
        )
