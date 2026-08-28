from uuid import UUID

from app.core.errors import AppError
from app.modules.audit.application.ports import AuditSink
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.governance.domain.enums import GovernanceAdminScopeType
from app.modules.governance.infrastructure.models import GovernanceAdminIdempotencyModel
from app.modules.governance.infrastructure.repositories import GovernanceRepository
from app.modules.iam.domain.models import Principal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


async def replay_or_conflict_idempotency(
    session: AsyncSession,
    repo: GovernanceRepository,
    *,
    principal: Principal,
    scope_type: GovernanceAdminScopeType,
    organization_id: UUID | None,
    operation: str,
    idempotency_key: str,
    request_fingerprint: str,
    permission: Permission,
    pdp: PolicyDecisionPoint,
    audit: AuditSink,
    purpose: str,
    correlation_id: str | None,
) -> UUID | None:
    await authorize(
        pdp,
        audit,
        session=session,
        principal=principal,
        action=permission,
        resource_type="Governance",
        organization_id=organization_id,
        purpose=purpose,
        correlation_id=correlation_id,
    )
    existing = await repo.get_idempotency(
        scope_type=scope_type.value,
        organization_id=organization_id,
        actor_id=principal.user.id,
        operation=operation,
        idempotency_key=idempotency_key,
    )
    if existing is None:
        return None
    if existing.request_fingerprint != request_fingerprint:
        raise AppError(
            "idempotency_key_conflict",
            "Idempotency-Key was reused with different request semantics",
            status_code=409,
        )
    return existing.resource_id


async def claim_idempotency(
    session: AsyncSession,
    repo: GovernanceRepository,
    *,
    scope_type: GovernanceAdminScopeType,
    organization_id: UUID | None,
    actor_id: UUID,
    operation: str,
    idempotency_key: str,
    request_fingerprint: str,
    resource_type: str,
    resource_id: UUID,
) -> bool:
    model = GovernanceAdminIdempotencyModel(
        scope_type=scope_type.value,
        organization_id=organization_id,
        actor_id=actor_id,
        operation=operation,
        idempotency_key=idempotency_key,
        request_fingerprint=request_fingerprint,
        resource_type=resource_type,
        resource_id=resource_id,
    )
    try:
        async with session.begin_nested():
            await repo.add_idempotency(model)
    except IntegrityError:
        return False
    return True
