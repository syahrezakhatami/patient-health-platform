from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import AppError, NotFoundError
from app.modules.authorization.domain.catalog import Permission
from app.modules.clinical.domain.enums import (
    AdverseEventCategory,
    AdverseEventStatus,
    AllergyCategory,
    AllergyStatus,
    ClinicalRecordStatus,
    ConditionCategory,
    ConditionClinicalStatus,
    ConsentCategory,
    ConsentStatus,
    EncounterClass,
    EncounterStatus,
    FamilyHistoryCategory,
    FamilyHistoryStatus,
    ImmunizationCategory,
    ImmunizationStatus,
    LaboratoryOrderStatus,
    LaboratoryResultStatus,
    LaboratorySpecimenStatus,
    MedicalDeviceCategory,
    MedicalDeviceStatus,
    MedicationCategory,
    MedicationStatus,
    ObservationCategory,
    ObservationStatus,
    ProcedureCategory,
    ProcedureStatus,
)
from app.modules.clinical_read.domain.enums import ChartSection, TimelineSourceType

LAB_READ_PERMISSIONS: tuple[str, ...] = (
    Permission.CLINICAL_LAB_ORDER_READ,
    Permission.CLINICAL_LAB_SPECIMEN_READ,
    Permission.CLINICAL_LAB_RESULT_READ,
)

SECTION_PERMISSIONS: dict[ChartSection, frozenset[str]] = {
    ChartSection.ENCOUNTERS: frozenset({Permission.CLINICAL_ENCOUNTER_READ}),
    ChartSection.NOTES: frozenset({Permission.CLINICAL_NOTE_READ}),
    ChartSection.CONDITIONS: frozenset({Permission.CLINICAL_CONDITION_READ}),
    ChartSection.OBSERVATIONS: frozenset({Permission.CLINICAL_OBSERVATION_READ}),
    ChartSection.LABORATORY: frozenset(LAB_READ_PERMISSIONS),
    ChartSection.MEDICATIONS: frozenset({Permission.CLINICAL_MEDICATION_READ}),
    ChartSection.ALLERGIES: frozenset({Permission.CLINICAL_ALLERGY_READ}),
    ChartSection.CONSENTS: frozenset({Permission.CLINICAL_CONSENT_READ}),
    ChartSection.IMMUNIZATIONS: frozenset({Permission.CLINICAL_IMMUNIZATION_READ}),
    ChartSection.PROCEDURES: frozenset({Permission.CLINICAL_PROCEDURE_READ}),
    ChartSection.MEDICAL_DEVICES: frozenset({Permission.CLINICAL_MEDICAL_DEVICE_READ}),
    ChartSection.ADVERSE_EVENTS: frozenset({Permission.CLINICAL_ADVERSE_EVENT_READ}),
    ChartSection.FAMILY_HISTORIES: frozenset({Permission.CLINICAL_FAMILY_HISTORY_READ}),
}

SECTION_SOURCE_TYPES: dict[ChartSection, tuple[TimelineSourceType, ...]] = {
    ChartSection.ENCOUNTERS: (TimelineSourceType.ENCOUNTER,),
    ChartSection.NOTES: (TimelineSourceType.NOTE,),
    ChartSection.CONDITIONS: (TimelineSourceType.CONDITION,),
    ChartSection.OBSERVATIONS: (TimelineSourceType.OBSERVATION,),
    ChartSection.LABORATORY: (
        TimelineSourceType.LABORATORY_ORDER,
        TimelineSourceType.LABORATORY_SPECIMEN,
        TimelineSourceType.LABORATORY_RESULT,
    ),
    ChartSection.MEDICATIONS: (TimelineSourceType.MEDICATION,),
    ChartSection.ALLERGIES: (TimelineSourceType.ALLERGY,),
    ChartSection.CONSENTS: (TimelineSourceType.CONSENT,),
    ChartSection.IMMUNIZATIONS: (TimelineSourceType.IMMUNIZATION,),
    ChartSection.PROCEDURES: (TimelineSourceType.PROCEDURE,),
    ChartSection.MEDICAL_DEVICES: (TimelineSourceType.MEDICAL_DEVICE,),
    ChartSection.ADVERSE_EVENTS: (TimelineSourceType.ADVERSE_EVENT,),
    ChartSection.FAMILY_HISTORIES: (TimelineSourceType.FAMILY_HISTORY,),
}

