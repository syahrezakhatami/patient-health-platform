from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFoundError
from app.modules.audit.application.ports import AuditSink
from app.modules.audit.domain.events import AuditEvent
from app.modules.authorization.application.authorize import authorize
from app.modules.authorization.application.ports import PolicyDecisionPoint
from app.modules.authorization.domain.catalog import Permission
from app.modules.clinical.domain.enums import (
    AllergyCategory,
    AllergyClinicalStatus,
    AllergyCriticality,
    AllergySeverity,
    AllergyStatus,
    AllergyVerificationStatus,
    ClinicalAuditAction,
    ClinicalNoteType,
    ClinicalProvenanceSubjectType,
    ClinicalRecordStatus,
    ConditionCategory,
    ConditionClinicalStatus,
    ConditionVerificationStatus,
    ConsentCategory,
    ConsentDecision,
    ConsentScope,
    ConsentSource,
    ConsentStatus,
    EncounterClass,
    EncounterStatus,
    ImmunizationCategory,
    ImmunizationRoute,
    ImmunizationSite,
    ImmunizationStatus,
    LaboratoryOrderStatus,
    LaboratoryResultInterpretation,
    LaboratoryResultStatus,
    LaboratoryResultValueType,
    LaboratorySpecimenStatus,
    LaboratorySpecimenType,
    MedicalDeviceAssociationStatus,
    MedicalDeviceCategory,
    MedicalDeviceStatus,
    MedicationCategory,
    MedicationRoute,
    MedicationStatus,
    ObservationCategory,
    ObservationStatus,
    ObservationValueType,
    ParticipationType,
    ProcedureCategory,
    ProcedureStatus,
)
from app.modules.clinical.domain.laboratory_values import (
    LaboratoryResultValue,
    laboratory_result_values_equal,
)
from app.modules.clinical.domain.lifecycle import (
    assert_allergy_can_amend,
    assert_allergy_mutable,
    assert_condition_clinical_transition,
    assert_condition_mutable,
    assert_condition_verification_transition,
    assert_consent_can_amend,
    assert_consent_can_revoke,
    assert_consent_mutable,
    assert_consent_period,
    assert_encounter_transition,
    assert_immunization_can_amend,
    assert_immunization_mutable,
    assert_lab_order_open,
    assert_lab_order_transition,
    assert_lab_result_can_amend,
    assert_lab_result_mutable,
    assert_lab_specimen_collectable,
    assert_lab_specimen_transition,
    assert_medical_device_can_amend,
    assert_medical_device_mutable,
    assert_medication_can_stop,
    assert_medication_mutable,
    assert_note_can_finalize,
    assert_note_can_mark_error,
    assert_note_is_draft,
    assert_observation_can_amend,
    assert_observation_mutable,
    assert_procedure_can_amend,
    assert_procedure_mutable,
    consent_is_effective,
)
from app.modules.clinical.domain.observation_values import (
    ObservationValue,
    observation_values_equal,
)
from app.modules.clinical.domain.terminology import CodeableConcept
from app.modules.clinical.infrastructure.models import (
    AllergyModel,
    ClinicalNoteModel,
    ClinicalProvenanceModel,
    ConditionModel,
    ConsentModel,
    EncounterModel,
    EncounterParticipantModel,
    ImmunizationModel,
    LaboratoryOrderModel,
    LaboratoryResultModel,
    LaboratorySpecimenModel,
    MedicalDeviceModel,
    MedicationModel,
    ObservationModel,
    ProcedureModel,
)
from app.modules.clinical.infrastructure.repositories import ClinicalRepository, utc_now
from app.modules.iam.domain.models import Principal
from app.modules.mpi.domain.enums import IdentityLifecycle
from app.modules.mpi.infrastructure.models import PatientIdentityModel
from app.modules.mpi.infrastructure.repositories import MpiRepository
from app.shared.enums import AuditResult, AuthorshipKind, InformationSource
from app.shared.types.ids import new_id


@dataclass(frozen=True, slots=True)
class EncounterView:
    id: UUID
    patient_identity_id: UUID
    organization_id: UUID
    facility_id: UUID | None
    encounter_class: EncounterClass
    status: EncounterStatus
    display_label: str
    started_at: datetime
    ended_at: datetime | None
    reason: CodeableConcept | None


@dataclass(frozen=True, slots=True)
class ClinicalNoteView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID
    organization_id: UUID
    facility_id: UUID | None
    note_type: ClinicalNoteType
    body_text: str
    record_status: ClinicalRecordStatus
    version: int
    authored_at: datetime
    finalized_at: datetime | None


@dataclass(frozen=True, slots=True)
class ConditionView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ConditionCategory
    code: CodeableConcept
    clinical_status: ConditionClinicalStatus
    verification_status: ConditionVerificationStatus
    onset_at: datetime | None
    abatement_at: datetime | None
    recorded_at: datetime


@dataclass(frozen=True, slots=True)
class ObservationView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ObservationCategory
    code: CodeableConcept
    status: ObservationStatus
    value_type: ObservationValueType
    value_numeric: Decimal | None
    value_text: str | None
    value_boolean: bool | None
    value_coded: CodeableConcept | None
    unit: str | None
    reference_range_low: Decimal | None
    reference_range_high: Decimal | None
    effective_at: datetime | None
    recorded_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class LaboratoryOrderView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    code: CodeableConcept
    status: LaboratoryOrderStatus
    ordered_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class LaboratorySpecimenView:
    id: UUID
    laboratory_order_id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    specimen_type: LaboratorySpecimenType
    status: LaboratorySpecimenStatus
    collected_at: datetime


@dataclass(frozen=True, slots=True)
class LaboratoryResultView:
    id: UUID
    laboratory_order_id: UUID
    laboratory_specimen_id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    code: CodeableConcept
    status: LaboratoryResultStatus
    value_type: LaboratoryResultValueType
    value_numeric: Decimal | None
    value_text: str | None
    value_boolean: bool | None
    value_coded: CodeableConcept | None
    unit: str | None
    reference_range_low: Decimal | None
    reference_range_high: Decimal | None
    interpretation: LaboratoryResultInterpretation | None
    effective_at: datetime | None
    recorded_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class MedicationView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: MedicationCategory
    code: CodeableConcept
    status: MedicationStatus
    dose_numeric: Decimal | None
    dose_unit: str | None
    route: MedicationRoute | None
    started_at: datetime | None
    stopped_at: datetime | None
    recorded_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class AllergyView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: AllergyCategory
    code: CodeableConcept
    status: AllergyStatus
    clinical_status: AllergyClinicalStatus
    verification_status: AllergyVerificationStatus
    criticality: AllergyCriticality | None
    severity: AllergySeverity | None
    reaction: CodeableConcept | None
    onset_at: datetime | None
    recorded_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class ConsentView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ConsentCategory
    scope: ConsentScope
    decision: ConsentDecision
    code: CodeableConcept | None
    source: ConsentSource
    period_start: datetime | None
    period_end: datetime | None
    note_text: str | None
    status: ConsentStatus
    recorded_at: datetime
    revoked_at: datetime | None
    version: int
    is_effective: bool


@dataclass(frozen=True, slots=True)
class ImmunizationView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ImmunizationCategory
    code: CodeableConcept
    occurrence_at: datetime | None
    route: ImmunizationRoute | None
    site: ImmunizationSite | None
    note_text: str | None
    status: ImmunizationStatus
    recorded_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class ProcedureView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ProcedureCategory
    code: CodeableConcept
    occurrence_at: datetime | None
    note_text: str | None
    status: ProcedureStatus
    recorded_at: datetime
    version: int


@dataclass(frozen=True, slots=True)
class MedicalDeviceView:
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: MedicalDeviceCategory
    code: CodeableConcept
    association_status: MedicalDeviceAssociationStatus
    occurrence_at: datetime | None
    note_text: str | None
    status: MedicalDeviceStatus
    recorded_at: datetime
    version: int


