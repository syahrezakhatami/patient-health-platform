from dataclasses import dataclass
from enum import StrEnum

MANUAL_VITALS_CATALOG_VERSION = "manual-vitals-mvp-v1"
MANUAL_VITALS_FEATURE_ID = "manual_vital_signs_write"
MANUAL_VITALS_FEATURE_VERSION = "1.0.0"

LOINC_SYSTEM = "http://loinc.org"
UCUM_SYSTEM = "http://unitsofmeasure.org"


class VitalMeasurementKey(StrEnum):
    HEART_RATE = "heart_rate"
    RESPIRATORY_RATE = "respiratory_rate"
    BODY_TEMPERATURE = "body_temperature"
    BODY_WEIGHT = "body_weight"
    BODY_HEIGHT = "body_height"


@dataclass(frozen=True, slots=True)
class VitalSignCatalogEntry:
    measurement_key: VitalMeasurementKey
    category: str
    code_system: str
    code: str
    canonical_concept: str
    value_type: str
    unit_system: str
    unit_code: str
    display_unit: str
    catalog_version: str


_CATALOG_ENTRIES: dict[VitalMeasurementKey, VitalSignCatalogEntry] = {
    VitalMeasurementKey.HEART_RATE: VitalSignCatalogEntry(
        measurement_key=VitalMeasurementKey.HEART_RATE,
        category="VITAL_SIGNS",
        code_system=LOINC_SYSTEM,
        code="8867-4",
        canonical_concept="Heart rate",
        value_type="NUMERIC",
        unit_system=UCUM_SYSTEM,
        unit_code="/min",
        display_unit="beats/min",
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
    ),
    VitalMeasurementKey.RESPIRATORY_RATE: VitalSignCatalogEntry(
        measurement_key=VitalMeasurementKey.RESPIRATORY_RATE,
        category="VITAL_SIGNS",
        code_system=LOINC_SYSTEM,
        code="9279-1",
        canonical_concept="Respiratory rate",
        value_type="NUMERIC",
        unit_system=UCUM_SYSTEM,
        unit_code="/min",
        display_unit="breaths/min",
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
    ),
    VitalMeasurementKey.BODY_TEMPERATURE: VitalSignCatalogEntry(
        measurement_key=VitalMeasurementKey.BODY_TEMPERATURE,
        category="VITAL_SIGNS",
        code_system=LOINC_SYSTEM,
        code="8310-5",
        canonical_concept="Body temperature",
        value_type="NUMERIC",
        unit_system=UCUM_SYSTEM,
        unit_code="Cel",
        display_unit="Cel",
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
    ),
    VitalMeasurementKey.BODY_WEIGHT: VitalSignCatalogEntry(
        measurement_key=VitalMeasurementKey.BODY_WEIGHT,
        category="VITAL_SIGNS",
        code_system=LOINC_SYSTEM,
        code="29463-7",
        canonical_concept="Body weight",
        value_type="NUMERIC",
        unit_system=UCUM_SYSTEM,
        unit_code="kg",
        display_unit="kg",
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
    ),
    VitalMeasurementKey.BODY_HEIGHT: VitalSignCatalogEntry(
        measurement_key=VitalMeasurementKey.BODY_HEIGHT,
        category="VITAL_SIGNS",
        code_system=LOINC_SYSTEM,
        code="8302-2",
        canonical_concept="Body height",
        value_type="NUMERIC",
        unit_system=UCUM_SYSTEM,
        unit_code="cm",
        display_unit="cm",
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
    ),
}


def get_catalog_entry(measurement_key: str) -> VitalSignCatalogEntry | None:
    try:
        key = VitalMeasurementKey(measurement_key)
    except ValueError:
        return None
    return _CATALOG_ENTRIES.get(key)


def list_catalog_entries() -> tuple[VitalSignCatalogEntry, ...]:
    return tuple(_CATALOG_ENTRIES[key] for key in VitalMeasurementKey)


def is_known_measurement_key(measurement_key: str) -> bool:
    return get_catalog_entry(measurement_key) is not None


def measurement_key_for_loinc_code(code: str) -> str | None:
    for entry in _CATALOG_ENTRIES.values():
        if entry.code == code:
            return entry.measurement_key.value
    return None
