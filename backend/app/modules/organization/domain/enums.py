from enum import StrEnum


class OrganizationType(StrEnum):
    HOSPITAL = "HOSPITAL"
    CLINIC = "CLINIC"
    LABORATORY = "LABORATORY"
    PHARMACY = "PHARMACY"
    NETWORK = "NETWORK"
    OTHER = "OTHER"


class OrganizationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class FacilityType(StrEnum):
    HOSPITAL_SITE = "HOSPITAL_SITE"
    CLINIC_SITE = "CLINIC_SITE"
    LABORATORY_SITE = "LABORATORY_SITE"
    EMERGENCY_DEPARTMENT = "EMERGENCY_DEPARTMENT"
    PHARMACY_SITE = "PHARMACY_SITE"
    OTHER = "OTHER"


class FacilityStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
