from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.clinical.application.services import (
    ClinicalService,
    ObservationView,
    _apply_observation_value,
    _observation_view,
    _require_actor_id,
)
from app.modules.clinical.domain.enums import (
    ClinicalAuditAction,
    ClinicalObservationWriteOperation,
    ClinicalProvenanceSubjectType,
    EncounterStatus,
    ObservationCategory,
    ObservationStatus,
    ObservationValueType,
)
from app.modules.clinical.domain.idempotency import manual_vital_create_fingerprint
from app.modules.clinical.domain.manual_vitals_approval import (
    approval_scope_fingerprint,
)
from app.modules.clinical.domain.manual_vitals_decimal import (
    canonical_decimal_fingerprint_text,
    parse_manual_vital_decimal,
)
from app.modules.clinical.domain.observation_values import ObservationValue
from app.modules.clinical.domain.vital_signs_catalog import (
    MANUAL_VITALS_CATALOG_VERSION,
    MANUAL_VITALS_FEATURE_ID,
    MANUAL_VITALS_FEATURE_VERSION,
    get_catalog_entry,
    is_known_measurement_key,
    list_catalog_entries,
    measurement_key_for_loinc_code,
)
from app.modules.clinical.infrastructure.models import (
    ClinicalObservationWriteIdempotencyModel,
    ObservationModel,
)
from app.modules.clinical.infrastructure.repositories import utc_now
from app.modules.governance.application.services import GovernanceService
from app.modules.governance.domain.enums import (
    ApprovalEvidenceStatus,
    DeploymentGateState,
    FeatureActivationState,
    PolicyEffect,
    ProviderCapabilityState,
)
from app.modules.governance.domain.models import ApprovalEvidence, GovernanceProfileVersion
from app.modules.governance.domain.policy_schema import GovernancePolicyDocumentV2
from app.modules.governance.domain.resolver import resolve_governance_required_layers
from app.modules.governance.infrastructure.repositories import GovernanceRepository
from app.modules.iam.domain.models import Principal
from app.shared.types.ids import new_id

MANUAL_VITALS_APPROVAL_TYPE = "CLINICAL_GOVERNANCE"


@dataclass(frozen=True, slots=True)
class ManualVitalMeasurementOption:
    measurement_key: str
    display_unit: str
    canonical_concept: str


@dataclass(frozen=True, slots=True)
class ManualVitalsWriteContext:
    available: bool
    catalog_version: str | None
    feature_version: str | None
    measurements: tuple[ManualVitalMeasurementOption, ...]


