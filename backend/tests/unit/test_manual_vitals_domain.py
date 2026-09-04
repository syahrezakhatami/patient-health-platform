from datetime import UTC, datetime, timedelta, timezone

import pytest
from app.core.errors import AppError
from app.modules.clinical.domain.manual_vitals_approval import (
    approval_scope_fingerprint,
    canonical_approval_payload_bytes,
    default_catalog_version_scope_fingerprint,
)
from app.modules.clinical.domain.manual_vitals_decimal import (
    canonical_decimal_fingerprint_text,
    parse_manual_vital_decimal,
)
from app.modules.clinical.domain.vital_signs_catalog import (
    LOINC_SYSTEM,
    MANUAL_VITALS_CATALOG_VERSION,
    UCUM_SYSTEM,
    get_catalog_entry,
    is_known_measurement_key,
    list_catalog_entries,
)
from app.modules.governance.domain.policy_schema import (
    GovernancePolicyDocumentV1,
    GovernancePolicyDocumentV2,
    ManualVitalSignsPolicy,
)
from pydantic import ValidationError


def test_catalog_exact_five_entries() -> None:
    entries = list_catalog_entries()
    assert len(entries) == 5
    keys = {entry.measurement_key.value for entry in entries}
    assert keys == {
        "heart_rate",
        "respiratory_rate",
        "body_temperature",
        "body_weight",
        "body_height",
    }
    assert all(entry.catalog_version == MANUAL_VITALS_CATALOG_VERSION for entry in entries)
    assert get_catalog_entry("8480-6") is None
    assert get_catalog_entry("spo2") is None
    assert is_known_measurement_key("heart_rate") is True
    assert is_known_measurement_key("unknown") is False


def test_catalog_loinc_ucum_exact() -> None:
    heart = get_catalog_entry("heart_rate")
    assert heart is not None
    assert heart.code_system == LOINC_SYSTEM
    assert heart.code == "8867-4"
    assert heart.unit_system == UCUM_SYSTEM
    assert heart.unit_code == "/min"
    assert heart.display_unit == "beats/min"

    resp = get_catalog_entry("respiratory_rate")
    assert resp is not None
    assert resp.code == "9279-1"
    assert resp.display_unit == "breaths/min"

    temp = get_catalog_entry("body_temperature")
    assert temp is not None
    assert temp.code == "8310-5"
    assert temp.unit_code == "Cel"

    weight = get_catalog_entry("body_weight")
    assert weight is not None
    assert weight.code == "29463-7"
    assert weight.unit_code == "kg"

    height = get_catalog_entry("body_height")
    assert height is not None
    assert height.code == "8302-2"
    assert height.unit_code == "cm"


def test_policy_v2_valid_subset() -> None:
    policy = GovernancePolicyDocumentV2(
        manual_vital_signs=ManualVitalSignsPolicy(
            catalog_version=MANUAL_VITALS_CATALOG_VERSION,
            approved_measurements=["heart_rate"],
        )
    )
    assert policy.manual_vital_signs.approved_measurements == ["heart_rate"]


def test_policy_v2_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        ManualVitalSignsPolicy(
            catalog_version=MANUAL_VITALS_CATALOG_VERSION,
            approved_measurements=["heart_rate", "blood_pressure"],
        )


def test_policy_v2_rejects_duplicate_key() -> None:
    with pytest.raises(ValidationError):
        ManualVitalSignsPolicy(
            catalog_version=MANUAL_VITALS_CATALOG_VERSION,
            approved_measurements=["heart_rate", "heart_rate"],
        )


def test_policy_v2_rejects_empty_subset() -> None:
    with pytest.raises(ValidationError):
        ManualVitalSignsPolicy(
            catalog_version=MANUAL_VITALS_CATALOG_VERSION,
            approved_measurements=[],
        )


def test_policy_v2_rejects_wrong_catalog_version() -> None:
    with pytest.raises(ValidationError):
        ManualVitalSignsPolicy(
            catalog_version="manual-vitals-mvp-v2",
            approved_measurements=["heart_rate"],
        )


def test_policy_v2_rejects_extra_field() -> None:
    with pytest.raises(ValidationError):
        GovernancePolicyDocumentV2.model_validate(
            {
                "schema_version": 2,
                "manual_vital_signs": {
                    "catalog_version": MANUAL_VITALS_CATALOG_VERSION,
                    "approved_measurements": ["heart_rate"],
                    "extra": True,
                },
            }
        )


def test_policy_v1_compatibility_without_manual_vitals() -> None:
    policy = GovernancePolicyDocumentV1()
    assert policy.schema_version == 1
    dumped = policy.model_dump(mode="json")
    assert "manual_vital_signs" not in dumped


