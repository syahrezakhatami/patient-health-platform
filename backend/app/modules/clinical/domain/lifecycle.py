from app.core.errors import AppError
from app.modules.clinical.domain.enums import ClinicalRecordStatus, EncounterStatus

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
