from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.clinical.domain.enums import (
    AllergyCategory,
    AllergyClinicalStatus,
    AllergyCriticality,
    AllergySeverity,
    AllergyStatus,
    AllergyVerificationStatus,
    ClinicalNoteType,
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
    LaboratoryOrderStatus,
    LaboratoryResultInterpretation,
    LaboratoryResultStatus,
    LaboratoryResultValueType,
    LaboratorySpecimenStatus,
    LaboratorySpecimenType,
    MedicationCategory,
    MedicationRoute,
    MedicationStatus,
    ObservationCategory,
    ObservationStatus,
    ObservationValueType,
)
from app.modules.mpi.domain.enums import (
    AdministrativeSex,
    IdentifierType,
    IdentifierVerificationStatus,
    IdentityKind,
    IdentityLifecycle,
    MatchDecision,
)
from app.modules.organization.domain.enums import FacilityType, OrganizationType


class ProvisionUserRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)


class AssignMembershipRequest(BaseModel):
    user_id: UUID
    organization_id: UUID | None = None
    facility_id: UUID | None = None
    role_code: str = Field(min_length=1, max_length=64)


class CreateOrganizationRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    organization_type: OrganizationType


class CreateFacilityRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    code: str = Field(min_length=1, max_length=64)
    facility_type: FacilityType
    address_text: str | None = Field(default=None, max_length=512)


class OrganizationIdentifierRequest(BaseModel):
    identifier_system: str = Field(min_length=1, max_length=128)
    identifier_value: str = Field(min_length=1, max_length=255)


class IdentifierRequest(BaseModel):
    identifier_system: str = Field(min_length=1, max_length=128)
    identifier_type: IdentifierType
    identifier_value: str = Field(min_length=1, max_length=255)
    organization_id: UUID | None = None
    facility_id: UUID | None = None
    source_system: str | None = Field(default=None, max_length=128)
    source_record_id: str | None = Field(default=None, max_length=128)


class CreateIdentityRequest(BaseModel):
    given_name: str | None = Field(default=None, max_length=255)
    family_name: str | None = Field(default=None, max_length=255)
    birth_date: date | None = None
    administrative_sex: AdministrativeSex | None = None
    identifiers: list[IdentifierRequest] = Field(min_length=1)
    source_system: str | None = Field(default=None, max_length=128)
    source_record_id: str | None = Field(default=None, max_length=128)


class CreateAnonymousIdentityRequest(BaseModel):
    temporary: bool = False
    source_system: str | None = Field(default=None, max_length=128)
    source_record_id: str | None = Field(default=None, max_length=128)


class IdentifyAnonymousRequest(BaseModel):
    given_name: str | None = Field(default=None, max_length=255)
    family_name: str | None = Field(default=None, max_length=255)
    birth_date: date | None = None
    administrative_sex: AdministrativeSex | None = None
    identifiers: list[IdentifierRequest] = Field(default_factory=list)
    reason: str = Field(min_length=1, max_length=512)


class VerifyIdentifierRequest(BaseModel):
    method: str = Field(min_length=1, max_length=64)


class LookupIdentityRequest(BaseModel):
    identifier_system: str = Field(min_length=1, max_length=128)
    identifier_type: IdentifierType
    identifier_value: str = Field(min_length=1, max_length=255)
    identifier_organization_id: UUID | None = None


class MatchRequest(BaseModel):
    identity_id: UUID | None = None
    given_name: str | None = Field(default=None, max_length=255)
    family_name: str | None = Field(default=None, max_length=255)
    birth_date: date | None = None
    identifiers: list[IdentifierRequest] = Field(default_factory=list)


class ReviewMatchRequest(BaseModel):
    decision: MatchDecision
    reason: str = Field(min_length=1, max_length=512)


class MergeEvidenceItemRequest(BaseModel):
    model_config = {"extra": "forbid"}

    evidence_type: str = Field(min_length=1, max_length=64)
    evidence_source: str = Field(min_length=1, max_length=128)
    evidence_reference: str = Field(min_length=1, max_length=255)
    reviewer_reason: str = Field(min_length=1, max_length=512)
    reviewed_at: datetime


class MergeRequest(BaseModel):
    source_identity_id: UUID
    target_identity_id: UUID
    reason: str = Field(min_length=1, max_length=512)
    evidence: list[MergeEvidenceItemRequest] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=128)


class UnmergeRequest(BaseModel):
    merge_operation_id: UUID
    reason: str = Field(min_length=1, max_length=512)
    evidence: list[MergeEvidenceItemRequest] = Field(min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=128)


class IdentifierResponse(BaseModel):
    id: UUID
    identifier_system: str
    identifier_type: IdentifierType
    masked_value: str
    verification_status: IdentifierVerificationStatus
    organization_id: UUID | None
    facility_id: UUID | None


