from enum import StrEnum


class AuthorshipKind(StrEnum):
    NATIVE = "NATIVE"
    IMPORTED = "IMPORTED"


class InformationSource(StrEnum):
    CLINICIAN = "CLINICIAN"
    PATIENT_REPORTED = "PATIENT_REPORTED"
    DEVICE = "DEVICE"
    EXTERNAL_SYSTEM = "EXTERNAL_SYSTEM"


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    CONFIRMED = "CONFIRMED"
    REFUTED = "REFUTED"
    ENTERED_IN_ERROR = "ENTERED_IN_ERROR"


class PrincipalType(StrEnum):
    PATIENT = "PATIENT"
    PRACTITIONER = "PRACTITIONER"
    STAFF = "STAFF"
    AUDITOR = "AUDITOR"
    SYSTEM = "SYSTEM"
    AI_SERVICE = "AI_SERVICE"


class AuditResult(StrEnum):
    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    ERROR = "ERROR"


class ClinicalConflictStatus(StrEnum):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"
    SUPERSEDED = "SUPERSEDED"


class DisclosureCategory(StrEnum):
    PATIENT_VISIBLE = "patient_visible"
    CLINICIAN_VISIBLE = "clinician_visible"
    ORGANIZATION_VISIBLE = "organization_visible"
    RESTRICTED = "restricted"
    LEGALLY_RESTRICTED = "legally_restricted"
