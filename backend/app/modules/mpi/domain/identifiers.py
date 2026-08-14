import re
from dataclasses import dataclass

from app.core.errors import AppError
from app.modules.mpi.domain.enums import IdentifierSystem, IdentifierType

_NON_DIGIT = re.compile(r"\D")
_WHITESPACE = re.compile(r"\s+")
_PASSPORT_KEEP = re.compile(r"[^A-Za-z0-9]")
_NAME_KEEP = re.compile(r"[^A-Za-z0-9 ]")

SENSITIVE_IDENTIFIER_TYPES: frozenset[IdentifierType] = frozenset(
    {
        IdentifierType.NIK,
        IdentifierType.BPJS,
        IdentifierType.PASSPORT,
        IdentifierType.DRIVERS_LICENSE,
        IdentifierType.NATIONAL_ID,
        IdentifierType.PHONE,
        IdentifierType.EMAIL,
    }
)

GLOBAL_IDENTIFIER_TYPES: frozenset[IdentifierType] = frozenset(
    {
        IdentifierType.NIK,
        IdentifierType.BPJS,
        IdentifierType.PASSPORT,
        IdentifierType.DRIVERS_LICENSE,
        IdentifierType.NATIONAL_ID,
        IdentifierType.PHONE,
        IdentifierType.EMAIL,
    }
)

ORG_SCOPED_IDENTIFIER_TYPES: frozenset[IdentifierType] = frozenset(
    {
        IdentifierType.MRN,
        IdentifierType.EXTERNAL,
    }
)


@dataclass(frozen=True, slots=True)
class NormalizedIdentifier:
    raw_value: str
    normalized_value: str
    matching_value: str


def normalize_identifier(
    identifier_system: str,
    identifier_type: IdentifierType,
    raw_value: str,
) -> NormalizedIdentifier:
    if not raw_value or not raw_value.strip():
        raise AppError("invalid_identifier", "Identifier value is required", status_code=422)
    raw = raw_value.strip()
    system = identifier_system.strip()
    if identifier_type is IdentifierType.NIK or system == IdentifierSystem.NIK:
        normalized = _normalize_nik(raw)
    elif identifier_type is IdentifierType.BPJS or system == IdentifierSystem.BPJS:
        normalized = _normalize_bpjs(raw)
    elif identifier_type is IdentifierType.PHONE or system == IdentifierSystem.PHONE:
        normalized = _normalize_phone(raw)
    elif identifier_type is IdentifierType.EMAIL or system == IdentifierSystem.EMAIL:
        normalized = _normalize_email(raw)
    elif identifier_type is IdentifierType.PASSPORT or system.startswith("passport"):
        normalized = _normalize_passport(raw)
    elif identifier_type is IdentifierType.MRN:
        normalized = _normalize_mrn(raw)
    else:
        normalized = _WHITESPACE.sub(" ", raw).strip()
    return NormalizedIdentifier(
        raw_value=raw,
        normalized_value=normalized,
        matching_value=normalized,
    )


def _normalize_nik(raw: str) -> str:
    digits = _NON_DIGIT.sub("", raw)
    if len(digits) != 16:
        raise AppError("invalid_identifier", "NIK must contain 16 digits", status_code=422)
    return digits


def _normalize_bpjs(raw: str) -> str:
    digits = _NON_DIGIT.sub("", raw)
    if len(digits) < 10 or len(digits) > 16:
        raise AppError(
            "invalid_identifier",
            "BPJS identifier has an unexpected length",
            status_code=422,
        )
    return digits


def _normalize_phone(raw: str) -> str:
    compact = raw.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    if compact.startswith("0") and not compact.startswith("00"):
        raise AppError(
            "invalid_identifier",
            "Phone numbers must include a country code",
            status_code=422,
        )
    if compact.startswith("+"):
        digits = _NON_DIGIT.sub("", compact)
        if len(digits) < 8 or len(digits) > 15:
            raise AppError(
                "invalid_identifier",
                "Phone number has an unexpected length",
                status_code=422,
            )
        return "+" + digits
    digits = _NON_DIGIT.sub("", compact)
    if len(digits) < 8 or len(digits) > 15:
        raise AppError(
            "invalid_identifier",
            "Phone number has an unexpected length",
            status_code=422,
        )
    return "+" + digits


def _normalize_email(raw: str) -> str:
    value = raw.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise AppError("invalid_identifier", "Email is not valid", status_code=422)
    return value


def _normalize_passport(raw: str) -> str:
    value = _PASSPORT_KEEP.sub("", raw).upper()
    if len(value) < 5 or len(value) > 16:
        raise AppError(
            "invalid_identifier",
            "Passport number has an unexpected length",
            status_code=422,
        )
    return value


def _normalize_mrn(raw: str) -> str:
    value = _WHITESPACE.sub(" ", raw).strip()
    if not value:
        raise AppError("invalid_identifier", "MRN is required", status_code=422)
    return value


def normalize_person_name(given_name: str | None, family_name: str | None) -> str | None:
    parts = [part for part in (given_name, family_name) if part and part.strip()]
    if not parts:
        return None
    joined = " ".join(parts).upper()
    collapsed = _WHITESPACE.sub(" ", _NAME_KEEP.sub("", joined)).strip()
    return collapsed or None


def mask_identifier(value: str) -> str:
    if not value:
        return ""
    visible = value[-4:] if len(value) > 4 else value
    hidden_len = max(8, len(value) - len(visible))
    return ("*" * hidden_len) + visible


def is_sensitive_identifier(identifier_type: IdentifierType) -> bool:
    return identifier_type in SENSITIVE_IDENTIFIER_TYPES


def requires_organization(identifier_type: IdentifierType) -> bool:
    return identifier_type in ORG_SCOPED_IDENTIFIER_TYPES


def is_global_identifier(identifier_type: IdentifierType) -> bool:
    return identifier_type in GLOBAL_IDENTIFIER_TYPES
