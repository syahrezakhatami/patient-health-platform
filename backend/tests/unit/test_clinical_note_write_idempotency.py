from uuid import UUID, uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.clinical.domain.idempotency import (
    create_note_fingerprint,
    finalize_note_fingerprint,
    parse_idempotency_key,
)

pytestmark = pytest.mark.unit

PATIENT_A = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PATIENT_B = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ENCOUNTER = UUID("11111111-1111-4111-8111-111111111111")


def test_parse_idempotency_key_accepts_opaque_charset() -> None:
    assert parse_idempotency_key("abcd1234") == "abcd1234"
    assert parse_idempotency_key("Note.Key-9_x") == "Note.Key-9_x"
    uuid_key = str(uuid4())
    assert parse_idempotency_key(uuid_key) == uuid_key


def test_parse_idempotency_key_rejects_missing_and_malformed() -> None:
    with pytest.raises(AppError) as missing:
        parse_idempotency_key(None)
    assert missing.value.code == "idempotency_key_required"
    with pytest.raises(AppError) as blank:
        parse_idempotency_key("   ")
    assert blank.value.code == "idempotency_key_required"
    with pytest.raises(AppError) as short:
        parse_idempotency_key("abc")
    assert short.value.code == "invalid_idempotency_key"
    with pytest.raises(AppError) as space:
        parse_idempotency_key("invalid key!")
    assert space.value.code == "invalid_idempotency_key"


def test_create_fingerprint_binds_patient_encounter_type_and_body() -> None:
    first = create_note_fingerprint(PATIENT_A, ENCOUNTER, "PROGRESS", "Nyeri dada")
    second = create_note_fingerprint(PATIENT_A, ENCOUNTER, "PROGRESS", "Nyeri dada")
    other_patient = create_note_fingerprint(PATIENT_B, ENCOUNTER, "PROGRESS", "Nyeri dada")
    other_body = create_note_fingerprint(PATIENT_A, ENCOUNTER, "PROGRESS", "Nyeri dada.")
    other_type = create_note_fingerprint(PATIENT_A, ENCOUNTER, "ED", "Nyeri dada")
    assert first == second
    assert len(first) == 64
    assert first != other_patient
    assert first != other_body
    assert first != other_type
    assert "|" not in first


def test_create_fingerprint_uses_exact_provided_body_bytes() -> None:
    stripped = create_note_fingerprint(PATIENT_A, ENCOUNTER, "PROGRESS", "Assessment")
    padded = create_note_fingerprint(PATIENT_A, ENCOUNTER, "PROGRESS", "  Assessment  ")
    assert stripped != padded


def test_create_fingerprint_is_stable_for_unicode() -> None:
    body = "Nyeri dada. 胸痛评估。é ⚠️"
    first = create_note_fingerprint(PATIENT_A, ENCOUNTER, "PROGRESS", body)
    second = create_note_fingerprint(PATIENT_A, ENCOUNTER, "PROGRESS", body)
    assert first == second


def test_finalize_fingerprint_binds_note_and_expected_patient() -> None:
    note_a = uuid4()
    note_b = uuid4()
    first = finalize_note_fingerprint(note_a, PATIENT_A)
    assert first == finalize_note_fingerprint(note_a, PATIENT_A)
    assert first != finalize_note_fingerprint(note_b, PATIENT_A)
    assert first != finalize_note_fingerprint(note_a, PATIENT_B)
    assert len(first) == 64


def test_body_text_and_idempotency_key_are_redacted_from_log_payloads() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "body_text": "patient reported chest pain",
            "event": "request",
            "headers": {"Idempotency-Key": "abcd1234-key", "X-Purpose": "TREATMENT"},
        },
    )
    assert redacted["body_text"] == "[REDACTED]"
    assert redacted["event"] == "request"
    assert redacted["headers"]["Idempotency-Key"] == "[REDACTED]"
    assert redacted["headers"]["X-Purpose"] == "TREATMENT"
