from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from pydantic import BaseModel

from app.modules.clinical.infrastructure.models import (
    AdverseEventModel,
    AllergyModel,
    ClinicalNoteModel,
    ConditionModel,
    ConsentModel,
    EncounterModel,
    FamilyHistoryModel,
    ImmunizationModel,
    LaboratoryOrderModel,
    LaboratoryResultModel,
    LaboratorySpecimenModel,
    MedicalDeviceModel,
    MedicationModel,
    ObservationModel,
    ProcedureModel,
)
from app.modules.clinical_read.application.schemas import (
    AdverseEventReadDTO,
    AllergyReadDTO,
    ConditionReadDTO,
    ConsentReadDTO,
    EncounterReadDTO,
    FamilyHistoryReadDTO,
    ImmunizationReadDTO,
    LaboratoryOrderReadDTO,
    LaboratoryResultReadDTO,
    LaboratorySpecimenReadDTO,
    MedicalDeviceReadDTO,
    MedicationReadDTO,
    NoteListDTO,
    ObservationReadDTO,
    ProcedureReadDTO,
    SelectedEncounterDTO,
    SummaryItemDTO,
    TimelineItemDTO,
)
from app.modules.clinical_read.domain.catalog import TIMESTAMP_MAP, occurred_at_value
from app.modules.clinical_read.domain.enums import TimelineSourceType


class _TimelineRow(Protocol):
    id: UUID
    organization_id: UUID
    patient_identity_id: UUID


def selected_encounter_dto(row: EncounterModel) -> SelectedEncounterDTO:
    return SelectedEncounterDTO(
        id=row.id,
        status=row.status,
        encounter_class=row.encounter_class,
        display_label=row.display_label,
        started_at=row.started_at,
        ended_at=row.ended_at,
        facility_id=row.facility_id,
    )


def encounter_dto(row: EncounterModel) -> EncounterReadDTO:
    return EncounterReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        encounter_class=row.encounter_class,
        status=row.status,
        display_label=row.display_label,
        started_at=row.started_at,
        ended_at=row.ended_at,
        reason_system=row.reason_system,
        reason_code=row.reason_code,
        reason_display=row.reason_display,
    )


def note_list_dto(row: ClinicalNoteModel) -> NoteListDTO:
    return NoteListDTO(
        id=row.id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        note_type=row.note_type,
        record_status=row.record_status,
        version=row.version,
        authored_at=row.authored_at,
        finalized_at=row.finalized_at,
        author_id=row.author_id,
        patient_identity_id=row.patient_identity_id,
    )


def condition_dto(row: ConditionModel) -> ConditionReadDTO:
    return ConditionReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        clinical_status=row.clinical_status,
        verification_status=row.verification_status,
        onset_at=row.onset_at,
        abatement_at=row.abatement_at,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
    )


def observation_dto(row: ObservationModel) -> ObservationReadDTO:
    return ObservationReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        status=row.status,
        value_type=row.value_type,
        value_numeric=row.value_numeric,
        value_text=row.value_text,
        value_boolean=row.value_boolean,
        value_code_system=row.value_code_system,
        value_code=row.value_code,
        value_code_display=row.value_code_display,
        unit=row.unit,
        effective_at=row.effective_at,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def lab_order_dto(
    row: LaboratoryOrderModel,
    *,
    specimens: list[LaboratorySpecimenModel] | None = None,
    results: list[LaboratoryResultModel] | None = None,
) -> LaboratoryOrderReadDTO:
    return LaboratoryOrderReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        status=row.status,
        ordered_at=row.ordered_at,
        version=row.version,
        specimens=[lab_specimen_dto(item) for item in specimens] if specimens is not None else None,
        results=[lab_result_dto(item) for item in results] if results is not None else None,
    )


def lab_specimen_dto(row: LaboratorySpecimenModel) -> LaboratorySpecimenReadDTO:
    return LaboratorySpecimenReadDTO(
        id=row.id,
        laboratory_order_id=row.laboratory_order_id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        specimen_type=row.specimen_type,
        status=row.status,
        collected_at=row.collected_at,
        recorder_id=row.recorder_id,
    )


