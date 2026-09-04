import json
from hashlib import sha256

from app.modules.clinical.domain.vital_signs_catalog import MANUAL_VITALS_CATALOG_VERSION


def canonical_approval_payload(
    *,
    catalog_version: str,
    approved_measurements: list[str],
) -> dict[str, object]:
    return {
        "catalog_version": catalog_version,
        "approved_measurements": sorted(set(approved_measurements)),
    }


def canonical_approval_payload_bytes(
    *,
    catalog_version: str,
    approved_measurements: list[str],
) -> bytes:
    payload = canonical_approval_payload(
        catalog_version=catalog_version,
        approved_measurements=approved_measurements,
    )
    material = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return material.encode("utf-8")


def approval_scope_fingerprint(
    *,
    catalog_version: str,
    approved_measurements: list[str],
) -> str:
    digest = sha256(
        canonical_approval_payload_bytes(
            catalog_version=catalog_version,
            approved_measurements=approved_measurements,
        )
    ).hexdigest()
    return f"{catalog_version}#sha256:{digest}"


def default_catalog_version_scope_fingerprint(approved_measurements: list[str]) -> str:
    return approval_scope_fingerprint(
        catalog_version=MANUAL_VITALS_CATALOG_VERSION,
        approved_measurements=approved_measurements,
    )