SOURCE_PERMISSION: dict[TimelineSourceType, str] = {
    TimelineSourceType.ENCOUNTER: Permission.CLINICAL_ENCOUNTER_READ,
    TimelineSourceType.NOTE: Permission.CLINICAL_NOTE_READ,
    TimelineSourceType.CONDITION: Permission.CLINICAL_CONDITION_READ,
    TimelineSourceType.OBSERVATION: Permission.CLINICAL_OBSERVATION_READ,
    TimelineSourceType.LABORATORY_ORDER: Permission.CLINICAL_LAB_ORDER_READ,
    TimelineSourceType.LABORATORY_SPECIMEN: Permission.CLINICAL_LAB_SPECIMEN_READ,
    TimelineSourceType.LABORATORY_RESULT: Permission.CLINICAL_LAB_RESULT_READ,
    TimelineSourceType.MEDICATION: Permission.CLINICAL_MEDICATION_READ,
    TimelineSourceType.ALLERGY: Permission.CLINICAL_ALLERGY_READ,
    TimelineSourceType.CONSENT: Permission.CLINICAL_CONSENT_READ,
    TimelineSourceType.IMMUNIZATION: Permission.CLINICAL_IMMUNIZATION_READ,
    TimelineSourceType.PROCEDURE: Permission.CLINICAL_PROCEDURE_READ,
    TimelineSourceType.MEDICAL_DEVICE: Permission.CLINICAL_MEDICAL_DEVICE_READ,
    TimelineSourceType.ADVERSE_EVENT: Permission.CLINICAL_ADVERSE_EVENT_READ,
    TimelineSourceType.FAMILY_HISTORY: Permission.CLINICAL_FAMILY_HISTORY_READ,
}


@dataclass(frozen=True, slots=True)
class TimestampMap:
    primary: str
    fallback: str | None


TIMESTAMP_MAP: dict[TimelineSourceType, TimestampMap] = {
    TimelineSourceType.ENCOUNTER: TimestampMap("started_at", None),
    TimelineSourceType.NOTE: TimestampMap("authored_at", None),
    TimelineSourceType.CONDITION: TimestampMap("onset_at", "recorded_at"),
    TimelineSourceType.OBSERVATION: TimestampMap("effective_at", "recorded_at"),
    TimelineSourceType.LABORATORY_ORDER: TimestampMap("ordered_at", None),
    TimelineSourceType.LABORATORY_SPECIMEN: TimestampMap("collected_at", None),
    TimelineSourceType.LABORATORY_RESULT: TimestampMap("effective_at", "recorded_at"),
    TimelineSourceType.MEDICATION: TimestampMap("started_at", "recorded_at"),
    TimelineSourceType.ALLERGY: TimestampMap("onset_at", "recorded_at"),
    TimelineSourceType.CONSENT: TimestampMap("period_start", "recorded_at"),
    TimelineSourceType.IMMUNIZATION: TimestampMap("occurrence_at", "recorded_at"),
    TimelineSourceType.PROCEDURE: TimestampMap("occurrence_at", "recorded_at"),
    TimelineSourceType.MEDICAL_DEVICE: TimestampMap("occurrence_at", "recorded_at"),
    TimelineSourceType.ADVERSE_EVENT: TimestampMap("occurrence_at", "recorded_at"),
    TimelineSourceType.FAMILY_HISTORY: TimestampMap("occurrence_at", "recorded_at"),
}

SUMMARY_CONDITION_LIMIT = 10
SUMMARY_MEDICATION_LIMIT = 10
SUMMARY_ALLERGY_LIMIT = 10
SUMMARY_VITAL_LIMIT = 5
SUMMARY_LAB_LIMIT = 5
SUMMARY_PROCEDURE_LIMIT = 5

ACTIVE_CONDITION_STATUSES = frozenset({"ACTIVE", "RECURRENCE", "RELAPSE"})
ENTERED_IN_ERROR = "ENTERED_IN_ERROR"


def actor_can_read_section(scopes: frozenset[str], section: ChartSection) -> bool:
    required = SECTION_PERMISSIONS[section]
    if section is ChartSection.LABORATORY:
        return any(permission in scopes for permission in required)
    permission = next(iter(required))
    return permission in scopes


