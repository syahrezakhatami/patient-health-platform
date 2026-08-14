from typing import Protocol

from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision


class PolicyDecisionPoint(Protocol):
    def evaluate(self, context: AuthorizationContext) -> AuthorizationDecision:
        """Return an authorization decision. Deny by default unless a later-wave policy allows."""
        ...
