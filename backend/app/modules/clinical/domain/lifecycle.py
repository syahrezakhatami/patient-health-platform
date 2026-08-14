from app.core.errors import AppError
from app.modules.clinical.domain.enums import (
    ClinicalRecordStatus,
    ConditionClinicalStatus,
    ConditionVerificationStatus,
    EncounterStatus,
    LaboratoryOrderStatus,
    LaboratoryResultStatus,
    LaboratorySpecimenStatus,
    MedicationStatus,
    ObservationStatus,
)

ENCOUNTER_TRANSITIONS: dict[EncounterStatus, frozenset[EncounterStatus]] = {
    EncounterStatus.PLANNED: frozenset(
        {
            EncounterStatus.IN_PROGRESS,
            EncounterStatus.CANCELLED,
            EncounterStatus.ENTERED_IN_ERROR,
        }
    ),
    EncounterStatus.IN_PROGRESS: frozenset(
        {
            EncounterStatus.FINISHED,
            EncounterStatus.CANCELLED,
            EncounterStatus.ENTERED_IN_ERROR,
        }
    ),
    EncounterStatus.FINISHED: frozenset({EncounterStatus.ENTERED_IN_ERROR}),
    EncounterStatus.CANCELLED: frozenset({EncounterStatus.ENTERED_IN_ERROR}),
    EncounterStatus.ENTERED_IN_ERROR: frozenset(),
}


def assert_encounter_transition(current: EncounterStatus, target: EncounterStatus) -> None:
    if target not in ENCOUNTER_TRANSITIONS.get(current, frozenset()):
        raise AppError(
            "invalid_encounter_transition",
            f"Encounter cannot transition from {current.value} to {target.value}",
            status_code=409,
        )


def assert_note_is_draft(status: ClinicalRecordStatus) -> None:
    if status is not ClinicalRecordStatus.DRAFT:
        raise AppError(
            "note_not_draft",
            "Only a DRAFT clinical note can be edited",
            status_code=409,
        )


def assert_note_can_finalize(status: ClinicalRecordStatus) -> None:
    if status is not ClinicalRecordStatus.DRAFT:
        raise AppError(
            "note_not_draft",
            "Only a DRAFT clinical note can be finalized",
            status_code=409,
        )


def assert_note_can_mark_error(status: ClinicalRecordStatus) -> None:
    if status is ClinicalRecordStatus.ENTERED_IN_ERROR:
        raise AppError(
            "note_already_entered_in_error",
            "Clinical note is already entered in error",
            status_code=409,
        )


CONDITION_CLINICAL_TRANSITIONS: dict[
    ConditionClinicalStatus, frozenset[ConditionClinicalStatus]
] = {
    ConditionClinicalStatus.ACTIVE: frozenset(
        {
            ConditionClinicalStatus.RECURRENCE,
            ConditionClinicalStatus.RELAPSE,
            ConditionClinicalStatus.INACTIVE,
            ConditionClinicalStatus.REMISSION,
            ConditionClinicalStatus.RESOLVED,
        }
    ),
    ConditionClinicalStatus.RECURRENCE: frozenset(
        {
            ConditionClinicalStatus.ACTIVE,
            ConditionClinicalStatus.REMISSION,
            ConditionClinicalStatus.RESOLVED,
        }
    ),
    ConditionClinicalStatus.RELAPSE: frozenset(
        {
            ConditionClinicalStatus.ACTIVE,
            ConditionClinicalStatus.REMISSION,
            ConditionClinicalStatus.RESOLVED,
        }
    ),
    ConditionClinicalStatus.INACTIVE: frozenset({ConditionClinicalStatus.ACTIVE}),
    ConditionClinicalStatus.REMISSION: frozenset(
        {
            ConditionClinicalStatus.ACTIVE,
            ConditionClinicalStatus.RELAPSE,
            ConditionClinicalStatus.RESOLVED,
        }
    ),
    ConditionClinicalStatus.RESOLVED: frozenset(
        {
            ConditionClinicalStatus.ACTIVE,
            ConditionClinicalStatus.RECURRENCE,
            ConditionClinicalStatus.RELAPSE,
        }
    ),
}