def authorized_sections(scopes: frozenset[str]) -> tuple[ChartSection, ...]:
    return tuple(section for section in ChartSection if actor_can_read_section(scopes, section))


def section_authorize_action(scopes: frozenset[str], section: ChartSection) -> str:
    """Permission passed to authorize() for a direct section GET."""
    if section is ChartSection.LABORATORY:
        for permission in LAB_READ_PERMISSIONS:
            if permission in scopes:
                return permission
        return Permission.CLINICAL_LAB_ORDER_READ
    return next(iter(SECTION_PERMISSIONS[section]))


def parse_section(raw: str) -> ChartSection:
    try:
        return ChartSection(raw)
    except ValueError as exc:
        raise NotFoundError("Resource not found") from exc


def occurred_at_value(primary: object, fallback: object) -> object:
    return primary if primary is not None else fallback


SECTION_STATUS_ENUM: dict[ChartSection, type[StrEnum]] = {
    ChartSection.ENCOUNTERS: EncounterStatus,
    ChartSection.NOTES: ClinicalRecordStatus,
    ChartSection.CONDITIONS: ConditionClinicalStatus,
    ChartSection.OBSERVATIONS: ObservationStatus,
    ChartSection.MEDICATIONS: MedicationStatus,
    ChartSection.ALLERGIES: AllergyStatus,
    ChartSection.CONSENTS: ConsentStatus,
    ChartSection.IMMUNIZATIONS: ImmunizationStatus,
    ChartSection.PROCEDURES: ProcedureStatus,
    ChartSection.MEDICAL_DEVICES: MedicalDeviceStatus,
    ChartSection.ADVERSE_EVENTS: AdverseEventStatus,
    ChartSection.FAMILY_HISTORIES: FamilyHistoryStatus,
}

SECTION_CATEGORY_ENUM: dict[ChartSection, type[StrEnum] | None] = {
    ChartSection.ENCOUNTERS: EncounterClass,
    ChartSection.NOTES: None,
    ChartSection.CONDITIONS: ConditionCategory,
    ChartSection.OBSERVATIONS: ObservationCategory,
    ChartSection.LABORATORY: None,
    ChartSection.MEDICATIONS: MedicationCategory,
    ChartSection.ALLERGIES: AllergyCategory,
    ChartSection.CONSENTS: ConsentCategory,
    ChartSection.IMMUNIZATIONS: ImmunizationCategory,
    ChartSection.PROCEDURES: ProcedureCategory,
    ChartSection.MEDICAL_DEVICES: MedicalDeviceCategory,
    ChartSection.ADVERSE_EVENTS: AdverseEventCategory,
    ChartSection.FAMILY_HISTORIES: FamilyHistoryCategory,
}


def _laboratory_status_enum(scopes: frozenset[str]) -> type[StrEnum]:
    if Permission.CLINICAL_LAB_ORDER_READ in scopes:
        return LaboratoryOrderStatus
    if Permission.CLINICAL_LAB_SPECIMEN_READ in scopes:
        return LaboratorySpecimenStatus
    return LaboratoryResultStatus


def _require_enum(enum_cls: type[StrEnum], raw: str, *, code: str, message: str) -> None:
    try:
        enum_cls(raw)
    except ValueError as exc:
        raise AppError(code, message, status_code=422) from exc


def validate_section_filters(
    section: ChartSection,
    *,
    status: str | None,
    category: str | None,
    scopes: frozenset[str],
) -> None:
    """Reject unknown status/category with 422. Closed frozen domain enums only."""
    if status is not None:
        if section is ChartSection.LABORATORY:
            status_enum = _laboratory_status_enum(scopes)
        else:
            status_enum = SECTION_STATUS_ENUM[section]
        _require_enum(
            status_enum,
            status,
            code="invalid_status",
            message="status is not valid for this section",
        )
    if category is not None:
        category_enum = SECTION_CATEGORY_ENUM[section]
        if category_enum is None:
            raise AppError(
                "invalid_category",
                "category is not valid for this section",
                status_code=422,
            )
        _require_enum(
            category_enum,
            category,
            code="invalid_category",
            message="category is not valid for this section",
        )
