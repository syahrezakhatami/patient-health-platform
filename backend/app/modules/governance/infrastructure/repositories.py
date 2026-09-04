from datetime import datetime
from uuid import UUID

from app.modules.governance.domain.enums import (
    ApprovalEvidenceStatus,
    DeploymentGateState,
    DeploymentGateType,
    FeatureActivationState,
    ProfileVersionStatus,
    ProviderCapabilityState,
)
from app.modules.governance.domain.models import (
    ApprovalEvidence,
    DeploymentGate,
    FeatureActivation,
    GovernanceProfile,
    GovernanceProfileVersion,
    ProviderCapability,
)
from app.modules.governance.domain.policy_schema import (
    parse_policy_document,
)
from app.modules.governance.infrastructure.models import (
    GovernanceAdminIdempotencyModel,
    GovernanceApprovalEvidenceModel,
    OrganizationDeploymentGateStateModel,
    OrganizationFeatureActivationModel,
    OrganizationGovernanceProfileModel,
    OrganizationGovernanceProfileVersionModel,
    ProviderCapabilityModel,
    ProviderCapabilityRequiredGateModel,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class GovernanceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_provider_capabilities(self) -> int:
        result = await self._session.execute(select(ProviderCapabilityModel))
        return len(result.scalars().all())

    async def list_provider_capabilities(self) -> list[ProviderCapability]:
        result = await self._session.execute(
            select(ProviderCapabilityModel).order_by(ProviderCapabilityModel.feature_id)
        )
        return [_map_capability(row) for row in result.scalars()]

    async def get_provider_capability_by_feature_id(
        self,
        feature_id: str,
        *,
        for_update: bool = False,
    ) -> ProviderCapability | None:
        stmt = select(ProviderCapabilityModel).where(
            ProviderCapabilityModel.feature_id == feature_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return None if row is None else _map_capability(row)

    async def get_provider_capability_by_id(
        self,
        capability_id: UUID,
        *,
        for_update: bool = False,
    ) -> ProviderCapability | None:
        stmt = select(ProviderCapabilityModel).where(ProviderCapabilityModel.id == capability_id)
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return None if row is None else _map_capability(row)

    async def add_provider_capability(self, model: ProviderCapabilityModel) -> ProviderCapability:
        self._session.add(model)
        await self._session.flush()
        return _map_capability(model)

    async def update_provider_capability_state(
        self,
        capability_id: UUID,
        *,
        provider_state: ProviderCapabilityState,
        row_version: int,
    ) -> None:
        result = await self._session.execute(
            select(ProviderCapabilityModel)
            .where(ProviderCapabilityModel.id == capability_id)
            .with_for_update()
        )
        row = result.scalar_one()
        row.provider_state = provider_state.value
        row.row_version = row_version
        await self._session.flush()

    async def list_required_gates(self, capability_id: UUID) -> frozenset[DeploymentGateType]:
        result = await self._session.execute(
            select(ProviderCapabilityRequiredGateModel.gate_type).where(
                ProviderCapabilityRequiredGateModel.provider_capability_id == capability_id
            )
        )
        return frozenset(DeploymentGateType(value) for value in result.scalars())

    async def add_required_gate(
        self,
        capability_id: UUID,
        gate_type: DeploymentGateType,
    ) -> None:
        self._session.add(
            ProviderCapabilityRequiredGateModel(
                provider_capability_id=capability_id,
                gate_type=gate_type.value,
            )
        )
        await self._session.flush()

    async def get_profile(
        self,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> GovernanceProfile | None:
        stmt = select(OrganizationGovernanceProfileModel).where(
            OrganizationGovernanceProfileModel.organization_id == organization_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return None if row is None else _map_profile(row)

    async def add_profile(self, model: OrganizationGovernanceProfileModel) -> GovernanceProfile:
        self._session.add(model)
        await self._session.flush()
        return _map_profile(model)

    async def set_active_published_version(
        self,
        profile_id: UUID,
        version_id: UUID,
    ) -> None:
        result = await self._session.execute(
            select(OrganizationGovernanceProfileModel)
            .where(OrganizationGovernanceProfileModel.id == profile_id)
            .with_for_update()
        )
        row = result.scalar_one()
        row.active_published_version_id = version_id
        await self._session.flush()

    async def get_profile_version(
        self,
        version_id: UUID,
        *,
        for_update: bool = False,
    ) -> GovernanceProfileVersion | None:
        stmt = select(OrganizationGovernanceProfileVersionModel).where(
            OrganizationGovernanceProfileVersionModel.id == version_id
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return None if row is None else _map_profile_version(row)

    async def get_next_version_number(self, profile_id: UUID) -> int:
        result = await self._session.execute(
            select(OrganizationGovernanceProfileVersionModel.version_number)
            .where(OrganizationGovernanceProfileVersionModel.profile_id == profile_id)
            .order_by(OrganizationGovernanceProfileVersionModel.version_number.desc())
            .limit(1)
        )
        current = result.scalar_one_or_none()
        return 1 if current is None else current + 1

    async def add_profile_version(
        self,
        model: OrganizationGovernanceProfileVersionModel,
    ) -> GovernanceProfileVersion:
        self._session.add(model)
        await self._session.flush()
        return _map_profile_version(model)

    async def mark_version_published(self, version_id: UUID) -> None:
        result = await self._session.execute(
            select(OrganizationGovernanceProfileVersionModel)
            .where(OrganizationGovernanceProfileVersionModel.id == version_id)
            .with_for_update()
        )
        row = result.scalar_one()
        row.status = "PUBLISHED"
        await self._session.flush()

    async def mark_version_superseded(self, version_id: UUID) -> None:
        result = await self._session.execute(
            select(OrganizationGovernanceProfileVersionModel)
            .where(OrganizationGovernanceProfileVersionModel.id == version_id)
            .with_for_update()
        )
        row = result.scalar_one()
        row.status = "SUPERSEDED"
        await self._session.flush()

    async def get_active_published_version(
        self,
        profile_id: UUID,
    ) -> GovernanceProfileVersion | None:
        profile = await self.get_profile_by_id(profile_id)
        if profile is None or profile.active_published_version_id is None:
            return None
        return await self.get_profile_version(profile.active_published_version_id)

    async def get_profile_by_id(self, profile_id: UUID) -> GovernanceProfile | None:
        result = await self._session.execute(
            select(OrganizationGovernanceProfileModel).where(
                OrganizationGovernanceProfileModel.id == profile_id
            )
        )
        row = result.scalar_one_or_none()
        return None if row is None else _map_profile(row)

    async def list_profile_versions(self, profile_id: UUID) -> list[GovernanceProfileVersion]:
        result = await self._session.execute(
            select(OrganizationGovernanceProfileVersionModel)
            .where(OrganizationGovernanceProfileVersionModel.profile_id == profile_id)
            .order_by(OrganizationGovernanceProfileVersionModel.version_number)
        )
        return [_map_profile_version(row) for row in result.scalars()]

    async def get_feature_activation(
        self,
        organization_id: UUID,
        feature_id: str,
        *,
        for_update: bool = False,
    ) -> FeatureActivation | None:
        stmt = select(OrganizationFeatureActivationModel).where(
            OrganizationFeatureActivationModel.organization_id == organization_id,
            OrganizationFeatureActivationModel.feature_id == feature_id,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return None if row is None else _map_activation(row)

    async def add_feature_activation(
        self,
        model: OrganizationFeatureActivationModel,
    ) -> FeatureActivation:
        self._session.add(model)
        await self._session.flush()
        return _map_activation(model)

    async def update_feature_activation_state(
        self,
        activation_id: UUID,
        *,
        activation_state: FeatureActivationState,
        row_version: int,
    ) -> None:
        result = await self._session.execute(
            select(OrganizationFeatureActivationModel)
            .where(OrganizationFeatureActivationModel.id == activation_id)
            .with_for_update()
        )
        row = result.scalar_one()
        row.activation_state = activation_state.value
        row.row_version = row_version
        await self._session.flush()

    async def get_deployment_gate(
        self,
        organization_id: UUID,
        gate_type: DeploymentGateType,
        *,
        for_update: bool = False,
    ) -> DeploymentGate | None:
        stmt = select(OrganizationDeploymentGateStateModel).where(
            OrganizationDeploymentGateStateModel.organization_id == organization_id,
            OrganizationDeploymentGateStateModel.gate_type == gate_type.value,
        )
        if for_update:
            stmt = stmt.with_for_update()
        result = await self._session.execute(stmt)
        row = result.scalar_one_or_none()
        return None if row is None else _map_gate(row)

    async def list_deployment_gates(self, organization_id: UUID) -> list[DeploymentGate]:
        result = await self._session.execute(
            select(OrganizationDeploymentGateStateModel).where(
                OrganizationDeploymentGateStateModel.organization_id == organization_id
            )
        )
        return [_map_gate(row) for row in result.scalars()]

    async def upsert_deployment_gate(
        self,
        organization_id: UUID,
        gate_type: DeploymentGateType,
        gate_state: DeploymentGateState,
        *,
        row_version: int | None = None,
    ) -> DeploymentGate:
        existing = await self.get_deployment_gate(organization_id, gate_type, for_update=True)
        if existing is None:
            model = OrganizationDeploymentGateStateModel(
                organization_id=organization_id,
                gate_type=gate_type.value,
                gate_state=gate_state.value,
                row_version=1,
            )
            self._session.add(model)
            await self._session.flush()
            return _map_gate(model)
        result = await self._session.execute(
            select(OrganizationDeploymentGateStateModel)
            .where(OrganizationDeploymentGateStateModel.id == existing.id)
            .with_for_update()
        )
        row = result.scalar_one()
        row.gate_state = gate_state.value
        row.row_version = row_version if row_version is not None else row.row_version + 1
        await self._session.flush()
        return _map_gate(row)

    async def update_deployment_gate_state(
        self,
        gate_id: UUID,
        *,
        gate_state: DeploymentGateState,
        row_version: int,
    ) -> None:
        result = await self._session.execute(
            select(OrganizationDeploymentGateStateModel)
            .where(OrganizationDeploymentGateStateModel.id == gate_id)
            .with_for_update()
        )
        row = result.scalar_one()
        row.gate_state = gate_state.value
        row.row_version = row_version
        await self._session.flush()

    async def add_approval_evidence(
        self,
        model: GovernanceApprovalEvidenceModel,
    ) -> ApprovalEvidence:
        self._session.add(model)
        await self._session.flush()
        return _map_evidence(model)

    async def list_approval_evidence(
        self,
        organization_id: UUID,
        feature_id: str | None = None,
    ) -> list[ApprovalEvidence]:
        stmt = select(GovernanceApprovalEvidenceModel).where(
            GovernanceApprovalEvidenceModel.organization_id == organization_id
        )
        if feature_id is not None:
            stmt = stmt.where(GovernanceApprovalEvidenceModel.feature_id == feature_id)
        result = await self._session.execute(
            stmt.order_by(GovernanceApprovalEvidenceModel.created_at)
        )
        return [_map_evidence(row) for row in result.scalars()]

    async def get_idempotency(
        self,
        *,
        scope_type: str,
        organization_id: UUID | None,
        actor_id: UUID,
        operation: str,
        idempotency_key: str,
    ) -> GovernanceAdminIdempotencyModel | None:
        stmt = select(GovernanceAdminIdempotencyModel).where(
            GovernanceAdminIdempotencyModel.scope_type == scope_type,
            GovernanceAdminIdempotencyModel.actor_id == actor_id,
            GovernanceAdminIdempotencyModel.operation == operation,
            GovernanceAdminIdempotencyModel.idempotency_key == idempotency_key,
        )
        if organization_id is None:
            stmt = stmt.where(GovernanceAdminIdempotencyModel.organization_id.is_(None))
        else:
            stmt = stmt.where(GovernanceAdminIdempotencyModel.organization_id == organization_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_idempotency(self, model: GovernanceAdminIdempotencyModel) -> None:
        self._session.add(model)
        await self._session.flush()


def _map_capability(row: ProviderCapabilityModel) -> ProviderCapability:
    return ProviderCapability(
        id=row.id,
        feature_id=row.feature_id,
        feature_version=row.feature_version,
        frozen_release_tag=row.frozen_release_tag,
        provider_state=ProviderCapabilityState(row.provider_state),
        governance_required=row.governance_required,
        row_version=row.row_version,
    )


def _map_profile(row: OrganizationGovernanceProfileModel) -> GovernanceProfile:
    return GovernanceProfile(
        id=row.id,
        organization_id=row.organization_id,
        active_published_version_id=row.active_published_version_id,
    )


def _map_profile_version(
    row: OrganizationGovernanceProfileVersionModel,
) -> GovernanceProfileVersion:
    return GovernanceProfileVersion(
        id=row.id,
        profile_id=row.profile_id,
        organization_id=row.organization_id,
        version_number=row.version_number,
        schema_version=row.schema_version,
        policy_document=parse_policy_document(row.policy_document),
        status=ProfileVersionStatus(row.status),
        effective_at=row.effective_at,
        changed_by=row.changed_by,
        changed_at=row.changed_at,
        reason=row.reason,
        previous_version_id=row.previous_version_id,
    )


def _map_activation(row: OrganizationFeatureActivationModel) -> FeatureActivation:
    return FeatureActivation(
        id=row.id,
        organization_id=row.organization_id,
        provider_capability_id=row.provider_capability_id,
        feature_id=row.feature_id,
        activation_state=FeatureActivationState(row.activation_state),
        row_version=row.row_version,
    )


def _map_gate(row: OrganizationDeploymentGateStateModel) -> DeploymentGate:
    return DeploymentGate(
        id=row.id,
        organization_id=row.organization_id,
        gate_type=DeploymentGateType(row.gate_type),
        gate_state=DeploymentGateState(row.gate_state),
        row_version=row.row_version,
    )


def _map_evidence(row: GovernanceApprovalEvidenceModel) -> ApprovalEvidence:
    approval_date = row.approval_date
    if isinstance(approval_date, datetime):
        approval_date = approval_date.date()
    return ApprovalEvidence(
        id=row.id,
        organization_id=row.organization_id,
        provider_capability_id=row.provider_capability_id,
        feature_id=row.feature_id,
        provider_feature_version=row.provider_feature_version,
        governance_profile_version_id=row.governance_profile_version_id,
        approval_type=row.approval_type,
        scope=row.scope,
        decision_by_name=row.decision_by_name,
        recorded_by_user_id=row.recorded_by_user_id,
        approval_date=approval_date,
        artifact_reference=row.artifact_reference,
        approver_role_category=row.approver_role_category,
        expires_at=row.expires_at,
        status=ApprovalEvidenceStatus(row.status),
        supersedes_evidence_id=row.supersedes_evidence_id,
        created_at=row.created_at,
    )