CONDITION_VERIFICATION_TRANSITIONS: dict[
    ConditionVerificationStatus, frozenset[ConditionVerificationStatus]
] = {
    ConditionVerificationStatus.UNCONFIRMED: frozenset(
        {
            ConditionVerificationStatus.PROVISIONAL,
            ConditionVerificationStatus.DIFFERENTIAL,
            ConditionVerificationStatus.CONFIRMED,
            ConditionVerificationStatus.REFUTED,
        }
    ),
    ConditionVerificationStatus.PROVISIONAL: frozenset(
        {
            ConditionVerificationStatus.UNCONFIRMED,
            ConditionVerificationStatus.DIFFERENTIAL,
            ConditionVerificationStatus.CONFIRMED,
            ConditionVerificationStatus.REFUTED,
        }
    ),
    ConditionVerificationStatus.DIFFERENTIAL: frozenset(
        {
            ConditionVerificationStatus.PROVISIONAL,
            ConditionVerificationStatus.CONFIRMED,
            ConditionVerificationStatus.REFUTED,
        }
    ),
    ConditionVerificationStatus.CONFIRMED: frozenset({ConditionVerificationStatus.REFUTED}),
    ConditionVerificationStatus.REFUTED: frozenset(),
    ConditionVerificationStatus.ENTERED_IN_ERROR: frozenset(),
}


def assert_condition_clinical_transition(
    current: ConditionClinicalStatus, target: ConditionClinicalStatus
) -> None:
    if target is current:
        return
    if target not in CONDITION_CLINICAL_TRANSITIONS.get(current, frozenset()):
        raise AppError(
            "invalid_condition_clinical_transition",
            (f"Condition clinical status cannot transition from {current.value} to {target.value}"),
            status_code=409,
        )


def assert_condition_verification_transition(
    current: ConditionVerificationStatus, target: ConditionVerificationStatus
) -> None:
    if target is current:
        return
    if target not in CONDITION_VERIFICATION_TRANSITIONS.get(current, frozenset()):
        raise AppError(
            "invalid_condition_verification_transition",
            (
                "Condition verification status cannot transition from "
                f"{current.value} to {target.value}"
            ),
            status_code=409,
        )


def assert_condition_mutable(status: ConditionVerificationStatus) -> None:
    if status is ConditionVerificationStatus.ENTERED_IN_ERROR:
        raise AppError(
            "condition_entered_in_error",
            "An entered-in-error condition is immutable",
            status_code=409,
        )


OBSERVATION_TRANSITIONS: dict[ObservationStatus, frozenset[ObservationStatus]] = {
    ObservationStatus.FINAL: frozenset(
        {ObservationStatus.AMENDED, ObservationStatus.ENTERED_IN_ERROR}
    ),
    ObservationStatus.AMENDED: frozenset({ObservationStatus.ENTERED_IN_ERROR}),
    ObservationStatus.ENTERED_IN_ERROR: frozenset(),
}


def assert_observation_mutable(status: ObservationStatus) -> None:
    if status is ObservationStatus.ENTERED_IN_ERROR:
        raise AppError(
            "observation_entered_in_error",
            "An entered-in-error observation is immutable",
            status_code=409,
        )


def assert_observation_can_amend(status: ObservationStatus) -> None:
    assert_observation_mutable(status)
    if status not in {ObservationStatus.FINAL, ObservationStatus.AMENDED}:
        raise AppError(
            "observation_not_amendable",
            "Only a FINAL or AMENDED observation can be amended",
            status_code=409,
        )


LAB_ORDER_TRANSITIONS: dict[LaboratoryOrderStatus, frozenset[LaboratoryOrderStatus]] = {
    LaboratoryOrderStatus.REGISTERED: frozenset(
        {
            LaboratoryOrderStatus.IN_PROGRESS,
            LaboratoryOrderStatus.CANCELLED,
            LaboratoryOrderStatus.ENTERED_IN_ERROR,
        }
    ),
    LaboratoryOrderStatus.IN_PROGRESS: frozenset({LaboratoryOrderStatus.ENTERED_IN_ERROR}),
    LaboratoryOrderStatus.CANCELLED: frozenset(),
    LaboratoryOrderStatus.ENTERED_IN_ERROR: frozenset(),
}