def lab_result_dto(row: LaboratoryResultModel) -> LaboratoryResultReadDTO:
    return LaboratoryResultReadDTO(
        id=row.id,
        laboratory_order_id=row.laboratory_order_id,
        laboratory_specimen_id=row.laboratory_specimen_id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        status=row.status,
        value_type=row.value_type,
        value_numeric=row.value_numeric,
        value_text=row.value_text,
        value_boolean=row.value_boolean,
        value_code_system=row.value_code_system,
        value_code=row.value_code,
        value_code_display=row.value_code_display,
        unit=row.unit,
        interpretation=row.interpretation,
        effective_at=row.effective_at,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def medication_dto(row: MedicationModel) -> MedicationReadDTO:
    return MedicationReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        status=row.status,
        dose_numeric=row.dose_numeric,
        dose_unit=row.dose_unit,
        route=row.route,
        started_at=row.started_at,
        stopped_at=row.stopped_at,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def allergy_dto(row: AllergyModel) -> AllergyReadDTO:
    return AllergyReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        status=row.status,
        clinical_status=row.clinical_status,
        verification_status=row.verification_status,
        criticality=row.criticality,
        severity=row.severity,
        onset_at=row.onset_at,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def consent_dto(row: ConsentModel) -> ConsentReadDTO:
    return ConsentReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        scope=row.scope,
        decision=row.decision,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        source=row.source,
        period_start=row.period_start,
        period_end=row.period_end,
        status=row.status,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def immunization_dto(row: ImmunizationModel) -> ImmunizationReadDTO:
    return ImmunizationReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        occurrence_at=row.occurrence_at,
        route=row.route,
        site=row.site,
        status=row.status,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def procedure_dto(row: ProcedureModel) -> ProcedureReadDTO:
    return ProcedureReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        occurrence_at=row.occurrence_at,
        status=row.status,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def medical_device_dto(row: MedicalDeviceModel) -> MedicalDeviceReadDTO:
    return MedicalDeviceReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        association_status=row.association_status,
        occurrence_at=row.occurrence_at,
        status=row.status,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def adverse_event_dto(row: AdverseEventModel) -> AdverseEventReadDTO:
    return AdverseEventReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        severity=row.severity,
        medication_id=row.medication_id,
        medical_device_id=row.medical_device_id,
        procedure_id=row.procedure_id,
        occurrence_at=row.occurrence_at,
        status=row.status,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def family_history_dto(row: FamilyHistoryModel) -> FamilyHistoryReadDTO:
    return FamilyHistoryReadDTO(
        id=row.id,
        patient_identity_id=row.patient_identity_id,
        encounter_id=row.encounter_id,
        organization_id=row.organization_id,
        facility_id=row.facility_id,
        relationship=row.relationship,
        category=row.category,
        code_system=row.code_system,
        code=row.code,
        code_display=row.code_display,
        occurrence_at=row.occurrence_at,
        status=row.status,
        recorded_at=row.recorded_at,
        recorder_id=row.recorder_id,
        version=row.version,
    )


def dump_dto(model: BaseModel) -> dict[str, Any]:
    return model.model_dump(mode="json")


def summary_item(
    *,
    source_type: str,
    source_id: UUID,
    code_system: str | None,
    code: str | None,
    code_display: str | None,
    status: str,
    occurred_at: datetime,
) -> SummaryItemDTO:
    return SummaryItemDTO(
        source_type=source_type,
        source_id=source_id,
        code_system=code_system,
        code=code,
        code_display=code_display,
        status=status,
        occurred_at=occurred_at,
    )


def row_occurred_at(row: object, source_type: TimelineSourceType) -> datetime:
    mapping = TIMESTAMP_MAP[source_type]
    primary = getattr(row, mapping.primary)
    fallback = None if mapping.fallback is None else getattr(row, mapping.fallback)
    value = occurred_at_value(primary, fallback)
    if not isinstance(value, datetime):
        raise TypeError(f"missing timeline timestamp for {source_type}")
    return value


def timeline_item(
    row: _TimelineRow,
    source_type: TimelineSourceType,
    *,
    canonical_patient_identity_id: UUID,
) -> TimelineItemDTO:
    occurred_at = row_occurred_at(row, source_type)
    code_system = getattr(row, "code_system", None)
    code = getattr(row, "code", None)
    code_display = getattr(row, "code_display", None)
    if source_type is TimelineSourceType.ENCOUNTER:
        code_system = getattr(row, "reason_system", None)
        code = getattr(row, "reason_code", None)
        code_display = getattr(row, "reason_display", None) or getattr(row, "display_label", None)
    if source_type is TimelineSourceType.NOTE:
        code = getattr(row, "note_type", None)
        code_display = getattr(row, "note_type", None)
    status = _status_for_timeline(row, source_type)
    encounter_id = (
        row.id
        if source_type is TimelineSourceType.ENCOUNTER
        else getattr(row, "encounter_id", None)
    )
    return TimelineItemDTO(
        source_type=source_type.value,
        source_id=row.id,
        occurred_at=occurred_at,
        organization_id=row.organization_id,
        facility_id=getattr(row, "facility_id", None),
        canonical_patient_identity_id=canonical_patient_identity_id,
        source_patient_identity_id=row.patient_identity_id,
        code_system=code_system,
        code=code,
        code_display=code_display,
        status=status,
        encounter_id=encounter_id,
    )


def _status_for_timeline(row: object, source_type: TimelineSourceType) -> str | None:
    if source_type is TimelineSourceType.NOTE:
        return getattr(row, "record_status", None)
    if source_type is TimelineSourceType.CONDITION:
        return getattr(row, "clinical_status", None)
    return getattr(row, "status", None)