class IdentityResponse(BaseModel):
    id: UUID
    lifecycle_status: IdentityLifecycle
    identity_kind: IdentityKind
    display_label: str
    given_name: str | None
    family_name: str | None
    birth_date: date | None
    administrative_sex: AdministrativeSex | None
    surviving_identity_id: UUID | None
    identifiers: list[IdentifierResponse]


class MatchResultResponse(BaseModel):
    candidate_patient_id: UUID
    score: float
    confidence: str
    decision: MatchDecision
    reasons: list[str]
    evidence: list[str]
    algorithm_version: str


class CodeableConceptRequest(BaseModel):
    system: str = Field(min_length=1, max_length=128)
    code: str = Field(min_length=1, max_length=64)
    display: str | None = Field(default=None, max_length=255)


class CreateEncounterRequest(BaseModel):
    patient_identity_id: UUID
    encounter_class: EncounterClass
    started_at: datetime | None = None
    reason: CodeableConceptRequest | None = None


class ChangeEncounterStatusRequest(BaseModel):
    status: EncounterStatus


class EncounterResponse(BaseModel):
    id: UUID
    patient_identity_id: UUID
    organization_id: UUID
    facility_id: UUID | None
    encounter_class: EncounterClass
    status: EncounterStatus
    display_label: str
    started_at: datetime
    ended_at: datetime | None
    reason: CodeableConceptRequest | None


class CreateClinicalNoteRequest(BaseModel):
    encounter_id: UUID
    note_type: ClinicalNoteType
    body_text: str = Field(min_length=1, max_length=20000)


class UpdateClinicalNoteRequest(BaseModel):
    body_text: str = Field(min_length=1, max_length=20000)


class ClinicalNoteResponse(BaseModel):
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


class CreateConditionRequest(BaseModel):
    patient_identity_id: UUID
    encounter_id: UUID | None = None
    category: ConditionCategory
    code: CodeableConceptRequest
    clinical_status: ConditionClinicalStatus = ConditionClinicalStatus.ACTIVE
    verification_status: ConditionVerificationStatus = ConditionVerificationStatus.CONFIRMED
    onset_at: datetime | None = None
    abatement_at: datetime | None = None


class ChangeConditionStatusRequest(BaseModel):
    clinical_status: ConditionClinicalStatus | None = None
    verification_status: ConditionVerificationStatus | None = None


