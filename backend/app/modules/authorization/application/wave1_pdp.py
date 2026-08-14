from uuid import UUID

from app.modules.authorization.application.deny_by_default import DenyByDefaultPDP
from app.modules.authorization.domain.catalog import (
    CATALOG_PERMISSIONS,
    ORG_SCOPED_PERMISSIONS,
    Permission,
)
from app.modules.authorization.domain.models import AuthorizationContext, AuthorizationDecision


class Wave1PolicyPDP:
    """Wave 1 PDP.

    Unknown actions remain deny-by-default (Wave 0).
    Wave 1 actions are allowed only when the permission is present in scopes
    and organization isolation holds. Role names are never inspected.
    """

    def __init__(self) -> None:
        self._fallback = DenyByDefaultPDP()

    def evaluate(self, context: AuthorizationContext) -> AuthorizationDecision:
        if context.action not in CATALOG_PERMISSIONS:
            return self._fallback.evaluate(context)

        if context.actor_id is None:
            return AuthorizationDecision(
                allowed=False,
                reason="unprovisioned_actor",
                policy_reference="pdp.wave1.unprovisioned_actor",
                obligations=("audit_denial",),
            )

        if context.action not in context.scopes:
            return AuthorizationDecision(
                allowed=False,
                reason="missing_permission",
                policy_reference="pdp.wave1.missing_permission",
                obligations=("audit_denial",),
            )

        if Permission.IAM_PLATFORM in context.scopes:
            return AuthorizationDecision(
                allowed=True,
                reason="platform_scope",
                policy_reference="pdp.wave1.platform_scope",
                obligations=("audit_success",),
            )

        if context.action in ORG_SCOPED_PERMISSIONS:
            if context.organization_id is None:
                return AuthorizationDecision(
                    allowed=False,
                    reason="missing_organization_scope",
                    policy_reference="pdp.wave1.missing_organization_scope",
                    obligations=("audit_denial",),
                )
            if not _organization_allowed(context.organization_id, context.actor_organization_ids):
                return AuthorizationDecision(
                    allowed=False,
                    reason="organization_scope_denied",
                    policy_reference="pdp.wave1.organization_scope_denied",
                    obligations=("audit_denial",),
                )
            if context.facility_id is not None and not _facility_allowed(
                context.facility_id, context.actor_facility_ids
            ):
                return AuthorizationDecision(
                    allowed=False,
                    reason="facility_scope_denied",
                    policy_reference="pdp.wave1.facility_scope_denied",
                    obligations=("audit_denial",),
                )

        return AuthorizationDecision(
            allowed=True,
            reason="permission_granted",
            policy_reference="pdp.wave1.permission_granted",
            obligations=("audit_success",),
        )


def _organization_allowed(organization_id: UUID, actor_organization_ids: tuple[UUID, ...]) -> bool:
    return organization_id in actor_organization_ids


def _facility_allowed(facility_id: UUID, actor_facility_ids: tuple[UUID, ...]) -> bool:
    """Facility scope is org-bounded, never platform-unrestricted.

    Empty ``actor_facility_ids`` means the membership is organization-wide:
    every facility in the already-authorized organization is in scope.
    It does not grant access outside that organization. Organization scope
    is evaluated separately. A non-empty binding list is an allow-list.
    """
    if not actor_facility_ids:
        return True
    return facility_id in actor_facility_ids
