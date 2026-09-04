import json
import re
from hashlib import sha256
from uuid import UUID

from app.core.errors import AppError

_IDEMPOTENCY_KEY = re.compile(r"^[A-Za-z0-9._-]{8,128}$")


def parse_idempotency_key(raw: str | None) -> str:
    if raw is None or not raw.strip():
        raise AppError(
            "idempotency_key_required",
            "Idempotency-Key is required",
            status_code=422,
        )
    key = raw.strip()
    if _IDEMPOTENCY_KEY.fullmatch(key) is None:
        raise AppError(
            "invalid_idempotency_key",
            "Idempotency-Key is not valid",
            status_code=422,
        )
    return key


def _canonical_fingerprint(payload: dict[str, str]) -> str:
    material = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return sha256(material.encode("utf-8")).hexdigest()


def create_note_fingerprint(
    expected_patient_identity_id: UUID,
    encounter_id: UUID,
    note_type: str,
    body_text: str,
) -> str:
    """Hash stored create semantics. `body_text` must already be the stored (stripped) body."""
    return _canonical_fingerprint(
        {
            "body_sha256": sha256(body_text.encode("utf-8")).hexdigest(),
            "encounter_id": str(encounter_id),
            "expected_patient_identity_id": str(expected_patient_identity_id),
            "note_type": note_type,
        }
    )


def finalize_note_fingerprint(note_id: UUID, expected_patient_identity_id: UUID) -> str:
    return _canonical_fingerprint(
        {
            "expected_patient_identity_id": str(expected_patient_identity_id),
            "note_id": str(note_id),
        }
    )


def manual_vital_create_fingerprint(
    *,
    expected_patient_identity_id: UUID,
    encounter_id: UUID,
    measurement_key: str,
    canonical_value: str,
    effective_at_iso: str,
    provider_catalog_version: str,
) -> str:
    return _canonical_fingerprint(
        {
            "effective_at": effective_at_iso,
            "encounter_id": str(encounter_id),
            "expected_patient_identity_id": str(expected_patient_identity_id),
            "measurement_key": measurement_key,
            "provider_catalog_version": provider_catalog_version,
            "value": canonical_value,
        }
    )
