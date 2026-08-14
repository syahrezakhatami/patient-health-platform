from enum import StrEnum

from app.core.errors import AppError


class Purpose(StrEnum):
    """Purpose-of-use catalog. Purpose is audit context, never an authorization grant."""

    REGISTRATION = "REGISTRATION"
    IDENTITY_RESOLUTION = "IDENTITY_RESOLUTION"
    EMERGENCY = "EMERGENCY"
    CARE_COORDINATION = "CARE_COORDINATION"
    ADMINISTRATION = "ADMINISTRATION"
    PATIENT_ACCESS = "PATIENT_ACCESS"
    AUDIT = "AUDIT"
    SYSTEM_OPERATION = "SYSTEM_OPERATION"
    TREATMENT = "TREATMENT"


def parse_purpose(raw: str | None) -> Purpose:
    if raw is None or not raw.strip():
        raise AppError("purpose_required", "X-Purpose is required", status_code=422)
    normalized = raw.strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return Purpose(normalized)
    except ValueError as exc:
        raise AppError(
            "invalid_purpose",
            "X-Purpose is not an allowed purpose",
            status_code=422,
        ) from exc