class ManualVitalsService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._clinical = ClinicalService(session, pdp, audit)
        self._governance = GovernanceService(session, pdp, audit)
        self._gov_repo = GovernanceRepository(session)

    async def get_write_context(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *,
        purpose: str,
        correlation_id: str | None,
    ) -> ManualVitalsWriteContext:
        scoped = self._require_org_membership(principal, organization_id)
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=scoped,
            action=Permission.CLINICAL_OBSERVATION_CREATE,
            resource_type="ManualVitalSigns",
            organization_id=organization_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        readiness = await self._resolve_write_readiness(organization_id)
        if not readiness.available:
            return ManualVitalsWriteContext(
                available=False,
                catalog_version=None,
                feature_version=None,
                measurements=(),
            )
        policy, _profile_version = readiness.policy_version_pair  # type: ignore[misc]
        assert policy.manual_vital_signs is not None
        approved = set(policy.manual_vital_signs.approved_measurements)
        measurements = tuple(
            ManualVitalMeasurementOption(
                measurement_key=entry.measurement_key.value,
                display_unit=entry.display_unit,
                canonical_concept=entry.canonical_concept,
            )
            for entry in list_catalog_entries()
            if entry.measurement_key.value in approved
        )
        return ManualVitalsWriteContext(
            available=True,
            catalog_version=policy.manual_vital_signs.catalog_version,
            feature_version=MANUAL_VITALS_FEATURE_VERSION,
            measurements=measurements,
        )

    async def create_measurement(
        self,
        principal: Principal | None,
        organization_id: UUID,
        *,
        expected_patient_identity_id: UUID,
        encounter_id: UUID,
        measurement_key: str,
        value: object,
        effective_at: datetime,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
        idempotency_key: str,
    ) -> ObservationView:
        if effective_at.tzinfo is None:
            raise AppError(
                "invalid_effective_at",
                "Measurement time must include timezone offset",
                status_code=422,
            )
        catalog_entry = get_catalog_entry(measurement_key)
        if catalog_entry is None:
            raise AppError(
                "invalid_measurement_key",
                "Measurement type is not supported",
                status_code=422,
            )
        decimal_value = parse_manual_vital_decimal(value)
        canonical_value = canonical_decimal_fingerprint_text(decimal_value)
        effective_at_iso = effective_at.astimezone(UTC).isoformat()
        fingerprint = manual_vital_create_fingerprint(
            expected_patient_identity_id=expected_patient_identity_id,
            encounter_id=encounter_id,
            measurement_key=measurement_key,
            canonical_value=canonical_value,
            effective_at_iso=effective_at_iso,
            provider_catalog_version=MANUAL_VITALS_CATALOG_VERSION,
        )
        scoped = self._require_org_membership(principal, organization_id)
        actor_id = _require_actor_id(scoped)
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=scoped,
            action=Permission.CLINICAL_OBSERVATION_CREATE,
            resource_type="ManualVitalSigns",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        readiness = await self._resolve_write_readiness(organization_id)
        if not readiness.available:
            raise AppError(
                "manual_vital_signs_unavailable",
                "Manual vital signs are not available for this organization",
                status_code=403,
            )
        policy, profile_version = readiness.policy_version_pair  # type: ignore[misc]
        assert policy.manual_vital_signs is not None
        if measurement_key not in policy.manual_vital_signs.approved_measurements:
            raise AppError(
                "measurement_not_approved",
                "Measurement type is not approved for this organization",
                status_code=403,
            )
        await self._clinical._require_expected_write_identity(  # noqa: SLF001
            scoped, expected_patient_identity_id, organization_id
        )
        encounter = await self._clinical._visible_encounter(  # noqa: SLF001
            scoped, encounter_id, organization_id, for_update=True
        )
        await self._clinical._assert_same_person_context(  # noqa: SLF001
            scoped,
            expected_patient_identity_id,
            encounter.patient_identity_id,
            organization_id,
            mismatch="encounter",
        )
        mutation_readiness = await self._resolve_write_readiness_for_mutation(organization_id)
        if not mutation_readiness.available:
            raise AppError(
                "manual_vital_signs_unavailable",
                "Manual vital signs are not available for this organization",
                status_code=403,
            )
        policy, profile_version = mutation_readiness.policy_version_pair  # type: ignore[misc]
        assert policy.manual_vital_signs is not None
        if measurement_key not in policy.manual_vital_signs.approved_measurements:
            raise AppError(
                "measurement_not_approved",
                "Measurement type is not approved for this organization",
                status_code=403,
            )
        await self._assert_encounter_documentable(encounter.status, policy)
        note_facility_id = await self._clinical._create_note_facility(  # noqa: SLF001
            scoped,
            organization_id=organization_id,
            header_facility_id=facility_id,
            encounter_facility_id=encounter.facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        replay = await self._replay_or_conflict(
            organization_id=organization_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            principal=scoped,
            header_facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if replay is not None:
            return replay
        observation_id = new_id()
        claimed = await self._claim_idempotency(
            organization_id=organization_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            observation_id=observation_id,
            principal=scoped,
            header_facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if claimed is not None:
            return claimed
        provenance = await self._clinical._record_provenance(  # noqa: SLF001
            subject_type=ClinicalProvenanceSubjectType.OBSERVATION,
            subject_id=observation_id,
            organization_id=organization_id,
            facility_id=note_facility_id,
            actor_id=actor_id,
        )
        observation = ObservationModel(
            id=observation_id,
            patient_identity_id=encounter.patient_identity_id,
            encounter_id=encounter.id,
            organization_id=organization_id,
            facility_id=note_facility_id,
            category=ObservationCategory.VITAL_SIGNS.value,
            code_system=catalog_entry.code_system,
            code=catalog_entry.code,
            code_display=catalog_entry.canonical_concept,
            status=ObservationStatus.FINAL.value,
            value_type=ObservationValueType.NUMERIC.value,
            recorded_at=utc_now(),
            recorder_id=actor_id,
            version=1,
            provenance_id=provenance.id,
            effective_at=effective_at.astimezone(UTC),
        )
        _apply_observation_value(
            observation,
            ObservationValue(
                value_type=ObservationValueType.NUMERIC,
                numeric=decimal_value,
                unit=catalog_entry.unit_code,
            ),
        )
        await self._clinical._clinical.add_observation(observation)  # noqa: SLF001
        await self._clinical._audit_success(  # noqa: SLF001
            ClinicalAuditAction.OBSERVATION_CREATED,
            scoped,
            organization_id,
            observation.facility_id,
            observation.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=observation.id,
            metadata={
                "category": observation.category,
                "status": observation.status,
                "feature_id": MANUAL_VITALS_FEATURE_ID,
                "feature_version": MANUAL_VITALS_FEATURE_VERSION,
                "catalog_version": MANUAL_VITALS_CATALOG_VERSION,
                "measurement_key": measurement_key,
                "governance_profile_version_id": str(profile_version.id),
            },
        )
        return _observation_view(observation)

    @dataclass(frozen=True, slots=True)
    class _WriteReadiness:
        available: bool
        policy_version_pair: tuple[GovernancePolicyDocumentV2, GovernanceProfileVersion] | None = (
            None
        )

    async def _resolve_write_readiness(self, organization_id: UUID) -> _WriteReadiness:
        resolution = await self._governance.resolve_feature(
            organization_id,
            MANUAL_VITALS_FEATURE_ID,
        )
        if not resolution.available:
            return self._WriteReadiness(available=False)
        profile = await self._gov_repo.get_profile(organization_id)
        if profile is None or profile.active_published_version_id is None:
            return self._WriteReadiness(available=False)
        profile_version = await self._gov_repo.get_profile_version(
            profile.active_published_version_id
        )
        if profile_version is None:
            return self._WriteReadiness(available=False)
        policy = profile_version.policy_document
        if not isinstance(policy, GovernancePolicyDocumentV2):
            return self._WriteReadiness(available=False)
        if policy.manual_vital_signs.catalog_version != MANUAL_VITALS_CATALOG_VERSION:
            return self._WriteReadiness(available=False)
        if not policy.manual_vital_signs.approved_measurements:
            return self._WriteReadiness(available=False)
        for key in policy.manual_vital_signs.approved_measurements:
            if not is_known_measurement_key(key):
                return self._WriteReadiness(available=False)
        if not await self._has_valid_approval(
            organization_id=organization_id,
            profile_version=profile_version,
            policy=policy,
        ):
            return self._WriteReadiness(available=False)
        activation = await self._gov_repo.get_feature_activation(
            organization_id,
            MANUAL_VITALS_FEATURE_ID,
        )
        if activation is None or activation.activation_state is not FeatureActivationState.ACTIVE:
            return self._WriteReadiness(available=False)
        return self._WriteReadiness(
            available=True,
            policy_version_pair=(policy, profile_version),
        )

    async def _resolve_write_readiness_for_mutation(
        self,
        organization_id: UUID,
    ) -> _WriteReadiness:
        """Re-validate governance under row locks immediately before mutation."""
        capability = await self._gov_repo.get_provider_capability_by_feature_id(
            MANUAL_VITALS_FEATURE_ID,
            for_update=True,
        )
        if capability is None or capability.provider_state is not ProviderCapabilityState.AVAILABLE:
            return self._WriteReadiness(available=False)
        profile = await self._gov_repo.get_profile(organization_id, for_update=True)
        if profile is None or profile.active_published_version_id is None:
            return self._WriteReadiness(available=False)
        profile_version = await self._gov_repo.get_profile_version(
            profile.active_published_version_id
        )
        if profile_version is None:
            return self._WriteReadiness(available=False)
        policy = profile_version.policy_document
        if not isinstance(policy, GovernancePolicyDocumentV2):
            return self._WriteReadiness(available=False)
        if policy.manual_vital_signs.catalog_version != MANUAL_VITALS_CATALOG_VERSION:
            return self._WriteReadiness(available=False)
        if not policy.manual_vital_signs.approved_measurements:
            return self._WriteReadiness(available=False)
        for key in policy.manual_vital_signs.approved_measurements:
            if not is_known_measurement_key(key):
                return self._WriteReadiness(available=False)
        activation = await self._gov_repo.get_feature_activation(
            organization_id,
            MANUAL_VITALS_FEATURE_ID,
            for_update=True,
        )
        gates_list = await self._gov_repo.list_deployment_gates(organization_id)
        gates = {gate.gate_type: gate for gate in gates_list}
        required = await self._gov_repo.list_required_gates(capability.id)
        evidence = await self._gov_repo.list_approval_evidence(
            organization_id,
            MANUAL_VITALS_FEATURE_ID,
        )
        org_active = await self._governance._organization_active(organization_id)  # noqa: SLF001
        resolution = resolve_governance_required_layers(
            capability=capability,
            activation=activation,
            required_gate_types=required,
            gates=gates,
            approval_evidence=evidence,
            organization_active=org_active,
        )
        if not resolution.available:
            return self._WriteReadiness(available=False)
        if not await self._has_valid_approval(
            organization_id=organization_id,
            profile_version=profile_version,
            policy=policy,
        ):
            return self._WriteReadiness(available=False)
        if activation is None or activation.activation_state is not FeatureActivationState.ACTIVE:
            return self._WriteReadiness(available=False)
        for gate in gates.values():
            if gate.gate_state in {
                DeploymentGateState.NOT_ASSESSED,
                DeploymentGateState.PENDING,
                DeploymentGateState.EXPIRED,
            }:
                return self._WriteReadiness(available=False)
        return self._WriteReadiness(
            available=True,
            policy_version_pair=(policy, profile_version),
        )

    async def _has_valid_approval(
        self,
        *,
        organization_id: UUID,
        profile_version: GovernanceProfileVersion,
        policy: GovernancePolicyDocumentV2,
    ) -> bool:
        expected_scope = approval_scope_fingerprint(
            catalog_version=policy.manual_vital_signs.catalog_version,
            approved_measurements=policy.manual_vital_signs.approved_measurements,
        )
        now = datetime.now(UTC)
        for evidence in await self._matching_evidence(organization_id):
            if evidence.governance_profile_version_id != profile_version.id:
                continue
            if evidence.approval_type != MANUAL_VITALS_APPROVAL_TYPE:
                continue
            if evidence.status is not ApprovalEvidenceStatus.APPROVED:
                continue
            if evidence.expires_at is not None and evidence.expires_at <= now:
                continue
            if evidence.scope != expected_scope:
                continue
            if evidence.provider_feature_version != MANUAL_VITALS_FEATURE_VERSION:
                continue
            return True
        return False

    async def _matching_evidence(self, organization_id: UUID) -> list[ApprovalEvidence]:
        return await self._gov_repo.list_approval_evidence(
            organization_id,
            MANUAL_VITALS_FEATURE_ID,
        )

    async def _assert_encounter_documentable(
        self,
        status_value: str,
        policy: GovernancePolicyDocumentV2,
    ) -> None:
        status = EncounterStatus(status_value)
        if status in {EncounterStatus.CANCELLED, EncounterStatus.ENTERED_IN_ERROR}:
            raise AppError(
                "encounter_not_documentable",
                "A cancelled or erroneous encounter cannot receive vital signs",
                status_code=409,
            )
        if status is EncounterStatus.IN_PROGRESS:
            return
        if status is EncounterStatus.PLANNED:
            if policy.encounter_status_policy.planned is not PolicyEffect.ALLOW:
                raise AppError(
                    "encounter_not_documentable",
                    "This encounter status is not approved for manual vital signs",
                    status_code=409,
                )
            return
        if status is EncounterStatus.FINISHED:
            if (
                policy.encounter_status_policy.finished is PolicyEffect.ALLOW
                or policy.late_documentation_policy.finished_encounter_write_allowed
            ):
                return
            raise AppError(
                "encounter_not_documentable",
                "This encounter status is not approved for manual vital signs",
                status_code=409,
            )
        raise AppError(
            "encounter_not_documentable",
            "This encounter status is not approved for manual vital signs",
            status_code=409,
        )

    def _require_org_membership(
        self,
        principal: Principal | None,
        organization_id: UUID,
    ) -> Principal:
        if principal is None:
            raise NotFoundError("Resource not found")
        scoped = principal.for_organization(organization_id)
        if not scoped.memberships:
            raise NotFoundError("Resource not found")
        return scoped

    async def _replay_or_conflict(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        principal: Principal,
        header_facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ObservationView | None:
        await authorize(
            self._pdp,
            self._audit,
            session=self._session,
            principal=principal,
            action=Permission.CLINICAL_OBSERVATION_CREATE,
            resource_type="ManualVitalSigns",
            organization_id=organization_id,
            facility_id=header_facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        readiness = await self._resolve_write_readiness_for_mutation(organization_id)
        if not readiness.available:
            raise AppError(
                "manual_vital_signs_unavailable",
                "Manual vital signs are not available for this organization",
                status_code=403,
            )
        policy, _profile_version = readiness.policy_version_pair  # type: ignore[misc]
        assert policy.manual_vital_signs is not None
        existing = await self._clinical._clinical.get_observation_write_idempotency(  # noqa: SLF001
            organization_id=organization_id,
            actor_id=actor_id,
            operation=ClinicalObservationWriteOperation.OBSERVATION_CREATE.value,
            idempotency_key=idempotency_key,
        )
        if existing is None:
            return None
        if existing.request_fingerprint != fingerprint:
            raise AppError(
                "idempotency_key_conflict",
                "Idempotency-Key was already used for a different request",
                status_code=409,
            )
        observation = await self._clinical._visible_observation(  # noqa: SLF001
            principal,
            existing.observation_id,
            organization_id,
        )
        measurement_key = measurement_key_for_loinc_code(observation.code)
        if (
            measurement_key is None
            or measurement_key not in policy.manual_vital_signs.approved_measurements
        ):
            raise AppError(
                "manual_vital_signs_unavailable",
                "Manual vital signs are not available for this organization",
                status_code=403,
            )
        return _observation_view(observation)

    async def _claim_idempotency(
        self,
        *,
        organization_id: UUID,
        actor_id: UUID,
        idempotency_key: str,
        fingerprint: str,
        observation_id: UUID,
        principal: Principal,
        header_facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ObservationView | None:
        try:
            async with self._session.begin_nested():
                await self._clinical._clinical.add_observation_write_idempotency(  # noqa: SLF001
                    ClinicalObservationWriteIdempotencyModel(
                        id=new_id(),
                        organization_id=organization_id,
                        actor_id=actor_id,
                        operation=ClinicalObservationWriteOperation.OBSERVATION_CREATE.value,
                        idempotency_key=idempotency_key,
                        request_fingerprint=fingerprint,
                        observation_id=observation_id,
                        created_at=utc_now(),
                    )
                )
        except IntegrityError:
            return await self._replay_or_conflict(
                organization_id=organization_id,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                fingerprint=fingerprint,
                principal=principal,
                header_facility_id=header_facility_id,
                purpose=purpose,
                correlation_id=correlation_id,
            )
        return None