LAB_SPECIMEN_TRANSITIONS: dict[LaboratorySpecimenStatus, frozenset[LaboratorySpecimenStatus]] = {
    LaboratorySpecimenStatus.COLLECTED: frozenset(
        {LaboratorySpecimenStatus.REJECTED, LaboratorySpecimenStatus.ENTERED_IN_ERROR}
    ),
    LaboratorySpecimenStatus.REJECTED: frozenset(),
    LaboratorySpecimenStatus.ENTERED_IN_ERROR: frozenset(),
}


LAB_RESULT_TRANSITIONS: dict[LaboratoryResultStatus, frozenset[LaboratoryResultStatus]] = {
    LaboratoryResultStatus.FINAL: frozenset(
        {LaboratoryResultStatus.AMENDED, LaboratoryResultStatus.ENTERED_IN_ERROR}
    ),
    LaboratoryResultStatus.AMENDED: frozenset({LaboratoryResultStatus.ENTERED_IN_ERROR}),
    LaboratoryResultStatus.ENTERED_IN_ERROR: frozenset(),
}


def assert_lab_order_transition(
    current: LaboratoryOrderStatus, target: LaboratoryOrderStatus
) -> None:
    if target not in LAB_ORDER_TRANSITIONS.get(current, frozenset()):
        raise AppError(
            "invalid_lab_order_transition",
            f"Laboratory order cannot transition from {current.value} to {target.value}",
            status_code=409,
        )


def assert_lab_order_open(status: LaboratoryOrderStatus) -> None:
    if status in {LaboratoryOrderStatus.CANCELLED, LaboratoryOrderStatus.ENTERED_IN_ERROR}:
        raise AppError(
            "lab_order_not_open",
            "A cancelled or entered-in-error laboratory order cannot receive specimens",
            status_code=409,
        )


def assert_lab_specimen_transition(
    current: LaboratorySpecimenStatus, target: LaboratorySpecimenStatus
) -> None:
    if target not in LAB_SPECIMEN_TRANSITIONS.get(current, frozenset()):
        raise AppError(
            "invalid_lab_specimen_transition",
            f"Laboratory specimen cannot transition from {current.value} to {target.value}",
            status_code=409,
        )


def assert_lab_specimen_collectable(status: LaboratorySpecimenStatus) -> None:
    if status is not LaboratorySpecimenStatus.COLLECTED:
        raise AppError(
            "lab_specimen_not_collectable",
            "Only a COLLECTED specimen can receive laboratory results",
            status_code=409,
        )


def assert_lab_result_mutable(status: LaboratoryResultStatus) -> None:
    if status is LaboratoryResultStatus.ENTERED_IN_ERROR:
        raise AppError(
            "lab_result_entered_in_error",
            "An entered-in-error laboratory result is immutable",
            status_code=409,
        )


def assert_lab_result_can_amend(status: LaboratoryResultStatus) -> None:
    assert_lab_result_mutable(status)
    if status not in {LaboratoryResultStatus.FINAL, LaboratoryResultStatus.AMENDED}:
        raise AppError(
            "lab_result_not_amendable",
            "Only a FINAL or AMENDED laboratory result can be amended",
            status_code=409,
        )


MEDICATION_TRANSITIONS: dict[MedicationStatus, frozenset[MedicationStatus]] = {
    MedicationStatus.ACTIVE: frozenset(
        {MedicationStatus.STOPPED, MedicationStatus.ENTERED_IN_ERROR}
    ),
    MedicationStatus.STOPPED: frozenset({MedicationStatus.ENTERED_IN_ERROR}),
    MedicationStatus.ENTERED_IN_ERROR: frozenset(),
}


def assert_medication_mutable(status: MedicationStatus) -> None:
    if status is MedicationStatus.ENTERED_IN_ERROR:
        raise AppError(
            "medication_entered_in_error",
            "An entered-in-error medication is immutable",
            status_code=409,
        )


def assert_medication_can_stop(status: MedicationStatus) -> None:
    assert_medication_mutable(status)
    if status is not MedicationStatus.ACTIVE:
        raise AppError(
            "medication_not_active",
            "Only an ACTIVE medication can be stopped",
            status_code=409,
        )
