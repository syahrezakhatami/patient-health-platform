from datetime import UTC, date, datetime
from uuid import UUID

from app.core.errors import AppError, ConflictError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.governance.application.idempotency import (
    claim_idempotency,
    replay_or_conflict_idempotency,
)
from app.modules.governance.domain.enums import (
    ApprovalEvidenceStatus,
    DeploymentGateState,
    DeploymentGateType,
    FeatureActivationState,
    GovernanceAdminOperation,
    GovernanceAdminScopeType,
    GovernanceAuditAction,
    GovernanceDenialReason,
    ProfileVersionStatus,
    ProviderCapabilityState,
)
from app.modules.governance.domain.idempotency import (
    approval_evidence_fingerprint,
    profile_version_create_fingerprint,
    profile_version_publish_fingerprint,
)
from app.modules.governance.domain.models import (
    ApprovalEvidence,
    DeploymentGate,
    FeatureActivation,
    GovernanceProfile,
    GovernanceProfileVersion,
    GovernanceResolution,
    ProviderCapability,
)
from app.modules.governance.domain.policy_schema import GovernancePolicyDocumentV1
from app.modules.governance.domain.resolver import (
    resolve_governance_required_layers,
    resolve_provider_layer,
)
from app.modules.governance.domain.transitions import (
    validate_activation_transition,
    validate_provider_transition,
)
from app.modules.governance.infrastructure.models import (
    GovernanceApprovalEvidenceModel,
    OrganizationFeatureActivationModel,
    OrganizationGovernanceProfileModel,
    OrganizationGovernanceProfileVersionModel,
)
from app.modules.governance.infrastructure.repositories import GovernanceRepository
from app.modules.iam.application.shell_context import tenant_memberships
from app.modules.iam.domain.models import Principal
from app.modules.organization.infrastructure.repositories import OrganizationRepository
from app.shared.enums import AuditResult
from app.shared.types.ids import new_id
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class GovernanceService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._repo = GovernanceRepository(session)
        self._orgs = OrganizationRepository(session)

    async def get_effective_context(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *,
        correlation_id: str | None,
    ) -> dict[str, object]:
        scoped = self._require_org_membership(principal, organization_id)
        if not await self._organization_active(organization_id):
            raise NotFoundError("Organization not found")
        profile = await self._repo.get_profile(organization_id)
        policy_payload: dict[str, object] | None = None
        if profile is not None and profile.active_published_version_id is not None:
            version = await self._repo.get_profile_version(profile.active_published_version_id)
            if version is not None:
                policy_payload = _safe_policy_subset(version.policy_document)
        capabilities = await self._repo.list_provider_capabilities()
        governed_features: list[dict[str, object]] = []
        for capability in capabilities:
            resolution = await self._resolve_capability(scoped, organization_id, capability)
            if not resolution.registered:
                continue
            governed_features.append(
                {
                    "feature_id": capability.feature_id,
                    "available": resolution.available,
                    "feature_version": capability.feature_version if resolution.available else None,
                }
            )
        result: dict[str, object] = {"governed_features": governed_features}
        if policy_payload is not None:
            result["policy"] = policy_payload
        return result

    async def get_management_profile(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *,
        correlation_id: str | None,
    ) -> dict[str, object]:
        scoped = self._require_org_membership(principal, organization_id)
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=scoped,
            action=Permission.GOVERNANCE_PROFILE_READ,
            resource_type="GovernanceProfile",
            organization_id=organization_id,
            purpose="governance_administration",
            correlation_id=correlation_id,
        )
        if not await self._organization_active(organization_id):
            raise NotFoundError("Organization not found")
        profile = await self._repo.get_profile(organization_id)
        if profile is None:
            return {
                "organization_id": str(organization_id),
                "profile": None,
                "versions": [],
                "activations": [],
                "deployment_gates": [],
                "approval_evidence": [],
            }
        versions = await self._repo.list_profile_versions(profile.id)
        activations = await self._list_activations(organization_id)
        gates = await self._repo.list_deployment_gates(organization_id)
        evidence = await self._repo.list_approval_evidence(organization_id)
        return {
            "organization_id": str(organization_id),
            "profile": {
                "id": str(profile.id),
                "active_published_version_id": (
                    None
                    if profile.active_published_version_id is None
                    else str(profile.active_published_version_id)
                ),
            },
            "versions": [_version_payload(version) for version in versions],
            "activations": [_activation_payload(item) for item in activations],
            "deployment_gates": [_gate_payload(item) for item in gates],
            "approval_evidence": [_evidence_payload(item) for item in evidence],
        }

    async def create_profile_version(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *,
        policy_document: GovernancePolicyDocumentV1,
        effective_at: datetime,
        reason: str,
        idempotency_key: str,
        correlation_id: str | None,
    ) -> GovernanceProfileVersion:
        scoped = self._require_org_membership(principal, organization_id)
        fingerprint = profile_version_create_fingerprint(
            organization_id=organization_id,
            schema_version=policy_document.schema_version,
            policy_document=policy_document,
            effective_at=effective_at,
            reason=reason,
        )
        replay_id = await replay_or_conflict_idempotency(
            self._session,
            self._repo,
            principal=scoped,
            scope_type=GovernanceAdminScopeType.ORGANIZATION,
            organization_id=organization_id,
            operation=GovernanceAdminOperation.PROFILE_VERSION_CREATE.value,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            permission=Permission.GOVERNANCE_PROFILE_MANAGE,
            pdp=self._pdp,
            audit=self._audit,
            purpose="governance_administration",
            correlation_id=correlation_id,
        )
        if replay_id is not None:
            replay_version = await self._repo.get_profile_version(replay_id)
            if replay_version is None:
                raise NotFoundError("Resource not found")
            return replay_version
        if not await self._organization_active(organization_id):
            raise NotFoundError("Organization not found")
        profile = await self._ensure_profile(organization_id)
        version_id = new_id()
        claimed = await claim_idempotency(
            self._session,
            self._repo,
            scope_type=GovernanceAdminScopeType.ORGANIZATION,
            organization_id=organization_id,
            actor_id=scoped.user.id,
            operation=GovernanceAdminOperation.PROFILE_VERSION_CREATE.value,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            resource_type="PROFILE_VERSION",
            resource_id=version_id,
        )
        if not claimed:
            replay_id = await replay_or_conflict_idempotency(
                self._session,
                self._repo,
                principal=scoped,
                scope_type=GovernanceAdminScopeType.ORGANIZATION,
                organization_id=organization_id,
                operation=GovernanceAdminOperation.PROFILE_VERSION_CREATE.value,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                permission=Permission.GOVERNANCE_PROFILE_MANAGE,
                pdp=self._pdp,
                audit=self._audit,
                purpose="governance_administration",
                correlation_id=correlation_id,
            )
            assert replay_id is not None
            replay_version = await self._repo.get_profile_version(replay_id)
            if replay_version is None:
                raise NotFoundError("Resource not found")
            return replay_version
        version_number = await self._repo.get_next_version_number(profile.id)
        now = datetime.now(UTC)
        previous = await self._repo.get_active_published_version(profile.id)
        version = await self._repo.add_profile_version(
            OrganizationGovernanceProfileVersionModel(
                id=version_id,
                profile_id=profile.id,
                organization_id=organization_id,
                version_number=version_number,
                schema_version=policy_document.schema_version,
                policy_document=policy_document.model_dump(mode="json"),
                status=ProfileVersionStatus.DRAFT.value,
                effective_at=effective_at,
                changed_by=scoped.user.id,
                changed_at=now,
                reason=reason.strip(),
                previous_version_id=None if previous is None else previous.id,
            )
        )
        await self._audit_success(
            GovernanceAuditAction.PROFILE_VERSION_CREATED,
            actor_id=scoped.user.id,
            organization_id=organization_id,
            resource_id=version.id,
            correlation_id=correlation_id,
        )
        return version

    async def publish_profile_version(
        self,
        principal: Principal | None,
        organization_id: UUID,
        version_id: UUID,
        *,
        idempotency_key: str,
        correlation_id: str | None,
    ) -> GovernanceProfileVersion:
        scoped = self._require_org_membership(principal, organization_id)
        fingerprint = profile_version_publish_fingerprint(
            organization_id=organization_id,
            profile_version_id=version_id,
        )
        replay_id = await replay_or_conflict_idempotency(
            self._session,
            self._repo,
            principal=scoped,
            scope_type=GovernanceAdminScopeType.ORGANIZATION,
            organization_id=organization_id,
            operation=GovernanceAdminOperation.PROFILE_VERSION_PUBLISH.value,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            permission=Permission.GOVERNANCE_PROFILE_MANAGE,
            pdp=self._pdp,
            audit=self._audit,
            purpose="governance_administration",
            correlation_id=correlation_id,
        )
        if replay_id is not None:
            replay_version = await self._repo.get_profile_version(replay_id)
            if replay_version is None:
                raise NotFoundError("Resource not found")
            return replay_version
        profile = await self._repo.get_profile(organization_id, for_update=True)
        if profile is None:
            raise NotFoundError("Governance profile not found")
        version = await self._repo.get_profile_version(version_id, for_update=True)
        if version is None or version.profile_id != profile.id:
            raise NotFoundError("Profile version not found")
        if version.status != ProfileVersionStatus.DRAFT:
            raise AppError(
                "invalid_transition",
                "Only draft versions can be published",
                status_code=409,
            )
        claimed = await claim_idempotency(
            self._session,
            self._repo,
            scope_type=GovernanceAdminScopeType.ORGANIZATION,
            organization_id=organization_id,
            actor_id=scoped.user.id,
            operation=GovernanceAdminOperation.PROFILE_VERSION_PUBLISH.value,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            resource_type="PROFILE_VERSION",
            resource_id=version_id,
        )
        if not claimed:
            replay_id = await replay_or_conflict_idempotency(
                self._session,
                self._repo,
                principal=scoped,
                scope_type=GovernanceAdminScopeType.ORGANIZATION,
                organization_id=organization_id,
                operation=GovernanceAdminOperation.PROFILE_VERSION_PUBLISH.value,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                permission=Permission.GOVERNANCE_PROFILE_MANAGE,
                pdp=self._pdp,
                audit=self._audit,
                purpose="governance_administration",
                correlation_id=correlation_id,
            )
            assert replay_id is not None
            replay_version = await self._repo.get_profile_version(replay_id)
            if replay_version is None:
                raise NotFoundError("Resource not found")
            return replay_version
        if profile.active_published_version_id is not None:
            await self._repo.mark_version_superseded(profile.active_published_version_id)
        await self._repo.mark_version_published(version_id)
        await self._repo.set_active_published_version(profile.id, version_id)
        published = await self._repo.get_profile_version(version_id)
        assert published is not None
        await self._audit_success(
            GovernanceAuditAction.PROFILE_VERSION_PUBLISHED,
            actor_id=scoped.user.id,
            organization_id=organization_id,
            resource_id=version_id,
            correlation_id=correlation_id,
        )
        return published

    async def record_approval_evidence(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *,
        feature_id: str,
        provider_feature_version: str,
        approval_type: str,
        scope: str,
        decision_by_name: str,
        approval_date: date,
        artifact_reference: str | None,
        approver_role_category: str | None,
        expires_at: datetime | None,
        idempotency_key: str,
        correlation_id: str | None,
    ) -> ApprovalEvidence:
        scoped = self._require_org_membership(principal, organization_id)
        fingerprint = approval_evidence_fingerprint(
            organization_id=organization_id,
            feature_id=feature_id,
            provider_feature_version=provider_feature_version,
            approval_type=approval_type,
            scope=scope,
            decision_by_name=decision_by_name,
            approval_date=approval_date,
            artifact_reference=artifact_reference,
            approver_role_category=approver_role_category,
        )
        replay_id = await replay_or_conflict_idempotency(
            self._session,
            self._repo,
            principal=scoped,
            scope_type=GovernanceAdminScopeType.ORGANIZATION,
            organization_id=organization_id,
            operation=GovernanceAdminOperation.APPROVAL_EVIDENCE_RECORD.value,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            permission=Permission.GOVERNANCE_APPROVAL_RECORD,
            pdp=self._pdp,
            audit=self._audit,
            purpose="governance_administration",
            correlation_id=correlation_id,
        )
        if replay_id is not None:
            evidence_rows = await self._repo.list_approval_evidence(organization_id, feature_id)
            for row in evidence_rows:
                if row.id == replay_id:
                    return row
            raise NotFoundError("Resource not found")
        capability = await self._repo.get_provider_capability_by_feature_id(feature_id)
        profile = await self._repo.get_profile(organization_id)
        active_version_id = None
        if profile is not None:
            active_version_id = profile.active_published_version_id
        evidence_id = new_id()
        claimed = await claim_idempotency(
            self._session,
            self._repo,
            scope_type=GovernanceAdminScopeType.ORGANIZATION,
            organization_id=organization_id,
            actor_id=scoped.user.id,
            operation=GovernanceAdminOperation.APPROVAL_EVIDENCE_RECORD.value,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            resource_type="APPROVAL_EVIDENCE",
            resource_id=evidence_id,
        )
        if not claimed:
            replay_id = await replay_or_conflict_idempotency(
                self._session,
                self._repo,
                principal=scoped,
                scope_type=GovernanceAdminScopeType.ORGANIZATION,
                organization_id=organization_id,
                operation=GovernanceAdminOperation.APPROVAL_EVIDENCE_RECORD.value,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                permission=Permission.GOVERNANCE_APPROVAL_RECORD,
                pdp=self._pdp,
                audit=self._audit,
                purpose="governance_administration",
                correlation_id=correlation_id,
            )
            assert replay_id is not None
            evidence_rows = await self._repo.list_approval_evidence(organization_id, feature_id)
            for row in evidence_rows:
                if row.id == replay_id:
                    return row
            raise NotFoundError("Resource not found")
        evidence = await self._repo.add_approval_evidence(
            GovernanceApprovalEvidenceModel(
                id=evidence_id,
                organization_id=organization_id,
                provider_capability_id=None if capability is None else capability.id,
                feature_id=feature_id.strip(),
                provider_feature_version=provider_feature_version.strip(),
                governance_profile_version_id=active_version_id,
                approval_type=approval_type.strip(),
                scope=scope.strip(),
                decision_by_name=decision_by_name.strip(),
                recorded_by_user_id=scoped.user.id,
                approval_date=approval_date,
                artifact_reference=artifact_reference,
                approver_role_category=approver_role_category,
                expires_at=expires_at,
                status=ApprovalEvidenceStatus.APPROVED.value,
                supersedes_evidence_id=None,
            )
        )
        await self._audit_success(
            GovernanceAuditAction.APPROVAL_EVIDENCE_RECORDED,
            actor_id=scoped.user.id,
            organization_id=organization_id,
            resource_id=evidence.id,
            correlation_id=correlation_id,
        )
        return evidence

    async def transition_feature_activation(
        self,
        principal: Principal | None,
        organization_id: UUID,
        feature_id: str,
        *,
        target_state: FeatureActivationState,
        expected_row_version: int | None,
        correlation_id: str | None,
    ) -> FeatureActivation:
        scoped = self._require_org_membership(principal, organization_id)
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=scoped,
            action=Permission.GOVERNANCE_FEATURE_ACTIVATE,
            resource_type="FeatureActivation",
            organization_id=organization_id,
            purpose="governance_administration",
            correlation_id=correlation_id,
        )
        capability = await self._repo.get_provider_capability_by_feature_id(feature_id)
        if capability is None:
            raise NotFoundError("Provider capability not found")
        activation = await self._repo.get_feature_activation(
            organization_id,
            feature_id,
            for_update=True,
        )
        current_state = None if activation is None else activation.activation_state
        mutates = validate_activation_transition(current_state, target_state)
        if not mutates:
            assert activation is not None
            return activation
        if activation is None:
            if expected_row_version is not None:
                raise ConflictError("Feature activation row version conflict")
            activation = await self._repo.add_feature_activation(
                OrganizationFeatureActivationModel(
                    id=new_id(),
                    organization_id=organization_id,
                    provider_capability_id=capability.id,
                    feature_id=feature_id,
                    activation_state=target_state.value,
                    row_version=1,
                )
            )
        else:
            if expected_row_version != activation.row_version:
                raise ConflictError("Feature activation row version conflict")
            await self._repo.update_feature_activation_state(
                activation.id,
                activation_state=target_state,
                row_version=activation.row_version + 1,
            )
            activation = await self._repo.get_feature_activation(organization_id, feature_id)
            assert activation is not None
        await self._audit_success(
            GovernanceAuditAction.FEATURE_ACTIVATION_CHANGED,
            actor_id=scoped.user.id,
            organization_id=organization_id,
            resource_id=activation.id,
            correlation_id=correlation_id,
            metadata={"feature_id": feature_id, "activation_state": target_state.value},
        )
        return activation

    async def update_deployment_gate(
        self,
        principal: Principal | None,
        organization_id: UUID,
        gate_type: DeploymentGateType,
        *,
        gate_state: DeploymentGateState,
        expected_row_version: int | None,
        correlation_id: str | None,
    ) -> DeploymentGate:
        scoped = self._require_org_membership(principal, organization_id)
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=scoped,
            action=Permission.GOVERNANCE_PROFILE_MANAGE,
            resource_type="DeploymentGate",
            organization_id=organization_id,
            purpose="governance_administration",
            correlation_id=correlation_id,
        )
        existing = await self._repo.get_deployment_gate(organization_id, gate_type, for_update=True)
        gate: DeploymentGate
        if existing is None:
            if expected_row_version is not None:
                raise ConflictError("Deployment gate row version conflict")
            gate = await self._repo.upsert_deployment_gate(
                organization_id,
                gate_type,
                gate_state,
            )
        else:
            if existing.gate_state == gate_state:
                return existing
            if expected_row_version != existing.row_version:
                raise ConflictError("Deployment gate row version conflict")
            await self._repo.update_deployment_gate_state(
                existing.id,
                gate_state=gate_state,
                row_version=existing.row_version + 1,
            )
            updated_gate = await self._repo.get_deployment_gate(organization_id, gate_type)
            if updated_gate is None:
                raise NotFoundError("Deployment gate not found")
            gate = updated_gate
        await self._audit_success(
            GovernanceAuditAction.DEPLOYMENT_GATE_CHANGED,
            actor_id=scoped.user.id,
            organization_id=organization_id,
            resource_id=gate.id,
            correlation_id=correlation_id,
            metadata={"gate_type": gate_type.value, "gate_state": gate_state.value},
        )
        return gate

    async def list_provider_capabilities(
        self,
        principal: Principal | None,
        *,
        correlation_id: str | None,
    ) -> list[ProviderCapability]:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.GOVERNANCE_PROVIDER_MANAGE,
            resource_type="ProviderCapability",
            organization_id=None,
            purpose="platform_governance",
            correlation_id=correlation_id,
        )
        return await self._repo.list_provider_capabilities()

    async def transition_provider_capability(
        self,
        principal: Principal | None,
        feature_id: str,
        *,
        target_state: ProviderCapabilityState,
        expected_row_version: int,
        correlation_id: str | None,
    ) -> ProviderCapability:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.GOVERNANCE_PROVIDER_MANAGE,
            resource_type="ProviderCapability",
            organization_id=None,
            purpose="platform_governance",
            correlation_id=correlation_id,
        )
        capability = await self._repo.get_provider_capability_by_feature_id(
            feature_id,
            for_update=True,
        )
        if capability is None:
            raise NotFoundError("Provider capability not found")
        mutates = validate_provider_transition(capability.provider_state, target_state)
        if not mutates:
            return capability
        if expected_row_version != capability.row_version:
            raise ConflictError("Provider capability row version conflict")
        await self._repo.update_provider_capability_state(
            capability.id,
            provider_state=target_state,
            row_version=capability.row_version + 1,
        )
        updated = await self._repo.get_provider_capability_by_feature_id(feature_id)
        assert updated is not None
        await self._audit_success(
            GovernanceAuditAction.PROVIDER_CAPABILITY_CHANGED,
            actor_id=None if principal is None else principal.user.id,
            organization_id=None,
            resource_id=updated.id,
            correlation_id=correlation_id,
            metadata={"feature_id": feature_id, "provider_state": target_state.value},
        )
        return updated

    async def resolve_feature(
        self,
        organization_id: UUID,
        feature_id: str,
    ) -> GovernanceResolution:
        capability = await self._repo.get_provider_capability_by_feature_id(feature_id)
        if capability is None:
            return GovernanceResolution(
                registered=False,
                available=False,
                denial_reason=GovernanceDenialReason.NOT_REGISTERED,
            )
        if not capability.governance_required:
            return resolve_provider_layer(capability)
        activation = await self._repo.get_feature_activation(organization_id, feature_id)
        gates_list = await self._repo.list_deployment_gates(organization_id)
        gates = {gate.gate_type: gate for gate in gates_list}
        required = await self._repo.list_required_gates(capability.id)
        evidence = await self._repo.list_approval_evidence(organization_id, feature_id)
        org_active = await self._organization_active(organization_id)
        return resolve_governance_required_layers(
            capability=capability,
            activation=activation,
            required_gate_types=required,
            gates=gates,
            approval_evidence=evidence,
            organization_active=org_active,
        )

    def _require_org_membership(
        self,
        principal: Principal | None,
        organization_id: UUID,
    ) -> Principal:
        if principal is None:
            raise NotFoundError("Resource not found")
        scoped = principal.for_organization(organization_id)
        if not tenant_memberships(scoped):
            raise NotFoundError("Resource not found")
        return scoped

    async def _ensure_profile(self, organization_id: UUID) -> GovernanceProfile:
        profile = await self._repo.get_profile(organization_id, for_update=True)
        if profile is not None:
            return profile
        try:
            return await self._repo.add_profile(
                OrganizationGovernanceProfileModel(
                    id=new_id(),
                    organization_id=organization_id,
                )
            )
        except IntegrityError:
            await self._session.rollback()
            profile = await self._repo.get_profile(organization_id, for_update=True)
            if profile is None:
                raise
            return profile

    async def _organization_active(self, organization_id: UUID) -> bool:
        org = await self._orgs.get_organization(organization_id)
        return org is not None

    async def _resolve_capability(
        self,
        principal: Principal,
        organization_id: UUID,
        capability: ProviderCapability,
    ) -> GovernanceResolution:
        del principal
        return await self.resolve_feature(organization_id, capability.feature_id)

    async def _list_activations(self, organization_id: UUID) -> list[FeatureActivation]:
        capabilities = await self._repo.list_provider_capabilities()
        activations: list[FeatureActivation] = []
        for capability in capabilities:
            activation = await self._repo.get_feature_activation(
                organization_id,
                capability.feature_id,
            )
            if activation is not None:
                activations.append(activation)
        return activations

    async def _audit_success(
        self,
        action: GovernanceAuditAction,
        *,
        actor_id: UUID | None,
        organization_id: UUID | None,
        resource_id: UUID,
        correlation_id: str | None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        await self._audit.record(
            AuditEvent(
                action=action.value,
                resource_type="Governance",
                result=AuditResult.SUCCESS,
                actor_id=actor_id,
                organization_id=organization_id,
                resource_id=resource_id,
                purpose="governance_administration",
                correlation_id=correlation_id,
                metadata=metadata or {},
            )
        )


def _safe_policy_subset(policy: GovernancePolicyDocumentV1) -> dict[str, object]:
    return {
        "encounter_status": {
            "planned": policy.encounter_status_policy.planned.value,
            "finished": policy.encounter_status_policy.finished.value,
        }
    }


def _version_payload(version: GovernanceProfileVersion) -> dict[str, object]:
    return {
        "id": str(version.id),
        "version_number": version.version_number,
        "status": version.status.value,
        "effective_at": version.effective_at.isoformat(),
        "reason": version.reason,
    }


def _activation_payload(activation: FeatureActivation) -> dict[str, object]:
    return {
        "id": str(activation.id),
        "feature_id": activation.feature_id,
        "activation_state": activation.activation_state.value,
        "row_version": activation.row_version,
    }


def _gate_payload(gate: DeploymentGate) -> dict[str, object]:
    return {
        "id": str(gate.id),
        "gate_type": gate.gate_type.value,
        "gate_state": gate.gate_state.value,
        "row_version": gate.row_version,
    }


def _evidence_payload(evidence: ApprovalEvidence) -> dict[str, object]:
    return {
        "id": str(evidence.id),
        "feature_id": evidence.feature_id,
        "approval_type": evidence.approval_type,
        "scope": evidence.scope,
        "status": evidence.status.value,
        "approval_date": evidence.approval_date.isoformat(),
        "expires_at": None if evidence.expires_at is None else evidence.expires_at.isoformat(),
    }