class ClinicalService:
    def __init__(
        self,
        session: AsyncSession,
        pdp: PolicyDecisionPoint,
        audit: AuditSink,
    ) -> None:
        self._session = session
        self._pdp = pdp
        self._audit = audit
        self._clinical = ClinicalRepository(session)
        self._mpi = MpiRepository(session)

    async def create_encounter(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_class: EncounterClass,
        started_at: datetime | None,
        reason: CodeableConcept | None,
        purpose: str,
        correlation_id: str | None,
    ) -> EncounterView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_CREATE,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_class is not EncounterClass.EMER
        ):
            raise AppError(
                "anonymous_encounter_not_emergency",
                "An anonymous identity may receive only an emergency encounter",
                status_code=409,
            )
        occurred = started_at or utc_now()
        encounter_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.ENCOUNTER,
            subject_id=encounter_id,
            organization_id=organization_id,
            facility_id=facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        encounter = EncounterModel(
            id=encounter_id,
            patient_identity_id=identity.id,
            organization_id=organization_id,
            facility_id=facility_id,
            encounter_class=encounter_class.value,
            status=EncounterStatus.IN_PROGRESS
            if encounter_class is EncounterClass.EMER
            else EncounterStatus.PLANNED,
            display_label=f"ENC-{encounter_id.hex[:8].upper()}",
            started_at=occurred,
            ended_at=None,
            reason_system=None if reason is None else reason.system,
            reason_code=None if reason is None else reason.code,
            reason_display=None if reason is None else reason.display,
            actor_id=None if principal is None else principal.user.id,
            provenance_id=provenance.id,
        )
        await self._clinical.add_encounter(encounter)
        if principal is not None:
            await self._clinical.add_participant(
                EncounterParticipantModel(
                    id=new_id(),
                    encounter_id=encounter.id,
                    actor_id=principal.user.id,
                    participation_type=ParticipationType.ATTENDING.value,
                )
            )
        await self._audit_success(
            ClinicalAuditAction.ENCOUNTER_CREATED,
            principal,
            organization_id,
            facility_id,
            identity.id,
            purpose,
            correlation_id,
            resource_id=encounter.id,
            metadata={"encounter_class": encounter.encounter_class, "purpose": purpose},
        )
        return _encounter_view(encounter)

    async def get_encounter(
        self,
        principal: Principal | None,
        encounter_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> EncounterView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_READ,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        encounter = await self._visible_encounter(principal, encounter_id, organization_id)
        return _encounter_view(encounter)

    async def list_encounters(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[EncounterView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_READ,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_encounters_for_patient(identity.id, organization_id)
        return [_encounter_view(item) for item in rows]

    async def change_encounter_status(
        self,
        principal: Principal | None,
        encounter_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        status: EncounterStatus,
        purpose: str,
        correlation_id: str | None,
    ) -> EncounterView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ENCOUNTER_UPDATE_STATUS,
            resource_type="Encounter",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        encounter = await self._visible_encounter(
            principal, encounter_id, organization_id, for_update=True
        )
        previous = EncounterStatus(encounter.status)
        assert_encounter_transition(previous, status)
        encounter.status = status.value
        if status in {
            EncounterStatus.FINISHED,
            EncounterStatus.CANCELLED,
            EncounterStatus.ENTERED_IN_ERROR,
        }:
            encounter.ended_at = encounter.ended_at or utc_now()
        await self._audit_success(
            ClinicalAuditAction.ENCOUNTER_STATUS_CHANGED,
            principal,
            organization_id,
            facility_id,
            encounter.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=encounter.id,
            metadata={"from": previous.value, "to": status.value, "purpose": purpose},
        )
        return _encounter_view(encounter)

    async def create_note(
        self,
        principal: Principal | None,
        *,
        encounter_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        note_type: ClinicalNoteType,
        body_text: str,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        body = _require_note_body(body_text)
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_CREATE,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        encounter = await self._visible_encounter(
            principal, encounter_id, organization_id, for_update=True
        )
        if EncounterStatus(encounter.status) in {
            EncounterStatus.CANCELLED,
            EncounterStatus.ENTERED_IN_ERROR,
        }:
            raise AppError(
                "encounter_not_documentable",
                "A cancelled or erroneous encounter cannot receive notes",
                status_code=409,
            )
        note_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.CLINICAL_NOTE,
            subject_id=note_id,
            organization_id=organization_id,
            facility_id=facility_id or encounter.facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        note = ClinicalNoteModel(
            id=note_id,
            patient_identity_id=encounter.patient_identity_id,
            encounter_id=encounter.id,
            organization_id=organization_id,
            facility_id=facility_id or encounter.facility_id,
            note_type=note_type.value,
            body_text=body,
            record_status=ClinicalRecordStatus.DRAFT.value,
            version=1,
            supersedes_id=None,
            content_hash=_content_hash(note_type.value, body),
            author_id=None if principal is None else principal.user.id,
            authored_at=utc_now(),
            finalized_at=None,
            provenance_id=provenance.id,
        )
        await self._clinical.add_note(note)
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_CREATED,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"note_type": note.note_type, "purpose": purpose},
        )
        return _note_view(note)

    async def get_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_READ,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id)
        return _note_view(note)

    async def update_draft_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        body_text: str,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        body = _require_note_body(body_text)
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_UPDATE_DRAFT,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id, for_update=True)
        assert_note_is_draft(ClinicalRecordStatus(note.record_status))
        note.body_text = body
        note.content_hash = _content_hash(note.note_type, body)
        note.version = note.version + 1
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_UPDATED,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"purpose": purpose},
        )
        return _note_view(note)

    async def finalize_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_FINALIZE,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id, for_update=True)
        assert_note_can_finalize(ClinicalRecordStatus(note.record_status))
        note.record_status = ClinicalRecordStatus.FINAL.value
        note.finalized_at = utc_now()
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_FINALIZED,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"purpose": purpose},
        )
        return _note_view(note)

    async def mark_note_entered_in_error(
        self,
        principal: Principal | None,
        note_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ClinicalNoteView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_NOTE_FINALIZE,
            resource_type="ClinicalNote",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        note = await self._visible_note(principal, note_id, organization_id, for_update=True)
        assert_note_can_mark_error(ClinicalRecordStatus(note.record_status))
        note.record_status = ClinicalRecordStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.CLINICAL_NOTE_ENTERED_IN_ERROR,
            principal,
            organization_id,
            note.facility_id,
            note.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=note.id,
            metadata={"purpose": purpose},
        )
        return _note_view(note)

    async def create_condition(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: ConditionCategory,
        code: CodeableConcept,
        clinical_status: ConditionClinicalStatus,
        verification_status: ConditionVerificationStatus,
        onset_at: datetime | None,
        abatement_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConditionView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONDITION_CREATE,
            resource_type="Condition",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if verification_status is ConditionVerificationStatus.ENTERED_IN_ERROR:
            raise AppError(
                "invalid_condition_create",
                "A condition cannot be created as entered in error",
                status_code=422,
            )
        _assert_condition_period(onset_at, abatement_at)
        if category is ConditionCategory.ENCOUNTER_DIAGNOSIS and encounter_id is None:
            raise AppError(
                "encounter_diagnosis_requires_encounter",
                "Encounter diagnosis requires an encounter",
                status_code=422,
            )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and category is ConditionCategory.PROBLEM_LIST_ITEM
        ):
            raise AppError(
                "anonymous_problem_list_not_allowed",
                "An anonymous identity cannot receive a problem-list condition",
                status_code=409,
            )
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive conditions",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "condition_patient_mismatch",
                    "Condition patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    "An anonymous identity may receive only an emergency encounter diagnosis",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        condition_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.CONDITION,
            subject_id=condition_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        condition = ConditionModel(
            id=condition_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            clinical_status=clinical_status.value,
            verification_status=verification_status.value,
            onset_at=onset_at,
            abatement_at=abatement_at,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            provenance_id=provenance.id,
        )
        await self._clinical.add_condition(condition)
        await self._audit_success(
            ClinicalAuditAction.CONDITION_CREATED,
            principal,
            organization_id,
            condition.facility_id,
            condition.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=condition.id,
            metadata={"category": condition.category, "purpose": purpose},
        )
        return _condition_view(condition)

    async def get_condition(
        self,
        principal: Principal | None,
        condition_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConditionView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONDITION_READ,
            resource_type="Condition",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        condition = await self._visible_condition(principal, condition_id, organization_id)
        return _condition_view(condition)

    async def list_conditions(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[ConditionView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONDITION_READ,
            resource_type="Condition",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_conditions_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_condition_view(item) for item in rows]

    async def change_condition_status(
        self,
        principal: Principal | None,
        condition_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        clinical_status: ConditionClinicalStatus | None,
        verification_status: ConditionVerificationStatus | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConditionView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONDITION_UPDATE,
            resource_type="Condition",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        if clinical_status is None and verification_status is None:
            raise AppError(
                "condition_status_required",
                "A condition status update requires clinical_status or verification_status",
                status_code=422,
            )
        if verification_status is ConditionVerificationStatus.ENTERED_IN_ERROR:
            raise AppError(
                "use_entered_in_error",
                "Use the entered-in-error operation to void a condition",
                status_code=422,
            )
        condition = await self._visible_condition(
            principal, condition_id, organization_id, for_update=True
        )
        current_clinical = ConditionClinicalStatus(condition.clinical_status)
        current_verification = ConditionVerificationStatus(condition.verification_status)
        assert_condition_mutable(current_verification)
        changed = False
        if clinical_status is not None and clinical_status is not current_clinical:
            assert_condition_clinical_transition(current_clinical, clinical_status)
            condition.clinical_status = clinical_status.value
            changed = True
        if verification_status is not None and verification_status is not current_verification:
            assert_condition_verification_transition(current_verification, verification_status)
            condition.verification_status = verification_status.value
            changed = True
        if not changed:
            raise AppError(
                "condition_status_unchanged",
                "Condition status is already at the requested values",
                status_code=409,
            )
        await self._audit_success(
            ClinicalAuditAction.CONDITION_STATUS_CHANGED,
            principal,
            organization_id,
            condition.facility_id,
            condition.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=condition.id,
            metadata={
                "clinical_status": condition.clinical_status,
                "verification_status": condition.verification_status,
                "purpose": purpose,
            },
        )
        return _condition_view(condition)

    async def mark_condition_entered_in_error(
        self,
        principal: Principal | None,
        condition_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConditionView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONDITION_ENTERED_IN_ERROR,
            resource_type="Condition",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        condition = await self._visible_condition(
            principal, condition_id, organization_id, for_update=True
        )
        assert_condition_mutable(ConditionVerificationStatus(condition.verification_status))
        condition.verification_status = ConditionVerificationStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.CONDITION_ENTERED_IN_ERROR,
            principal,
            organization_id,
            condition.facility_id,
            condition.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=condition.id,
            metadata={"purpose": purpose},
        )
        return _condition_view(condition)

    async def create_observation(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: ObservationCategory,
        code: CodeableConcept,
        value: ObservationValue,
        effective_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ObservationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_OBSERVATION_CREATE,
            resource_type="Observation",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_id is None
        ):
            raise AppError(
                "anonymous_observation_requires_encounter",
                "An anonymous identity may receive only an emergency encounter observation",
                status_code=409,
            )
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive observations",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "observation_patient_mismatch",
                    "Observation patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    "An anonymous identity may receive only an emergency encounter observation",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        observation_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.OBSERVATION,
            subject_id=observation_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        observation = ObservationModel(
            id=observation_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            status=ObservationStatus.FINAL.value,
            value_type=value.value_type.value,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
            effective_at=effective_at,
        )
        _apply_observation_value(observation, value)
        await self._clinical.add_observation(observation)
        await self._audit_success(
            ClinicalAuditAction.OBSERVATION_CREATED,
            principal,
            organization_id,
            observation.facility_id,
            observation.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=observation.id,
            metadata={"category": observation.category, "status": observation.status},
        )
        return _observation_view(observation)

    async def get_observation(
        self,
        principal: Principal | None,
        observation_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ObservationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_OBSERVATION_READ,
            resource_type="Observation",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        observation = await self._visible_observation(principal, observation_id, organization_id)
        return _observation_view(observation)

    async def list_observations(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[ObservationView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_OBSERVATION_READ,
            resource_type="Observation",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_observations_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_observation_view(item) for item in rows]

    async def amend_observation(
        self,
        principal: Principal | None,
        observation_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        value: ObservationValue,
        effective_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ObservationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_OBSERVATION_UPDATE,
            resource_type="Observation",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        observation = await self._visible_observation(
            principal, observation_id, organization_id, for_update=True
        )
        current_status = ObservationStatus(observation.status)
        assert_observation_can_amend(current_status)
        current_value = _observation_value_from_model(observation)
        if value.value_type is not current_value.value_type:
            raise AppError(
                "observation_value_type_immutable",
                "Observation value type cannot change",
                status_code=422,
            )
        next_effective = observation.effective_at if effective_at is None else effective_at
        value_unchanged = observation_values_equal(current_value, value)
        if value_unchanged and next_effective == observation.effective_at:
            raise AppError(
                "observation_unchanged",
                "Observation value is already at the requested values",
                status_code=409,
            )
        old_status = observation.status
        _apply_observation_value(observation, value)
        observation.effective_at = next_effective
        observation.status = ObservationStatus.AMENDED.value
        observation.version = observation.version + 1
        await self._audit_success(
            ClinicalAuditAction.OBSERVATION_AMENDED,
            principal,
            organization_id,
            observation.facility_id,
            observation.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=observation.id,
            metadata={
                "old_status": old_status,
                "new_status": observation.status,
                "version": str(observation.version),
            },
        )
        return _observation_view(observation)

    async def mark_observation_entered_in_error(
        self,
        principal: Principal | None,
        observation_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ObservationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_OBSERVATION_ENTERED_IN_ERROR,
            resource_type="Observation",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        observation = await self._visible_observation(
            principal, observation_id, organization_id, for_update=True
        )
        assert_observation_mutable(ObservationStatus(observation.status))
        observation.status = ObservationStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.OBSERVATION_ENTERED_IN_ERROR,
            principal,
            organization_id,
            observation.facility_id,
            observation.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=observation.id,
            metadata={"purpose": purpose},
        )
        return _observation_view(observation)

    async def create_lab_order(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        code: CodeableConcept,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryOrderView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_ORDER_CREATE,
            resource_type="LaboratoryOrder",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        _identity, encounter, bound_patient_id, bound_facility_id = await self._bind_lab_identity(
            principal,
            patient_identity_id,
            encounter_id,
            organization_id,
            facility_id,
            resource="laboratory order",
        )
        order_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.LABORATORY_ORDER,
            subject_id=order_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        order = LaboratoryOrderModel(
            id=order_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            status=LaboratoryOrderStatus.REGISTERED.value,
            ordered_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
        )
        await self._clinical.add_lab_order(order)
        await self._audit_success(
            ClinicalAuditAction.LAB_ORDER_CREATED,
            principal,
            organization_id,
            order.facility_id,
            order.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=order.id,
            metadata={"status": order.status},
        )
        return _lab_order_view(order)

    async def get_lab_order(
        self,
        principal: Principal | None,
        order_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryOrderView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_ORDER_READ,
            resource_type="LaboratoryOrder",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        order = await self._visible_lab_order(principal, order_id, organization_id)
        return _lab_order_view(order)

    async def list_lab_orders(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[LaboratoryOrderView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_ORDER_READ,
            resource_type="LaboratoryOrder",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_lab_orders_for_patient(identity.id, organization_id)
        return [_lab_order_view(item) for item in rows]

    async def cancel_lab_order(
        self,
        principal: Principal | None,
        order_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryOrderView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_ORDER_UPDATE,
            resource_type="LaboratoryOrder",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        order = await self._visible_lab_order(principal, order_id, organization_id, for_update=True)
        current = LaboratoryOrderStatus(order.status)
        assert_lab_order_transition(current, LaboratoryOrderStatus.CANCELLED)
        order.status = LaboratoryOrderStatus.CANCELLED.value
        order.version = order.version + 1
        await self._audit_success(
            ClinicalAuditAction.LAB_ORDER_CANCELLED,
            principal,
            organization_id,
            order.facility_id,
            order.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=order.id,
            metadata={"old_status": current.value, "new_status": order.status},
        )
        return _lab_order_view(order)

    async def mark_lab_order_entered_in_error(
        self,
        principal: Principal | None,
        order_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryOrderView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_ORDER_ENTERED_IN_ERROR,
            resource_type="LaboratoryOrder",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        order = await self._visible_lab_order(principal, order_id, organization_id, for_update=True)
        current = LaboratoryOrderStatus(order.status)
        assert_lab_order_transition(current, LaboratoryOrderStatus.ENTERED_IN_ERROR)
        order.status = LaboratoryOrderStatus.ENTERED_IN_ERROR.value
        order.version = order.version + 1
        await self._audit_success(
            ClinicalAuditAction.LAB_ORDER_ENTERED_IN_ERROR,
            principal,
            organization_id,
            order.facility_id,
            order.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=order.id,
            metadata={"old_status": current.value},
        )
        return _lab_order_view(order)

    async def collect_lab_specimen(
        self,
        principal: Principal | None,
        *,
        laboratory_order_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        specimen_type: LaboratorySpecimenType,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratorySpecimenView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_SPECIMEN_CREATE,
            resource_type="LaboratorySpecimen",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        order = await self._visible_lab_order(
            principal, laboratory_order_id, organization_id, for_update=True
        )
        assert_lab_order_open(LaboratoryOrderStatus(order.status))
        specimen_id = new_id()
        bound_facility_id = facility_id or order.facility_id
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.LABORATORY_SPECIMEN,
            subject_id=specimen_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        specimen = LaboratorySpecimenModel(
            id=specimen_id,
            laboratory_order_id=order.id,
            patient_identity_id=order.patient_identity_id,
            encounter_id=order.encounter_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            specimen_type=specimen_type.value,
            status=LaboratorySpecimenStatus.COLLECTED.value,
            collected_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            provenance_id=provenance.id,
        )
        await self._clinical.add_lab_specimen(specimen)
        if LaboratoryOrderStatus(order.status) is LaboratoryOrderStatus.REGISTERED:
            assert_lab_order_transition(
                LaboratoryOrderStatus.REGISTERED, LaboratoryOrderStatus.IN_PROGRESS
            )
            order.status = LaboratoryOrderStatus.IN_PROGRESS.value
            order.version = order.version + 1
            await self._audit_success(
                ClinicalAuditAction.LAB_ORDER_IN_PROGRESS,
                principal,
                organization_id,
                order.facility_id,
                order.patient_identity_id,
                purpose,
                correlation_id,
                resource_id=order.id,
                metadata={"status": order.status},
            )
        await self._audit_success(
            ClinicalAuditAction.LAB_SPECIMEN_COLLECTED,
            principal,
            organization_id,
            specimen.facility_id,
            specimen.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=specimen.id,
            metadata={"specimen_type": specimen.specimen_type, "order_id": str(order.id)},
        )
        return _lab_specimen_view(specimen)

    async def get_lab_specimen(
        self,
        principal: Principal | None,
        specimen_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratorySpecimenView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_SPECIMEN_READ,
            resource_type="LaboratorySpecimen",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        specimen = await self._visible_lab_specimen(principal, specimen_id, organization_id)
        return _lab_specimen_view(specimen)

    async def list_lab_specimens(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[LaboratorySpecimenView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_SPECIMEN_READ,
            resource_type="LaboratorySpecimen",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_lab_specimens_for_patient(identity.id, organization_id)
        return [_lab_specimen_view(item) for item in rows]

    async def reject_lab_specimen(
        self,
        principal: Principal | None,
        specimen_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratorySpecimenView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_SPECIMEN_UPDATE,
            resource_type="LaboratorySpecimen",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        specimen = await self._visible_lab_specimen(
            principal, specimen_id, organization_id, for_update=True
        )
        current = LaboratorySpecimenStatus(specimen.status)
        assert_lab_specimen_transition(current, LaboratorySpecimenStatus.REJECTED)
        specimen.status = LaboratorySpecimenStatus.REJECTED.value
        await self._audit_success(
            ClinicalAuditAction.LAB_SPECIMEN_REJECTED,
            principal,
            organization_id,
            specimen.facility_id,
            specimen.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=specimen.id,
            metadata={"old_status": current.value},
        )
        return _lab_specimen_view(specimen)

    async def mark_lab_specimen_entered_in_error(
        self,
        principal: Principal | None,
        specimen_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratorySpecimenView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_SPECIMEN_ENTERED_IN_ERROR,
            resource_type="LaboratorySpecimen",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        specimen = await self._visible_lab_specimen(
            principal, specimen_id, organization_id, for_update=True
        )
        current = LaboratorySpecimenStatus(specimen.status)
        assert_lab_specimen_transition(current, LaboratorySpecimenStatus.ENTERED_IN_ERROR)
        specimen.status = LaboratorySpecimenStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.LAB_SPECIMEN_ENTERED_IN_ERROR,
            principal,
            organization_id,
            specimen.facility_id,
            specimen.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=specimen.id,
            metadata={"old_status": current.value},
        )
        return _lab_specimen_view(specimen)

    async def create_lab_result(
        self,
        principal: Principal | None,
        *,
        laboratory_specimen_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        code: CodeableConcept,
        value: LaboratoryResultValue,
        interpretation: LaboratoryResultInterpretation | None,
        effective_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryResultView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_RESULT_CREATE,
            resource_type="LaboratoryResult",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        specimen = await self._visible_lab_specimen(
            principal, laboratory_specimen_id, organization_id, for_update=True
        )
        assert_lab_specimen_collectable(LaboratorySpecimenStatus(specimen.status))
        order = await self._visible_lab_order(
            principal, specimen.laboratory_order_id, organization_id, for_update=True
        )
        assert_lab_order_open(LaboratoryOrderStatus(order.status))
        result_id = new_id()
        bound_facility_id = facility_id or specimen.facility_id
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.LABORATORY_RESULT,
            subject_id=result_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        result = LaboratoryResultModel(
            id=result_id,
            laboratory_order_id=order.id,
            laboratory_specimen_id=specimen.id,
            patient_identity_id=specimen.patient_identity_id,
            encounter_id=specimen.encounter_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            status=LaboratoryResultStatus.FINAL.value,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
            interpretation=None if interpretation is None else interpretation.value,
            effective_at=effective_at,
        )
        _apply_lab_result_value(result, value)
        await self._clinical.add_lab_result(result)
        await self._audit_success(
            ClinicalAuditAction.LAB_RESULT_CREATED,
            principal,
            organization_id,
            result.facility_id,
            result.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=result.id,
            metadata={"status": result.status, "interpretation": result.interpretation or ""},
        )
        return _lab_result_view(result)

    async def get_lab_result(
        self,
        principal: Principal | None,
        result_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryResultView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_RESULT_READ,
            resource_type="LaboratoryResult",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        result = await self._visible_lab_result(principal, result_id, organization_id)
        return _lab_result_view(result)

    async def list_lab_results(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[LaboratoryResultView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_RESULT_READ,
            resource_type="LaboratoryResult",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_lab_results_for_patient(identity.id, organization_id)
        return [_lab_result_view(item) for item in rows]

    async def amend_lab_result(
        self,
        principal: Principal | None,
        result_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        value: LaboratoryResultValue,
        interpretation: LaboratoryResultInterpretation | None,
        effective_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryResultView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_RESULT_UPDATE,
            resource_type="LaboratoryResult",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        result = await self._visible_lab_result(
            principal, result_id, organization_id, for_update=True
        )
        current_status = LaboratoryResultStatus(result.status)
        assert_lab_result_can_amend(current_status)
        current_value = _lab_result_value_from_model(result)
        if value.value_type is not current_value.value_type:
            raise AppError(
                "lab_result_value_type_immutable",
                "Laboratory result value type cannot change",
                status_code=422,
            )
        next_effective = result.effective_at if effective_at is None else effective_at
        next_interpretation = (
            result.interpretation if interpretation is None else interpretation.value
        )
        if (
            laboratory_result_values_equal(current_value, value)
            and next_effective == result.effective_at
            and next_interpretation == result.interpretation
        ):
            raise AppError(
                "lab_result_unchanged",
                "Laboratory result is already at the requested values",
                status_code=409,
            )
        old_status = result.status
        _apply_lab_result_value(result, value)
        result.effective_at = next_effective
        result.interpretation = next_interpretation
        result.status = LaboratoryResultStatus.AMENDED.value
        result.version = result.version + 1
        await self._audit_success(
            ClinicalAuditAction.LAB_RESULT_AMENDED,
            principal,
            organization_id,
            result.facility_id,
            result.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=result.id,
            metadata={
                "old_status": old_status,
                "new_status": result.status,
                "version": str(result.version),
            },
        )
        return _lab_result_view(result)

    async def mark_lab_result_entered_in_error(
        self,
        principal: Principal | None,
        result_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> LaboratoryResultView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_LAB_RESULT_ENTERED_IN_ERROR,
            resource_type="LaboratoryResult",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        result = await self._visible_lab_result(
            principal, result_id, organization_id, for_update=True
        )
        assert_lab_result_mutable(LaboratoryResultStatus(result.status))
        result.status = LaboratoryResultStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.LAB_RESULT_ENTERED_IN_ERROR,
            principal,
            organization_id,
            result.facility_id,
            result.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=result.id,
            metadata={"purpose": purpose},
        )
        return _lab_result_view(result)

    async def create_medication(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: MedicationCategory,
        code: CodeableConcept,
        dose_numeric: Decimal | None,
        dose_unit: str | None,
        route: MedicationRoute | None,
        started_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICATION_CREATE,
            resource_type="Medication",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_id is None
        ):
            raise AppError(
                "anonymous_medication_requires_encounter",
                "An anonymous identity may receive only an emergency encounter medication",
                status_code=409,
            )
        parsed_dose, parsed_unit = _parse_medication_dose(dose_numeric, dose_unit)
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive medications",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "medication_patient_mismatch",
                    "Medication patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    "An anonymous identity may receive only an emergency encounter medication",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        medication_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.MEDICATION,
            subject_id=medication_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        medication = MedicationModel(
            id=medication_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            status=MedicationStatus.ACTIVE.value,
            dose_numeric=parsed_dose,
            dose_unit=parsed_unit,
            route=None if route is None else route.value,
            started_at=started_at,
            stopped_at=None,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
        )
        await self._clinical.add_medication(medication)
        await self._audit_success(
            ClinicalAuditAction.MEDICATION_CREATED,
            principal,
            organization_id,
            medication.facility_id,
            medication.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=medication.id,
            metadata={"category": medication.category, "status": medication.status},
        )
        return _medication_view(medication)

    async def get_medication(
        self,
        principal: Principal | None,
        medication_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICATION_READ,
            resource_type="Medication",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        medication = await self._visible_medication(principal, medication_id, organization_id)
        return _medication_view(medication)

    async def list_medications(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[MedicationView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICATION_READ,
            resource_type="Medication",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_medications_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_medication_view(item) for item in rows]

    async def stop_medication(
        self,
        principal: Principal | None,
        medication_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICATION_UPDATE,
            resource_type="Medication",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        medication = await self._visible_medication(
            principal, medication_id, organization_id, for_update=True
        )
        current_status = MedicationStatus(medication.status)
        assert_medication_can_stop(current_status)
        medication.status = MedicationStatus.STOPPED.value
        medication.stopped_at = utc_now()
        medication.version = medication.version + 1
        await self._audit_success(
            ClinicalAuditAction.MEDICATION_STOPPED,
            principal,
            organization_id,
            medication.facility_id,
            medication.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=medication.id,
            metadata={"status": medication.status, "version": str(medication.version)},
        )
        return _medication_view(medication)

    async def mark_medication_entered_in_error(
        self,
        principal: Principal | None,
        medication_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICATION_ENTERED_IN_ERROR,
            resource_type="Medication",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        medication = await self._visible_medication(
            principal, medication_id, organization_id, for_update=True
        )
        assert_medication_mutable(MedicationStatus(medication.status))
        medication.status = MedicationStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.MEDICATION_ENTERED_IN_ERROR,
            principal,
            organization_id,
            medication.facility_id,
            medication.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=medication.id,
            metadata={"purpose": purpose},
        )
        return _medication_view(medication)

    async def create_allergy(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: AllergyCategory,
        code: CodeableConcept,
        clinical_status: AllergyClinicalStatus,
        verification_status: AllergyVerificationStatus,
        criticality: AllergyCriticality | None,
        severity: AllergySeverity | None,
        reaction: CodeableConcept | None,
        onset_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> AllergyView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ALLERGY_CREATE,
            resource_type="Allergy",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_id is None
        ):
            raise AppError(
                "anonymous_allergy_requires_encounter",
                "An anonymous identity may receive only an emergency encounter allergy",
                status_code=409,
            )
        reaction_system, reaction_code, reaction_display = _parse_optional_reaction(reaction)
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive allergies",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "allergy_patient_mismatch",
                    "Allergy patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    "An anonymous identity may receive only an emergency encounter allergy",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        allergy_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.ALLERGY,
            subject_id=allergy_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        allergy = AllergyModel(
            id=allergy_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            status=AllergyStatus.ACTIVE.value,
            clinical_status=clinical_status.value,
            verification_status=verification_status.value,
            criticality=None if criticality is None else criticality.value,
            severity=None if severity is None else severity.value,
            reaction_code_system=reaction_system,
            reaction_code=reaction_code,
            reaction_display=reaction_display,
            onset_at=onset_at,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
        )
        await self._clinical.add_allergy(allergy)
        await self._audit_success(
            ClinicalAuditAction.ALLERGY_CREATED,
            principal,
            organization_id,
            allergy.facility_id,
            allergy.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=allergy.id,
            metadata={
                "category": allergy.category,
                "status": allergy.status,
                "clinical_status": allergy.clinical_status,
                "verification_status": allergy.verification_status,
            },
        )
        return _allergy_view(allergy)

    async def get_allergy(
        self,
        principal: Principal | None,
        allergy_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> AllergyView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ALLERGY_READ,
            resource_type="Allergy",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        allergy = await self._visible_allergy(principal, allergy_id, organization_id)
        return _allergy_view(allergy)

    async def list_allergies(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[AllergyView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ALLERGY_READ,
            resource_type="Allergy",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_allergies_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_allergy_view(item) for item in rows]

    async def amend_allergy(
        self,
        principal: Principal | None,
        allergy_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        clinical_status: AllergyClinicalStatus,
        verification_status: AllergyVerificationStatus,
        criticality: AllergyCriticality | None,
        severity: AllergySeverity | None,
        reaction: CodeableConcept | None,
        onset_at: datetime | None,
        purpose: str,
        correlation_id: str | None,
    ) -> AllergyView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ALLERGY_UPDATE,
            resource_type="Allergy",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        allergy = await self._visible_allergy(
            principal, allergy_id, organization_id, for_update=True
        )
        current_status = AllergyStatus(allergy.status)
        assert_allergy_can_amend(current_status)
        reaction_system, reaction_code, reaction_display = _parse_optional_reaction(reaction)
        next_criticality = None if criticality is None else criticality.value
        next_severity = None if severity is None else severity.value
        unchanged = (
            allergy.clinical_status == clinical_status.value
            and allergy.verification_status == verification_status.value
            and allergy.criticality == next_criticality
            and allergy.severity == next_severity
            and allergy.reaction_code_system == reaction_system
            and allergy.reaction_code == reaction_code
            and allergy.reaction_display == reaction_display
            and allergy.onset_at == onset_at
        )
        if unchanged:
            raise AppError(
                "allergy_unchanged",
                "Allergy is already at the requested values",
                status_code=409,
            )
        old_status = allergy.status
        allergy.clinical_status = clinical_status.value
        allergy.verification_status = verification_status.value
        allergy.criticality = next_criticality
        allergy.severity = next_severity
        allergy.reaction_code_system = reaction_system
        allergy.reaction_code = reaction_code
        allergy.reaction_display = reaction_display
        allergy.onset_at = onset_at
        allergy.status = AllergyStatus.AMENDED.value
        allergy.version = allergy.version + 1
        await self._audit_success(
            ClinicalAuditAction.ALLERGY_AMENDED,
            principal,
            organization_id,
            allergy.facility_id,
            allergy.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=allergy.id,
            metadata={
                "old_status": old_status,
                "new_status": allergy.status,
                "clinical_status": allergy.clinical_status,
                "verification_status": allergy.verification_status,
                "version": str(allergy.version),
            },
        )
        return _allergy_view(allergy)

    async def mark_allergy_entered_in_error(
        self,
        principal: Principal | None,
        allergy_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> AllergyView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_ALLERGY_ENTERED_IN_ERROR,
            resource_type="Allergy",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        allergy = await self._visible_allergy(
            principal, allergy_id, organization_id, for_update=True
        )
        assert_allergy_mutable(AllergyStatus(allergy.status))
        allergy.status = AllergyStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.ALLERGY_ENTERED_IN_ERROR,
            principal,
            organization_id,
            allergy.facility_id,
            allergy.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=allergy.id,
            metadata={"purpose": purpose},
        )
        return _allergy_view(allergy)

    async def create_consent(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: ConsentCategory,
        scope: ConsentScope,
        decision: ConsentDecision,
        code: CodeableConcept | None,
        source: ConsentSource,
        period_start: datetime | None,
        period_end: datetime | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConsentView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONSENT_CREATE,
            resource_type="Consent",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS:
            raise AppError(
                "anonymous_consent_not_allowed",
                "An anonymous identity cannot receive a consent record",
                status_code=409,
            )
        assert_consent_period(period_start, period_end)
        code_system, code_value, code_display = _parse_optional_consent_code(code)
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive consents",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "consent_patient_mismatch",
                    "Consent patient must match the encounter patient",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        consent_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.CONSENT,
            subject_id=consent_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        consent = ConsentModel(
            id=consent_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            scope=scope.value,
            decision=decision.value,
            code_system=code_system,
            code=code_value,
            code_display=code_display,
            source=source.value,
            period_start=period_start,
            period_end=period_end,
            note_text=None if note_text is None or note_text.strip() == "" else note_text.strip(),
            status=ConsentStatus.ACTIVE.value,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            revoked_at=None,
            version=1,
            provenance_id=provenance.id,
        )
        await self._clinical.add_consent(consent)
        await self._audit_success(
            ClinicalAuditAction.CONSENT_CREATED,
            principal,
            organization_id,
            consent.facility_id,
            consent.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=consent.id,
            metadata={
                "category": consent.category,
                "scope": consent.scope,
                "decision": consent.decision,
                "status": consent.status,
            },
        )
        return _consent_view(consent)

    async def get_consent(
        self,
        principal: Principal | None,
        consent_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConsentView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONSENT_READ,
            resource_type="Consent",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        consent = await self._visible_consent(principal, consent_id, organization_id)
        return _consent_view(consent)

    async def list_consents(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[ConsentView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONSENT_READ,
            resource_type="Consent",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_consents_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_consent_view(item) for item in rows]

    async def amend_consent(
        self,
        principal: Principal | None,
        consent_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        period_start: datetime | None,
        period_end: datetime | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConsentView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONSENT_UPDATE,
            resource_type="Consent",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        consent = await self._visible_consent(
            principal, consent_id, organization_id, for_update=True
        )
        assert_consent_can_amend(ConsentStatus(consent.status))
        assert_consent_period(period_start, period_end)
        next_note = None if note_text is None or note_text.strip() == "" else note_text.strip()
        unchanged = (
            consent.period_start == period_start
            and consent.period_end == period_end
            and consent.note_text == next_note
        )
        if unchanged:
            raise AppError(
                "consent_unchanged",
                "Consent is already at the requested values",
                status_code=409,
            )
        old_status = consent.status
        consent.period_start = period_start
        consent.period_end = period_end
        consent.note_text = next_note
        consent.status = ConsentStatus.AMENDED.value
        consent.version = consent.version + 1
        await self._audit_success(
            ClinicalAuditAction.CONSENT_AMENDED,
            principal,
            organization_id,
            consent.facility_id,
            consent.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=consent.id,
            metadata={
                "old_status": old_status,
                "new_status": consent.status,
                "status": consent.status,
                "version": str(consent.version),
            },
        )
        return _consent_view(consent)

    async def revoke_consent(
        self,
        principal: Principal | None,
        consent_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConsentView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONSENT_REVOKE,
            resource_type="Consent",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        consent = await self._visible_consent(
            principal, consent_id, organization_id, for_update=True
        )
        assert_consent_can_revoke(ConsentStatus(consent.status))
        old_status = consent.status
        consent.status = ConsentStatus.REVOKED.value
        consent.revoked_at = utc_now()
        consent.version = consent.version + 1
        await self._audit_success(
            ClinicalAuditAction.CONSENT_REVOKED,
            principal,
            organization_id,
            consent.facility_id,
            consent.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=consent.id,
            metadata={
                "old_status": old_status,
                "new_status": consent.status,
                "status": consent.status,
                "version": str(consent.version),
            },
        )
        return _consent_view(consent)

    async def mark_consent_entered_in_error(
        self,
        principal: Principal | None,
        consent_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ConsentView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_CONSENT_ENTERED_IN_ERROR,
            resource_type="Consent",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        consent = await self._visible_consent(
            principal, consent_id, organization_id, for_update=True
        )
        assert_consent_mutable(ConsentStatus(consent.status))
        old_status = consent.status
        consent.status = ConsentStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.CONSENT_ENTERED_IN_ERROR,
            principal,
            organization_id,
            consent.facility_id,
            consent.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=consent.id,
            metadata={
                "old_status": old_status,
                "new_status": consent.status,
                "status": consent.status,
            },
        )
        return _consent_view(consent)

    async def create_immunization(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: ImmunizationCategory,
        code: CodeableConcept,
        occurrence_at: datetime | None,
        route: ImmunizationRoute | None,
        site: ImmunizationSite | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ImmunizationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_IMMUNIZATION_CREATE,
            resource_type="Immunization",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_id is None
        ):
            raise AppError(
                "anonymous_immunization_requires_encounter",
                "An anonymous identity may receive only an emergency encounter immunization",
                status_code=409,
            )
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive immunizations",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "immunization_patient_mismatch",
                    "Immunization patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    "An anonymous identity may receive only an emergency encounter immunization",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        immunization_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.IMMUNIZATION,
            subject_id=immunization_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        immunization = ImmunizationModel(
            id=immunization_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            occurrence_at=occurrence_at,
            route=None if route is None else route.value,
            site=None if site is None else site.value,
            note_text=None if note_text is None or note_text.strip() == "" else note_text.strip(),
            status=ImmunizationStatus.ACTIVE.value,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
        )
        await self._clinical.add_immunization(immunization)
        await self._audit_success(
            ClinicalAuditAction.IMMUNIZATION_CREATED,
            principal,
            organization_id,
            immunization.facility_id,
            immunization.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=immunization.id,
            metadata={
                "category": immunization.category,
                "status": immunization.status,
                "version": str(immunization.version),
            },
        )
        return _immunization_view(immunization)

    async def get_immunization(
        self,
        principal: Principal | None,
        immunization_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ImmunizationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_IMMUNIZATION_READ,
            resource_type="Immunization",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        immunization = await self._visible_immunization(principal, immunization_id, organization_id)
        return _immunization_view(immunization)

    async def list_immunizations(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[ImmunizationView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_IMMUNIZATION_READ,
            resource_type="Immunization",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_immunizations_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_immunization_view(item) for item in rows]

    async def amend_immunization(
        self,
        principal: Principal | None,
        immunization_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        occurrence_at: datetime | None,
        route: ImmunizationRoute | None,
        site: ImmunizationSite | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ImmunizationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_IMMUNIZATION_UPDATE,
            resource_type="Immunization",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        immunization = await self._visible_immunization(
            principal, immunization_id, organization_id, for_update=True
        )
        assert_immunization_can_amend(ImmunizationStatus(immunization.status))
        next_route = None if route is None else route.value
        next_site = None if site is None else site.value
        next_note = None if note_text is None or note_text.strip() == "" else note_text.strip()
        unchanged = (
            immunization.occurrence_at == occurrence_at
            and immunization.route == next_route
            and immunization.site == next_site
            and immunization.note_text == next_note
        )
        if unchanged:
            raise AppError(
                "immunization_unchanged",
                "Immunization is already at the requested values",
                status_code=409,
            )
        old_status = immunization.status
        immunization.occurrence_at = occurrence_at
        immunization.route = next_route
        immunization.site = next_site
        immunization.note_text = next_note
        immunization.status = ImmunizationStatus.AMENDED.value
        immunization.version = immunization.version + 1
        await self._audit_success(
            ClinicalAuditAction.IMMUNIZATION_AMENDED,
            principal,
            organization_id,
            immunization.facility_id,
            immunization.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=immunization.id,
            metadata={
                "old_status": old_status,
                "new_status": immunization.status,
                "status": immunization.status,
                "version": str(immunization.version),
            },
        )
        return _immunization_view(immunization)

    async def mark_immunization_entered_in_error(
        self,
        principal: Principal | None,
        immunization_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ImmunizationView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_IMMUNIZATION_ENTERED_IN_ERROR,
            resource_type="Immunization",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        immunization = await self._visible_immunization(
            principal, immunization_id, organization_id, for_update=True
        )
        assert_immunization_mutable(ImmunizationStatus(immunization.status))
        old_status = immunization.status
        immunization.status = ImmunizationStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.IMMUNIZATION_ENTERED_IN_ERROR,
            principal,
            organization_id,
            immunization.facility_id,
            immunization.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=immunization.id,
            metadata={
                "old_status": old_status,
                "new_status": immunization.status,
                "status": immunization.status,
            },
        )
        return _immunization_view(immunization)

    async def create_procedure(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: ProcedureCategory,
        code: CodeableConcept,
        occurrence_at: datetime | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ProcedureView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_PROCEDURE_CREATE,
            resource_type="Procedure",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_id is None
        ):
            raise AppError(
                "anonymous_procedure_requires_encounter",
                "An anonymous identity may receive only an emergency encounter procedure",
                status_code=409,
            )
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive procedures",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "procedure_patient_mismatch",
                    "Procedure patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    "An anonymous identity may receive only an emergency encounter procedure",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        procedure_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.PROCEDURE,
            subject_id=procedure_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        procedure = ProcedureModel(
            id=procedure_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            occurrence_at=occurrence_at,
            note_text=None if note_text is None or note_text.strip() == "" else note_text.strip(),
            status=ProcedureStatus.ACTIVE.value,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
        )
        await self._clinical.add_procedure(procedure)
        await self._audit_success(
            ClinicalAuditAction.PROCEDURE_CREATED,
            principal,
            organization_id,
            procedure.facility_id,
            procedure.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=procedure.id,
            metadata={
                "category": procedure.category,
                "status": procedure.status,
                "version": str(procedure.version),
            },
        )
        return _procedure_view(procedure)

    async def get_procedure(
        self,
        principal: Principal | None,
        procedure_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ProcedureView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_PROCEDURE_READ,
            resource_type="Procedure",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        procedure = await self._visible_procedure(principal, procedure_id, organization_id)
        return _procedure_view(procedure)

    async def list_procedures(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[ProcedureView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_PROCEDURE_READ,
            resource_type="Procedure",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_procedures_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_procedure_view(item) for item in rows]

    async def amend_procedure(
        self,
        principal: Principal | None,
        procedure_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        occurrence_at: datetime | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ProcedureView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_PROCEDURE_UPDATE,
            resource_type="Procedure",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        procedure = await self._visible_procedure(
            principal, procedure_id, organization_id, for_update=True
        )
        assert_procedure_can_amend(ProcedureStatus(procedure.status))
        next_note = None if note_text is None or note_text.strip() == "" else note_text.strip()
        unchanged = procedure.occurrence_at == occurrence_at and procedure.note_text == next_note
        if unchanged:
            raise AppError(
                "procedure_unchanged",
                "Procedure is already at the requested values",
                status_code=409,
            )
        old_status = procedure.status
        procedure.occurrence_at = occurrence_at
        procedure.note_text = next_note
        procedure.status = ProcedureStatus.AMENDED.value
        procedure.version = procedure.version + 1
        await self._audit_success(
            ClinicalAuditAction.PROCEDURE_AMENDED,
            principal,
            organization_id,
            procedure.facility_id,
            procedure.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=procedure.id,
            metadata={
                "old_status": old_status,
                "new_status": procedure.status,
                "status": procedure.status,
                "version": str(procedure.version),
            },
        )
        return _procedure_view(procedure)

    async def mark_procedure_entered_in_error(
        self,
        principal: Principal | None,
        procedure_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> ProcedureView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_PROCEDURE_ENTERED_IN_ERROR,
            resource_type="Procedure",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        procedure = await self._visible_procedure(
            principal, procedure_id, organization_id, for_update=True
        )
        assert_procedure_mutable(ProcedureStatus(procedure.status))
        old_status = procedure.status
        procedure.status = ProcedureStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.PROCEDURE_ENTERED_IN_ERROR,
            principal,
            organization_id,
            procedure.facility_id,
            procedure.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=procedure.id,
            metadata={
                "old_status": old_status,
                "new_status": procedure.status,
                "status": procedure.status,
            },
        )
        return _procedure_view(procedure)

    async def create_medical_device(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        category: MedicalDeviceCategory,
        code: CodeableConcept,
        association_status: MedicalDeviceAssociationStatus,
        occurrence_at: datetime | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicalDeviceView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICAL_DEVICE_CREATE,
            resource_type="MedicalDevice",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_id is None
        ):
            raise AppError(
                "anonymous_medical_device_requires_encounter",
                "An anonymous identity may receive only an emergency encounter medical device",
                status_code=409,
            )
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    "A cancelled or erroneous encounter cannot receive medical devices",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "medical_device_patient_mismatch",
                    "Medical device patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    "An anonymous identity may receive only an emergency encounter medical device",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        medical_device_id = new_id()
        provenance = await self._record_provenance(
            subject_type=ClinicalProvenanceSubjectType.MEDICAL_DEVICE,
            subject_id=medical_device_id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            actor_id=None if principal is None else principal.user.id,
        )
        medical_device = MedicalDeviceModel(
            id=medical_device_id,
            patient_identity_id=bound_patient_id,
            encounter_id=None if encounter is None else encounter.id,
            organization_id=organization_id,
            facility_id=bound_facility_id,
            category=category.value,
            code_system=code.system,
            code=code.code,
            code_display=code.display,
            association_status=association_status.value,
            occurrence_at=occurrence_at,
            note_text=None if note_text is None or note_text.strip() == "" else note_text.strip(),
            status=MedicalDeviceStatus.ACTIVE.value,
            recorded_at=utc_now(),
            recorder_id=None if principal is None else principal.user.id,
            version=1,
            provenance_id=provenance.id,
        )
        await self._clinical.add_medical_device(medical_device)
        await self._audit_success(
            ClinicalAuditAction.MEDICAL_DEVICE_CREATED,
            principal,
            organization_id,
            medical_device.facility_id,
            medical_device.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=medical_device.id,
            metadata={
                "category": medical_device.category,
                "status": medical_device.status,
                "association_status": medical_device.association_status,
                "version": str(medical_device.version),
            },
        )
        return _medical_device_view(medical_device)

    async def get_medical_device(
        self,
        principal: Principal | None,
        medical_device_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicalDeviceView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICAL_DEVICE_READ,
            resource_type="MedicalDevice",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        medical_device = await self._visible_medical_device(
            principal, medical_device_id, organization_id
        )
        return _medical_device_view(medical_device)

    async def list_medical_devices(
        self,
        principal: Principal | None,
        *,
        patient_identity_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        encounter_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> list[MedicalDeviceView]:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICAL_DEVICE_READ,
            resource_type="MedicalDevice",
            organization_id=organization_id,
            facility_id=facility_id,
            patient_id=patient_identity_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        rows = await self._clinical.list_medical_devices_for_patient(
            identity.id, organization_id, encounter_id=encounter_id
        )
        return [_medical_device_view(item) for item in rows]

    async def amend_medical_device(
        self,
        principal: Principal | None,
        medical_device_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        association_status: MedicalDeviceAssociationStatus | None,
        occurrence_at: datetime | None,
        note_text: str | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicalDeviceView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICAL_DEVICE_UPDATE,
            resource_type="MedicalDevice",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        medical_device = await self._visible_medical_device(
            principal, medical_device_id, organization_id, for_update=True
        )
        assert_medical_device_can_amend(MedicalDeviceStatus(medical_device.status))
        next_association = (
            medical_device.association_status
            if association_status is None
            else association_status.value
        )
        next_note = None if note_text is None or note_text.strip() == "" else note_text.strip()
        unchanged = (
            medical_device.association_status == next_association
            and medical_device.occurrence_at == occurrence_at
            and medical_device.note_text == next_note
        )
        if unchanged:
            raise AppError(
                "medical_device_unchanged",
                "Medical device is already at the requested values",
                status_code=409,
            )
        old_status = medical_device.status
        medical_device.association_status = next_association
        medical_device.occurrence_at = occurrence_at
        medical_device.note_text = next_note
        medical_device.status = MedicalDeviceStatus.AMENDED.value
        medical_device.version = medical_device.version + 1
        await self._audit_success(
            ClinicalAuditAction.MEDICAL_DEVICE_AMENDED,
            principal,
            organization_id,
            medical_device.facility_id,
            medical_device.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=medical_device.id,
            metadata={
                "old_status": old_status,
                "new_status": medical_device.status,
                "status": medical_device.status,
                "association_status": medical_device.association_status,
                "version": str(medical_device.version),
            },
        )
        return _medical_device_view(medical_device)

    async def mark_medical_device_entered_in_error(
        self,
        principal: Principal | None,
        medical_device_id: UUID,
        *,
        organization_id: UUID,
        facility_id: UUID | None,
        purpose: str,
        correlation_id: str | None,
    ) -> MedicalDeviceView:
        await authorize(
            self._pdp,
            self._audit,
            principal=principal,
            action=Permission.CLINICAL_MEDICAL_DEVICE_ENTERED_IN_ERROR,
            resource_type="MedicalDevice",
            organization_id=organization_id,
            facility_id=facility_id,
            purpose=purpose,
            correlation_id=correlation_id,
        )
        medical_device = await self._visible_medical_device(
            principal, medical_device_id, organization_id, for_update=True
        )
        assert_medical_device_mutable(MedicalDeviceStatus(medical_device.status))
        old_status = medical_device.status
        medical_device.status = MedicalDeviceStatus.ENTERED_IN_ERROR.value
        await self._audit_success(
            ClinicalAuditAction.MEDICAL_DEVICE_ENTERED_IN_ERROR,
            principal,
            organization_id,
            medical_device.facility_id,
            medical_device.patient_identity_id,
            purpose,
            correlation_id,
            resource_id=medical_device.id,
            metadata={
                "old_status": old_status,
                "new_status": medical_device.status,
                "status": medical_device.status,
                "association_status": medical_device.association_status,
            },
        )
        return _medical_device_view(medical_device)

    async def _require_canonical_identity(
        self,
        principal: Principal | None,
        identity_id: UUID,
        organization_id: UUID,
    ) -> PatientIdentityModel:
        await self._require_visible_identity(principal, identity_id, organization_id)
        canonical = await self._mpi.resolve_canonical_identity(identity_id)
        if canonical is None:
            raise AppError(
                "canonical_resolution_failed",
                "Identity cannot be resolved to a canonical active identity",
                status_code=409,
            )
        return canonical

    async def _require_visible_identity(
        self,
        principal: Principal | None,
        identity_id: UUID,
        organization_id: UUID,
    ) -> PatientIdentityModel:
        identity = await self._mpi.get_identity(identity_id)
        if identity is None:
            raise NotFoundError("Patient identity not found")
        if not await self._identity_visible(principal, identity, organization_id):
            raise NotFoundError("Patient identity not found")
        if IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.RETIRED:
            raise AppError(
                "identity_not_usable",
                "A retired identity cannot receive clinical records",
                status_code=409,
            )
        return identity

    async def _identity_visible(
        self,
        principal: Principal | None,
        identity: PatientIdentityModel,
        organization_id: UUID,
    ) -> bool:
        if principal is not None and principal.has_platform_scope:
            return True
        provenances = await self._mpi.list_provenances(identity.id)
        if any(item.source_organization_id == organization_id for item in provenances):
            return True
        identifiers = await self._mpi.list_identifiers(identity.id)
        return any(item.organization_id == organization_id for item in identifiers)

    async def _visible_encounter(
        self,
        principal: Principal | None,
        encounter_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> EncounterModel:
        if for_update:
            encounter = await self._clinical.get_encounter_for_update(encounter_id)
        else:
            encounter = await self._clinical.get_encounter(encounter_id)
        if encounter is None:
            raise NotFoundError("Encounter not found")
        if principal is not None and principal.has_platform_scope:
            return encounter
        if encounter.organization_id != organization_id:
            raise NotFoundError("Encounter not found")
        return encounter

    async def _visible_note(
        self,
        principal: Principal | None,
        note_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> ClinicalNoteModel:
        if for_update:
            note = await self._clinical.get_note_for_update(note_id)
        else:
            note = await self._clinical.get_note(note_id)
        if note is None:
            raise NotFoundError("Clinical note not found")
        if principal is not None and principal.has_platform_scope:
            return note
        if note.organization_id != organization_id:
            raise NotFoundError("Clinical note not found")
        return note

    async def _visible_condition(
        self,
        principal: Principal | None,
        condition_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> ConditionModel:
        if for_update:
            condition = await self._clinical.get_condition_for_update(condition_id)
        else:
            condition = await self._clinical.get_condition(condition_id)
        if condition is None:
            raise NotFoundError("Condition not found")
        if principal is not None and principal.has_platform_scope:
            return condition
        if condition.organization_id != organization_id:
            raise NotFoundError("Condition not found")
        return condition

    async def _visible_observation(
        self,
        principal: Principal | None,
        observation_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> ObservationModel:
        if for_update:
            observation = await self._clinical.get_observation_for_update(observation_id)
        else:
            observation = await self._clinical.get_observation(observation_id)
        if observation is None:
            raise NotFoundError("Observation not found")
        if principal is not None and principal.has_platform_scope:
            return observation
        if observation.organization_id != organization_id:
            raise NotFoundError("Observation not found")
        return observation

    async def _bind_lab_identity(
        self,
        principal: Principal | None,
        patient_identity_id: UUID,
        encounter_id: UUID | None,
        organization_id: UUID,
        facility_id: UUID | None,
        *,
        resource: str,
    ) -> tuple[PatientIdentityModel, EncounterModel | None, UUID, UUID | None]:
        identity = await self._require_canonical_identity(
            principal, patient_identity_id, organization_id
        )
        if (
            IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
            and encounter_id is None
        ):
            raise AppError(
                "anonymous_laboratory_requires_encounter",
                f"An anonymous identity may receive only an emergency encounter {resource}",
                status_code=409,
            )
        encounter = None
        bound_patient_id = identity.id
        bound_facility_id = facility_id
        if encounter_id is not None:
            encounter = await self._visible_encounter(
                principal, encounter_id, organization_id, for_update=True
            )
            if EncounterStatus(encounter.status) in {
                EncounterStatus.CANCELLED,
                EncounterStatus.ENTERED_IN_ERROR,
            }:
                raise AppError(
                    "encounter_not_documentable",
                    f"A cancelled or erroneous encounter cannot receive {resource}s",
                    status_code=409,
                )
            if encounter.patient_identity_id != identity.id:
                raise AppError(
                    "laboratory_patient_mismatch",
                    "Laboratory patient must match the encounter patient",
                    status_code=409,
                )
            if (
                IdentityLifecycle(identity.lifecycle_status) is IdentityLifecycle.ANONYMOUS
                and EncounterClass(encounter.encounter_class) is not EncounterClass.EMER
            ):
                raise AppError(
                    "anonymous_encounter_not_emergency",
                    f"An anonymous identity may receive only an emergency encounter {resource}",
                    status_code=409,
                )
            bound_patient_id = encounter.patient_identity_id
            bound_facility_id = facility_id or encounter.facility_id
        return identity, encounter, bound_patient_id, bound_facility_id

    async def _visible_lab_order(
        self,
        principal: Principal | None,
        order_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> LaboratoryOrderModel:
        if for_update:
            order = await self._clinical.get_lab_order_for_update(order_id)
        else:
            order = await self._clinical.get_lab_order(order_id)
        if order is None:
            raise NotFoundError("Laboratory order not found")
        if principal is not None and principal.has_platform_scope:
            return order
        if order.organization_id != organization_id:
            raise NotFoundError("Laboratory order not found")
        return order

    async def _visible_lab_specimen(
        self,
        principal: Principal | None,
        specimen_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> LaboratorySpecimenModel:
        if for_update:
            specimen = await self._clinical.get_lab_specimen_for_update(specimen_id)
        else:
            specimen = await self._clinical.get_lab_specimen(specimen_id)
        if specimen is None:
            raise NotFoundError("Laboratory specimen not found")
        if principal is not None and principal.has_platform_scope:
            return specimen
        if specimen.organization_id != organization_id:
            raise NotFoundError("Laboratory specimen not found")
        return specimen

    async def _visible_lab_result(
        self,
        principal: Principal | None,
        result_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> LaboratoryResultModel:
        if for_update:
            result = await self._clinical.get_lab_result_for_update(result_id)
        else:
            result = await self._clinical.get_lab_result(result_id)
        if result is None:
            raise NotFoundError("Laboratory result not found")
        if principal is not None and principal.has_platform_scope:
            return result
        if result.organization_id != organization_id:
            raise NotFoundError("Laboratory result not found")
        return result

    async def _visible_medication(
        self,
        principal: Principal | None,
        medication_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> MedicationModel:
        if for_update:
            medication = await self._clinical.get_medication_for_update(medication_id)
        else:
            medication = await self._clinical.get_medication(medication_id)
        if medication is None:
            raise NotFoundError("Medication not found")
        if principal is not None and principal.has_platform_scope:
            return medication
        if medication.organization_id != organization_id:
            raise NotFoundError("Medication not found")
        return medication

    async def _visible_allergy(
        self,
        principal: Principal | None,
        allergy_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> AllergyModel:
        if for_update:
            allergy = await self._clinical.get_allergy_for_update(allergy_id)
        else:
            allergy = await self._clinical.get_allergy(allergy_id)
        if allergy is None:
            raise NotFoundError("Allergy not found")
        if principal is not None and principal.has_platform_scope:
            return allergy
        if allergy.organization_id != organization_id:
            raise NotFoundError("Allergy not found")
        return allergy

    async def _visible_consent(
        self,
        principal: Principal | None,
        consent_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> ConsentModel:
        if for_update:
            consent = await self._clinical.get_consent_for_update(consent_id)
        else:
            consent = await self._clinical.get_consent(consent_id)
        if consent is None:
            raise NotFoundError("Consent not found")
        if principal is not None and principal.has_platform_scope:
            return consent
        if consent.organization_id != organization_id:
            raise NotFoundError("Consent not found")
        return consent

    async def _visible_immunization(
        self,
        principal: Principal | None,
        immunization_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> ImmunizationModel:
        if for_update:
            immunization = await self._clinical.get_immunization_for_update(immunization_id)
        else:
            immunization = await self._clinical.get_immunization(immunization_id)
        if immunization is None:
            raise NotFoundError("Immunization not found")
        if principal is not None and principal.has_platform_scope:
            return immunization
        if immunization.organization_id != organization_id:
            raise NotFoundError("Immunization not found")
        return immunization

    async def _visible_procedure(
        self,
        principal: Principal | None,
        procedure_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> ProcedureModel:
        if for_update:
            procedure = await self._clinical.get_procedure_for_update(procedure_id)
        else:
            procedure = await self._clinical.get_procedure(procedure_id)
        if procedure is None:
            raise NotFoundError("Procedure not found")
        if principal is not None and principal.has_platform_scope:
            return procedure
        if procedure.organization_id != organization_id:
            raise NotFoundError("Procedure not found")
        return procedure

    async def _visible_medical_device(
        self,
        principal: Principal | None,
        medical_device_id: UUID,
        organization_id: UUID,
        *,
        for_update: bool = False,
    ) -> MedicalDeviceModel:
        if for_update:
            medical_device = await self._clinical.get_medical_device_for_update(medical_device_id)
        else:
            medical_device = await self._clinical.get_medical_device(medical_device_id)
        if medical_device is None:
            raise NotFoundError("Medical device not found")
        if principal is not None and principal.has_platform_scope:
            return medical_device
        if medical_device.organization_id != organization_id:
            raise NotFoundError("Medical device not found")
        return medical_device

    async def _record_provenance(
        self,
        *,
        subject_type: ClinicalProvenanceSubjectType,
        subject_id: UUID,
        organization_id: UUID,
        facility_id: UUID | None,
        actor_id: UUID | None,
    ) -> ClinicalProvenanceModel:
        model = ClinicalProvenanceModel(
            id=new_id(),
            subject_type=subject_type.value,
            subject_id=subject_id,
            source_organization_id=organization_id,
            source_facility_id=facility_id,
            actor_id=actor_id,
            recorded_at=utc_now(),
            verification_method="clinical_authorship",
            authorship_kind=AuthorshipKind.NATIVE.value,
            information_source=InformationSource.CLINICIAN.value,
        )
        return await self._clinical.add_provenance(model)

    async def _audit_success(
        self,
        action: ClinicalAuditAction,
        principal: Principal | None,
        organization_id: UUID | None,
        facility_id: UUID | None,
        patient_id: UUID | None,
        purpose: str | None,
        correlation_id: str | None,
        *,
        resource_id: UUID | None = None,
        metadata: dict[str, str] | None = None,
    ) -> None:
        await self._audit.record(
            AuditEvent(
                action=action.value,
                resource_type="ClinicalRecord",
                result=AuditResult.SUCCESS,
                actor_id=None if principal is None else principal.user.id,
                organization_id=organization_id,
                facility_id=facility_id,
                resource_id=resource_id or patient_id,
                patient_id=patient_id,
                purpose=purpose,
                correlation_id=correlation_id,
                metadata={**(metadata or {}), "purpose": purpose or ""},
            )
        )


def _require_note_body(body_text: str) -> str:
    body = body_text.strip()
    if not body:
        raise AppError("note_body_required", "Clinical note body is required", status_code=422)
    if len(body) > 20_000:
        raise AppError("note_body_too_long", "Clinical note body exceeds 20000 characters", 422)
    return body


def _content_hash(note_type: str, body: str) -> str:
    return sha256(f"{note_type}\n{body}".encode()).hexdigest()


def _encounter_view(model: EncounterModel) -> EncounterView:
    reason = None
    if model.reason_system and model.reason_code:
        reason = CodeableConcept(
            system=model.reason_system,
            code=model.reason_code,
            display=model.reason_display,
        )
    return EncounterView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        encounter_class=EncounterClass(model.encounter_class),
        status=EncounterStatus(model.status),
        display_label=model.display_label,
        started_at=model.started_at,
        ended_at=model.ended_at,
        reason=reason,
    )


def _note_view(model: ClinicalNoteModel) -> ClinicalNoteView:
    return ClinicalNoteView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        note_type=ClinicalNoteType(model.note_type),
        body_text=model.body_text,
        record_status=ClinicalRecordStatus(model.record_status),
        version=model.version,
        authored_at=model.authored_at,
        finalized_at=model.finalized_at,
    )


def _assert_condition_period(onset_at: datetime | None, abatement_at: datetime | None) -> None:
    if onset_at is not None and abatement_at is not None and abatement_at < onset_at:
        raise AppError(
            "invalid_condition_period",
            "Condition abatement cannot precede onset",
            status_code=422,
        )


def _condition_view(model: ConditionModel) -> ConditionView:
    return ConditionView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=ConditionCategory(model.category),
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        clinical_status=ConditionClinicalStatus(model.clinical_status),
        verification_status=ConditionVerificationStatus(model.verification_status),
        onset_at=model.onset_at,
        abatement_at=model.abatement_at,
        recorded_at=model.recorded_at,
    )


def _observation_value_from_model(model: ObservationModel) -> ObservationValue:
    coded = None
    if model.value_code_system and model.value_code:
        coded = CodeableConcept(
            system=model.value_code_system,
            code=model.value_code,
            display=model.value_code_display,
        )
    return ObservationValue(
        value_type=ObservationValueType(model.value_type),
        numeric=model.value_numeric,
        text=model.value_text,
        boolean=model.value_boolean,
        coded=coded,
        unit=model.unit,
        range_low=model.reference_range_low,
        range_high=model.reference_range_high,
    )


def _apply_observation_value(model: ObservationModel, value: ObservationValue) -> None:
    model.value_type = value.value_type.value
    model.value_numeric = value.numeric
    model.value_text = value.text
    model.value_boolean = value.boolean
    model.value_code_system = None if value.coded is None else value.coded.system
    model.value_code = None if value.coded is None else value.coded.code
    model.value_code_display = None if value.coded is None else value.coded.display
    model.unit = value.unit
    model.reference_range_low = value.range_low
    model.reference_range_high = value.range_high


def _observation_view(model: ObservationModel) -> ObservationView:
    coded = None
    if model.value_code_system and model.value_code:
        coded = CodeableConcept(
            system=model.value_code_system,
            code=model.value_code,
            display=model.value_code_display,
        )
    return ObservationView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=ObservationCategory(model.category),
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        status=ObservationStatus(model.status),
        value_type=ObservationValueType(model.value_type),
        value_numeric=model.value_numeric,
        value_text=model.value_text,
        value_boolean=model.value_boolean,
        value_coded=coded,
        unit=model.unit,
        reference_range_low=model.reference_range_low,
        reference_range_high=model.reference_range_high,
        effective_at=model.effective_at,
        recorded_at=model.recorded_at,
        version=model.version,
    )


def _lab_order_view(model: LaboratoryOrderModel) -> LaboratoryOrderView:
    return LaboratoryOrderView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        status=LaboratoryOrderStatus(model.status),
        ordered_at=model.ordered_at,
        version=model.version,
    )


def _lab_specimen_view(model: LaboratorySpecimenModel) -> LaboratorySpecimenView:
    return LaboratorySpecimenView(
        id=model.id,
        laboratory_order_id=model.laboratory_order_id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        specimen_type=LaboratorySpecimenType(model.specimen_type),
        status=LaboratorySpecimenStatus(model.status),
        collected_at=model.collected_at,
    )


def _lab_result_value_from_model(model: LaboratoryResultModel) -> LaboratoryResultValue:
    coded = None
    if model.value_code_system and model.value_code:
        coded = CodeableConcept(
            system=model.value_code_system,
            code=model.value_code,
            display=model.value_code_display,
        )
    return LaboratoryResultValue(
        value_type=ObservationValueType(model.value_type),
        numeric=model.value_numeric,
        text=model.value_text,
        boolean=model.value_boolean,
        coded=coded,
        unit=model.unit,
        range_low=model.reference_range_low,
        range_high=model.reference_range_high,
    )


def _apply_lab_result_value(model: LaboratoryResultModel, value: LaboratoryResultValue) -> None:
    model.value_type = value.value_type.value
    model.value_numeric = value.numeric
    model.value_text = value.text
    model.value_boolean = value.boolean
    model.value_code_system = None if value.coded is None else value.coded.system
    model.value_code = None if value.coded is None else value.coded.code
    model.value_code_display = None if value.coded is None else value.coded.display
    model.unit = value.unit
    model.reference_range_low = value.range_low
    model.reference_range_high = value.range_high


def _lab_result_view(model: LaboratoryResultModel) -> LaboratoryResultView:
    coded = None
    if model.value_code_system and model.value_code:
        coded = CodeableConcept(
            system=model.value_code_system,
            code=model.value_code,
            display=model.value_code_display,
        )
    interpretation = (
        None
        if model.interpretation is None
        else LaboratoryResultInterpretation(model.interpretation)
    )
    return LaboratoryResultView(
        id=model.id,
        laboratory_order_id=model.laboratory_order_id,
        laboratory_specimen_id=model.laboratory_specimen_id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        status=LaboratoryResultStatus(model.status),
        value_type=LaboratoryResultValueType(model.value_type),
        value_numeric=model.value_numeric,
        value_text=model.value_text,
        value_boolean=model.value_boolean,
        value_coded=coded,
        unit=model.unit,
        reference_range_low=model.reference_range_low,
        reference_range_high=model.reference_range_high,
        interpretation=interpretation,
        effective_at=model.effective_at,
        recorded_at=model.recorded_at,
        version=model.version,
    )


def _parse_medication_dose(
    dose_numeric: Decimal | None,
    dose_unit: str | None,
) -> tuple[Decimal | None, str | None]:
    unit = None if dose_unit is None else dose_unit.strip()
    if unit == "":
        unit = None
    if dose_numeric is None and unit is None:
        return None, None
    if dose_numeric is None or unit is None:
        raise AppError(
            "medication_dose_shape",
            "Medication dose requires both dose_numeric and dose_unit, or neither",
            status_code=422,
        )
    return dose_numeric, unit


def _medication_view(model: MedicationModel) -> MedicationView:
    return MedicationView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=MedicationCategory(model.category),
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        status=MedicationStatus(model.status),
        dose_numeric=model.dose_numeric,
        dose_unit=model.dose_unit,
        route=None if model.route is None else MedicationRoute(model.route),
        started_at=model.started_at,
        stopped_at=model.stopped_at,
        recorded_at=model.recorded_at,
        version=model.version,
    )


def _parse_optional_reaction(
    reaction: CodeableConcept | None,
) -> tuple[str | None, str | None, str | None]:
    if reaction is None:
        return None, None, None
    system = reaction.system.strip()
    code = reaction.code.strip()
    if system == "" or code == "":
        raise AppError(
            "allergy_reaction_shape",
            "Allergy reaction requires both system and code, or neither",
            status_code=422,
        )
    display = None if reaction.display is None else reaction.display.strip()
    if display == "":
        display = None
    return system, code, display


def _allergy_view(model: AllergyModel) -> AllergyView:
    reaction = None
    if model.reaction_code_system is not None and model.reaction_code is not None:
        reaction = CodeableConcept(
            system=model.reaction_code_system,
            code=model.reaction_code,
            display=model.reaction_display,
        )
    return AllergyView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=AllergyCategory(model.category),
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        status=AllergyStatus(model.status),
        clinical_status=AllergyClinicalStatus(model.clinical_status),
        verification_status=AllergyVerificationStatus(model.verification_status),
        criticality=None if model.criticality is None else AllergyCriticality(model.criticality),
        severity=None if model.severity is None else AllergySeverity(model.severity),
        reaction=reaction,
        onset_at=model.onset_at,
        recorded_at=model.recorded_at,
        version=model.version,
    )


def _parse_optional_consent_code(
    code: CodeableConcept | None,
) -> tuple[str | None, str | None, str | None]:
    if code is None:
        return None, None, None
    system = code.system.strip()
    value = code.code.strip()
    if system == "" or value == "":
        raise AppError(
            "consent_code_shape",
            "Consent code requires both system and code, or neither",
            status_code=422,
        )
    display = None if code.display is None else code.display.strip()
    if display == "":
        display = None
    return system, value, display


def _consent_view(model: ConsentModel) -> ConsentView:
    coded = None
    if model.code_system is not None and model.code is not None:
        coded = CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        )
    status = ConsentStatus(model.status)
    return ConsentView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=ConsentCategory(model.category),
        scope=ConsentScope(model.scope),
        decision=ConsentDecision(model.decision),
        code=coded,
        source=ConsentSource(model.source),
        period_start=model.period_start,
        period_end=model.period_end,
        note_text=model.note_text,
        status=status,
        recorded_at=model.recorded_at,
        revoked_at=model.revoked_at,
        version=model.version,
        is_effective=consent_is_effective(status, model.period_start, model.period_end, utc_now()),
    )


def _immunization_view(model: ImmunizationModel) -> ImmunizationView:
    return ImmunizationView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=ImmunizationCategory(model.category),
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        occurrence_at=model.occurrence_at,
        route=None if model.route is None else ImmunizationRoute(model.route),
        site=None if model.site is None else ImmunizationSite(model.site),
        note_text=model.note_text,
        status=ImmunizationStatus(model.status),
        recorded_at=model.recorded_at,
        version=model.version,
    )


def _procedure_view(model: ProcedureModel) -> ProcedureView:
    return ProcedureView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=ProcedureCategory(model.category),
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        occurrence_at=model.occurrence_at,
        note_text=model.note_text,
        status=ProcedureStatus(model.status),
        recorded_at=model.recorded_at,
        version=model.version,
    )


def _medical_device_view(model: MedicalDeviceModel) -> MedicalDeviceView:
    return MedicalDeviceView(
        id=model.id,
        patient_identity_id=model.patient_identity_id,
        encounter_id=model.encounter_id,
        organization_id=model.organization_id,
        facility_id=model.facility_id,
        category=MedicalDeviceCategory(model.category),
        code=CodeableConcept(
            system=model.code_system,
            code=model.code,
            display=model.code_display,
        ),
        association_status=MedicalDeviceAssociationStatus(model.association_status),
        occurrence_at=model.occurrence_at,
        note_text=model.note_text,
        status=MedicalDeviceStatus(model.status),
        recorded_at=model.recorded_at,
        version=model.version,
    )