def test_approval_scope_fingerprint_deterministic() -> None:
    full = [
        "heart_rate",
        "respiratory_rate",
        "body_temperature",
        "body_weight",
        "body_height",
    ]
    scope_a = approval_scope_fingerprint(
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
        approved_measurements=list(reversed(full)),
    )
    scope_b = approval_scope_fingerprint(
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
        approved_measurements=sorted(full),
    )
    assert scope_a == scope_b
    assert scope_a == (
        "manual-vitals-mvp-v1#sha256:"
        "7f034c6ea0c1b6adb3f030aca106d4829eb1fc26528afac207b63e2085819eef"
    )
    assert len(scope_a) <= 128
    subset = default_catalog_version_scope_fingerprint(["heart_rate", "body_temperature"])
    assert subset != scope_a
    other_version = approval_scope_fingerprint(
        catalog_version="other-version",
        approved_measurements=["heart_rate"],
    )
    assert other_version != subset


def test_approval_canonical_payload_bytes() -> None:
    payload = canonical_approval_payload_bytes(
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
        approved_measurements=["body_height", "heart_rate"],
    )
    expected = (
        '{"approved_measurements":["body_height","heart_rate"],'
        '"catalog_version":"manual-vitals-mvp-v1"}'
    )
    assert payload.decode("utf-8") == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1", "1"),
        ("1.0", "1"),
        ("1.00", "1"),
        ("1.0000", "1"),
        ("1.2300", "1.23"),
        ("0.0000", "0"),
    ],
)
def test_decimal_canonical_fingerprint(raw: str, expected: str) -> None:
    value = parse_manual_vital_decimal(raw)
    assert canonical_decimal_fingerprint_text(value) == expected


def test_decimal_rejects_scale_overflow() -> None:
    with pytest.raises(AppError, match="scale"):
        parse_manual_vital_decimal("1.23456")


def test_decimal_rejects_nan_and_infinity() -> None:
    with pytest.raises(AppError):
        parse_manual_vital_decimal("NaN")
    with pytest.raises(AppError):
        parse_manual_vital_decimal("Infinity")


def test_decimal_rejects_precision_overflow() -> None:
    with pytest.raises(AppError, match="precision"):
        parse_manual_vital_decimal("123456789012345")


def test_decimal_accepts_numeric_boundaries() -> None:
    max_positive = parse_manual_vital_decimal("9999999999.9999")
    assert canonical_decimal_fingerprint_text(max_positive) == "9999999999.9999"
    max_negative = parse_manual_vital_decimal("-9999999999.9999")
    assert canonical_decimal_fingerprint_text(max_negative) == "-9999999999.9999"
    assert canonical_decimal_fingerprint_text(parse_manual_vital_decimal("-0.0000")) == "-0"


def test_effective_at_fingerprint_uses_utc_instant() -> None:
    from uuid import uuid4

    from app.modules.clinical.domain.idempotency import manual_vital_create_fingerprint

    patient_id = uuid4()
    encounter_id = uuid4()
    jakarta = datetime(2026, 8, 29, 10, 0, tzinfo=timezone(timedelta(hours=7)))
    utc = jakarta.astimezone(UTC)
    fp_jakarta = manual_vital_create_fingerprint(
        expected_patient_identity_id=patient_id,
        encounter_id=encounter_id,
        measurement_key="heart_rate",
        canonical_value="72",
        effective_at_iso=jakarta.astimezone(UTC).isoformat(),
        provider_catalog_version=MANUAL_VITALS_CATALOG_VERSION,
    )
    fp_utc = manual_vital_create_fingerprint(
        expected_patient_identity_id=patient_id,
        encounter_id=encounter_id,
        measurement_key="heart_rate",
        canonical_value="72",
        effective_at_iso=utc.isoformat(),
        provider_catalog_version=MANUAL_VITALS_CATALOG_VERSION,
    )
    assert fp_jakarta == fp_utc


@pytest.mark.parametrize(
    "measurement_key",
    [
        "heart_rate",
        "respiratory_rate",
        "body_temperature",
        "body_weight",
        "body_height",
    ],
)
def test_approval_scope_for_each_catalog_entry(measurement_key: str) -> None:
    scope = default_catalog_version_scope_fingerprint([measurement_key])
    assert scope.startswith(f"{MANUAL_VITALS_CATALOG_VERSION}#sha256:")
    assert len(scope) <= 128
    assert len(scope.split(":")[-1]) == 64


def test_decimal_rejects_float_input() -> None:
    with pytest.raises(AppError):
        parse_manual_vital_decimal(1.5)
