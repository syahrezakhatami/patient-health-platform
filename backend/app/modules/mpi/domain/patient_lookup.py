from uuid import UUID

from app.modules.mpi.domain.enums import IdentifierSystem, IdentifierType, PatientLookupType

MAX_PATIENT_LOOKUP_RESULTS = 5
PATIENT_LOOKUP_FETCH_LIMIT = MAX_PATIENT_LOOKUP_RESULTS + 1

LOOKUP_TYPE_TO_IDENTIFIER: dict[PatientLookupType, IdentifierType] = {
    PatientLookupType.MRN: IdentifierType.MRN,
    PatientLookupType.NIK: IdentifierType.NIK,
    PatientLookupType.BPJS: IdentifierType.BPJS,
}

CANONICAL_LOOKUP_SYSTEM: dict[PatientLookupType, str] = {
    PatientLookupType.NIK: IdentifierSystem.NIK.value,
    PatientLookupType.BPJS: IdentifierSystem.BPJS.value,
}

NATIONAL_LOOKUP_TYPES: frozenset[PatientLookupType] = frozenset(
    {PatientLookupType.NIK, PatientLookupType.BPJS}
)


def lookup_system_for(lookup_type: PatientLookupType, identifier_type: IdentifierType) -> str:
    if lookup_type in CANONICAL_LOOKUP_SYSTEM:
        return CANONICAL_LOOKUP_SYSTEM[lookup_type]
    return identifier_type.value.lower()


def parse_patient_identity_uuid(raw: str) -> UUID:
    return UUID(raw.strip())
