from app.core.errors import AppError
from app.modules.clinical.domain.enums import (
    ClinicalRecordStatus,
    ConditionClinicalStatus,
    ConditionVerificationStatus,
    EncounterStatus,
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
