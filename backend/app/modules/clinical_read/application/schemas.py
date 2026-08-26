from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_serializer

from app.modules.clinical_read.domain.enums import ChartSection


class ClinicalReadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SelectedEncounterDTO(ClinicalReadModel):
    id: UUID
    status: str
    encounter_class: str
    display_label: str
    started_at: datetime
    ended_at: datetime | None
    facility_id: UUID | None


class PatientHeaderDTO(ClinicalReadModel):
    requested_patient_identity_id: UUID
    canonical_patient_identity_id: UUID
    lifecycle_status: str
    identity_kind: str
    display_label: str
    given_name: str | None
    family_name: str | None
    birth_date: date | None
    age_years: int | None
    administrative_sex: str | None
    mrn: list[str]
    selected_encounter: SelectedEncounterDTO | None = None
    documented_allergy_exists: bool | None = None

    @model_serializer(mode="wrap")
    def _omit_unauthorized_optional(self, serializer: Any) -> dict[str, Any]:
        payload = serializer(self)
        if not isinstance(payload, dict):
            raise TypeError("patient header serializer must return a dict")
        data = dict(payload)
        if data.get("documented_allergy_exists") is None:
            data.pop("documented_allergy_exists", None)
        if data.get("selected_encounter") is None:
            data.pop("selected_encounter", None)
        return data


class ChartShellResponse(ClinicalReadModel):
    requested_patient_identity_id: UUID
    canonical_patient_identity_id: UUID
    header: PatientHeaderDTO
    authorized_sections: list[ChartSection]


class SummaryItemDTO(ClinicalReadModel):
    source_type: str
    source_id: UUID
    code_system: str | None = None
    code: str | None = None
    code_display: str | None = None
    status: str
    occurred_at: datetime


class ClinicalSummaryResponse(ClinicalReadModel):
    requested_patient_identity_id: UUID
    canonical_patient_identity_id: UUID
    active_conditions: list[SummaryItemDTO] | None = None
    active_medications: list[SummaryItemDTO] | None = None
    active_allergies: list[SummaryItemDTO] | None = None
    recent_vitals: list[SummaryItemDTO] | None = None
    recent_lab_results: list[SummaryItemDTO] | None = None
    recent_procedures: list[SummaryItemDTO] | None = None


class TimelineItemDTO(ClinicalReadModel):
    source_type: str
    source_id: UUID
    occurred_at: datetime
    organization_id: UUID
    facility_id: UUID | None
    canonical_patient_identity_id: UUID
    source_patient_identity_id: UUID
    code_system: str | None = None
    code: str | None = None
    code_display: str | None = None
    status: str | None = None
    encounter_id: UUID | None = None


class TimelinePageResponse(ClinicalReadModel):
    requested_patient_identity_id: UUID
    canonical_patient_identity_id: UUID
    items: list[TimelineItemDTO]
    has_more: bool
    next_cursor: str | None = None


class EncounterReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    organization_id: UUID
    facility_id: UUID | None
    encounter_class: str
    status: str
    display_label: str
    started_at: datetime
    ended_at: datetime | None
    reason_system: str | None = None
    reason_code: str | None = None
    reason_display: str | None = None


class NoteListDTO(ClinicalReadModel):
    id: UUID
    encounter_id: UUID
    organization_id: UUID
    facility_id: UUID | None
    note_type: str
    record_status: str
    version: int
    authored_at: datetime
    finalized_at: datetime | None
    author_id: UUID | None
    patient_identity_id: UUID


class ConditionReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    clinical_status: str
    verification_status: str
    onset_at: datetime | None
    abatement_at: datetime | None
    recorded_at: datetime
    recorder_id: UUID | None


class ObservationReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    status: str
    value_type: str
    value_numeric: Decimal | None = None
    value_text: str | None = None
    value_boolean: bool | None = None
    value_code_system: str | None = None
    value_code: str | None = None
    value_code_display: str | None = None
    unit: str | None = None
    effective_at: datetime | None
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class LaboratoryOrderReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    code_system: str
    code: str
    code_display: str | None
    status: str
    ordered_at: datetime
    version: int
    specimens: list["LaboratorySpecimenReadDTO"] | None = None
    results: list["LaboratoryResultReadDTO"] | None = None

    @model_serializer(mode="wrap")
    def _omit_unauthorized_lab_layers(self, serializer: Any) -> dict[str, Any]:
        payload = serializer(self)
        if not isinstance(payload, dict):
            raise TypeError("laboratory order serializer must return a dict")
        data = dict(payload)
        if data.get("specimens") is None:
            data.pop("specimens", None)
        if data.get("results") is None:
            data.pop("results", None)
        return data


class LaboratorySpecimenReadDTO(ClinicalReadModel):
    id: UUID
    laboratory_order_id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    specimen_type: str
    status: str
    collected_at: datetime
    recorder_id: UUID | None


class LaboratoryResultReadDTO(ClinicalReadModel):
    id: UUID
    laboratory_order_id: UUID
    laboratory_specimen_id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    code_system: str
    code: str
    code_display: str | None
    status: str
    value_type: str
    value_numeric: Decimal | None = None
    value_text: str | None = None
    value_boolean: bool | None = None
    value_code_system: str | None = None
    value_code: str | None = None
    value_code_display: str | None = None
    unit: str | None = None
    interpretation: str | None = None
    effective_at: datetime | None
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class MedicationReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    status: str
    dose_numeric: Decimal | None = None
    dose_unit: str | None = None
    route: str | None = None
    started_at: datetime | None
    stopped_at: datetime | None
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class AllergyReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    status: str
    clinical_status: str
    verification_status: str
    criticality: str | None = None
    severity: str | None = None
    onset_at: datetime | None
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class ConsentReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    scope: str
    decision: str
    code_system: str | None = None
    code: str | None = None
    code_display: str | None = None
    source: str
    period_start: datetime | None
    period_end: datetime | None
    status: str
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class ImmunizationReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    occurrence_at: datetime | None
    route: str | None = None
    site: str | None = None
    status: str
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class ProcedureReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    occurrence_at: datetime | None
    status: str
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class MedicalDeviceReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    association_status: str
    occurrence_at: datetime | None
    status: str
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class AdverseEventReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    category: str
    code_system: str
    code: str
    code_display: str | None
    severity: str
    medication_id: UUID | None = None
    medical_device_id: UUID | None = None
    procedure_id: UUID | None = None
    occurrence_at: datetime | None
    status: str
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class FamilyHistoryReadDTO(ClinicalReadModel):
    id: UUID
    patient_identity_id: UUID
    encounter_id: UUID | None
    organization_id: UUID
    facility_id: UUID | None
    relationship: str
    category: str
    code_system: str
    code: str
    code_display: str | None
    occurrence_at: datetime | None
    status: str
    recorded_at: datetime
    recorder_id: UUID | None
    version: int


class SectionPageResponse(ClinicalReadModel):
    requested_patient_identity_id: UUID
    canonical_patient_identity_id: UUID
    section: ChartSection
    items: list[dict[str, Any]]
    has_more: bool
    next_cursor: str | None = None


LaboratoryOrderReadDTO.model_rebuild()
