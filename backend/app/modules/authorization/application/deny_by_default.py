from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision


class DenyByDefaultPDP:
    """Wave 0 PDP skeleton. No role shortcut. Full policies arrive in the Consent/PDP wave."""

    def evaluate(self, context: AuthorizationContext) -> AuthorizationDecision:
        del context
        return AuthorizationDecision(
            allowed=False,
            reason="deny_by_default",
            policy_reference="pdp.wave0.deny_by_default",
            obligations=("audit_denial",),
        )
