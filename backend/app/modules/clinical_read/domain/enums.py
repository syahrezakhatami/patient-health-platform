from enum import StrEnum


class ChartSection(StrEnum):
    ENCOUNTERS = "encounters"
    NOTES = "notes"
    CONDITIONS = "conditions"
    OBSERVATIONS = "observations"
    LABORATORY = "laboratory"
    MEDICATIONS = "medications"
    ALLERGIES = "allergies"
    CONSENTS = "consents"
    IMMUNIZATIONS = "immunizations"
    PROCEDURES = "procedures"
    MEDICAL_DEVICES = "medical-devices"
    ADVERSE_EVENTS = "adverse-events"
    FAMILY_HISTORIES = "family-histories"


class TimelineSourceType(StrEnum):
    ENCOUNTER = "encounter"
    NOTE = "note"
    CONDITION = "condition"
    OBSERVATION = "observation"
    LABORATORY_ORDER = "laboratory_order"
    LABORATORY_SPECIMEN = "laboratory_specimen"
    LABORATORY_RESULT = "laboratory_result"
    MEDICATION = "medication"
    ALLERGY = "allergy"
    CONSENT = "consent"
    IMMUNIZATION = "immunization"
    PROCEDURE = "procedure"
    MEDICAL_DEVICE = "medical_device"
    ADVERSE_EVENT = "adverse_event"
    FAMILY_HISTORY = "family_history"


class ChartSurface(StrEnum):
    SHELL = "shell"
    SUMMARY = "summary"
    TIMELINE = "timeline"


class ClinicalReadAuditAction(StrEnum):
    CLINICAL_CHART_ACCESSED = "CLINICAL_CHART_ACCESSED"