class ConditionResponse(BaseModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ConditionCategory
    code: CodeableConceptRequest
    clinical_status: ConditionClinicalStatus
    verification_status: ConditionVerificationStatus
    onset_at: datetime | None
    abatement_at: datetime | None
    recorded_at: datetime


class CreateObservationRequest(BaseModel):
    patient_identity_id: UUID
    encounter_id: UUID | None = None
    category: ObservationCategory
    code: CodeableConceptRequest
    value_type: ObservationValueType
    value_numeric: Decimal | None = None
    value_text: str | None = Field(default=None, max_length=2000)
    value_boolean: bool | None = None
    value_coded: CodeableConceptRequest | None = None
    unit: str | None = Field(default=None, max_length=32)
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    effective_at: datetime | None = None


class AmendObservationRequest(BaseModel):
    value_type: ObservationValueType
    value_numeric: Decimal | None = None
    value_text: str | None = Field(default=None, max_length=2000)
    value_boolean: bool | None = None
    value_coded: CodeableConceptRequest | None = None
    unit: str | None = Field(default=None, max_length=32)
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    effective_at: datetime | None = None


class ObservationResponse(BaseModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ObservationCategory
    code: CodeableConceptRequest
    status: ObservationStatus
    value_type: ObservationValueType
    value_numeric: Decimal | None
    value_text: str | None
    value_boolean: bool | None
    value_coded: CodeableConceptRequest | None
    unit: str | None
    reference_range_low: Decimal | None
    reference_range_high: Decimal | None
    effective_at: datetime | None
    recorded_at: datetime
    version: int


class CreateLaboratoryOrderRequest(BaseModel):
    patient_identity_id: UUID
    encounter_id: UUID | None = None
    code: CodeableConceptRequest


class LaboratoryOrderResponse(BaseModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    code: CodeableConceptRequest
    status: LaboratoryOrderStatus
    ordered_at: datetime
    version: int


class CreateLaboratorySpecimenRequest(BaseModel):
    laboratory_order_id: UUID
    specimen_type: LaboratorySpecimenType


class LaboratorySpecimenResponse(BaseModel):
    id: UUID
    laboratory_order_id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    specimen_type: LaboratorySpecimenType
    status: LaboratorySpecimenStatus
    collected_at: datetime


class CreateLaboratoryResultRequest(BaseModel):
    laboratory_specimen_id: UUID
    code: CodeableConceptRequest
    value_type: LaboratoryResultValueType
    value_numeric: Decimal | None = None
    value_text: str | None = Field(default=None, max_length=2000)
    value_boolean: bool | None = None
    value_coded: CodeableConceptRequest | None = None
    unit: str | None = Field(default=None, max_length=32)
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    interpretation: LaboratoryResultInterpretation | None = None
    effective_at: datetime | None = None


class AmendLaboratoryResultRequest(BaseModel):
    value_type: LaboratoryResultValueType
    value_numeric: Decimal | None = None
    value_text: str | None = Field(default=None, max_length=2000)
    value_boolean: bool | None = None
    value_coded: CodeableConceptRequest | None = None
    unit: str | None = Field(default=None, max_length=32)
    reference_range_low: Decimal | None = None
    reference_range_high: Decimal | None = None
    interpretation: LaboratoryResultInterpretation | None = None
    effective_at: datetime | None = None


class LaboratoryResultResponse(BaseModel):
    id: UUID
    laboratory_order_id: UUID
    laboratory_specimen_id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    code: CodeableConceptRequest
    status: LaboratoryResultStatus
    value_type: LaboratoryResultValueType
    value_numeric: Decimal | None
    value_text: str | None
    value_boolean: bool | None
    value_coded: CodeableConceptRequest | None
    unit: str | None
    reference_range_low: Decimal | None
    reference_range_high: Decimal | None
    interpretation: LaboratoryResultInterpretation | None
    effective_at: datetime | None
    recorded_at: datetime
    version: int


class CreateMedicationRequest(BaseModel):
    patient_identity_id: UUID
    encounter_id: UUID | None = None
    category: MedicationCategory
    code: CodeableConceptRequest
    dose_numeric: Decimal | None = None
    dose_unit: str | None = Field(default=None, max_length=32)
    route: MedicationRoute | None = None
    started_at: datetime | None = None


class MedicationResponse(BaseModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: MedicationCategory
    code: CodeableConceptRequest
    status: MedicationStatus
    dose_numeric: Decimal | None
    dose_unit: str | None
    route: MedicationRoute | None
    started_at: datetime | None
    stopped_at: datetime | None
    recorded_at: datetime
    version: int


class CreateAllergyRequest(BaseModel):
    patient_identity_id: UUID
    encounter_id: UUID | None = None
    category: AllergyCategory
    code: CodeableConceptRequest
    clinical_status: AllergyClinicalStatus = AllergyClinicalStatus.ACTIVE
    verification_status: AllergyVerificationStatus = AllergyVerificationStatus.UNCONFIRMED
    criticality: AllergyCriticality | None = None
    severity: AllergySeverity | None = None
    reaction: CodeableConceptRequest | None = None
    onset_at: datetime | None = None


class AmendAllergyRequest(BaseModel):
    clinical_status: AllergyClinicalStatus
    verification_status: AllergyVerificationStatus
    criticality: AllergyCriticality | None = None
    severity: AllergySeverity | None = None
    reaction: CodeableConceptRequest | None = None
    onset_at: datetime | None = None


class AllergyResponse(BaseModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: AllergyCategory
    code: CodeableConceptRequest
    status: AllergyStatus
    clinical_status: AllergyClinicalStatus
    verification_status: AllergyVerificationStatus
    criticality: AllergyCriticality | None
    severity: AllergySeverity | None
    reaction: CodeableConceptRequest | None
    onset_at: datetime | None
    recorded_at: datetime
    version: int


class CreateConsentRequest(BaseModel):
    patient_identity_id: UUID
    encounter_id: UUID | None = None
    category: ConsentCategory
    scope: ConsentScope
    decision: ConsentDecision
    code: CodeableConceptRequest | None = None
    source: ConsentSource
    period_start: datetime | None = None
    period_end: datetime | None = None
    note_text: str | None = Field(default=None, max_length=2000)


class AmendConsentRequest(BaseModel):
    period_start: datetime | None = None
    period_end: datetime | None = None
    note_text: str | None = Field(default=None, max_length=2000)


class ConsentResponse(BaseModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: ConsentCategory
    scope: ConsentScope
    decision: ConsentDecision
    code: CodeableConceptRequest | None
    source: ConsentSource
    period_start: datetime | None
    period_end: datetime | None
    note_text: str | None
    status: ConsentStatus
    recorded_at: datetime
    revoked_at: datetime | None
    version: int
    is_effective: bool


class MergeOperationResponse(BaseModel):
    id: UUID
    source_identity_id: UUID
    target_identity_id: UUID
    operation: str
    status: str
    reason: str
    related_merge_id: UUID | None
