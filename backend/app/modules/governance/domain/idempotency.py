import json
from datetime import date, datetime
from hashlib import sha256
from uuid import UUID

from app.modules.governance.domain.policy_schema import GovernancePolicyDocumentV1


def canonical_fingerprint(payload: dict[str, str]) -> str:
    material = json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return sha256(material.encode("utf-8")).hexdigest()


def profile_version_create_fingerprint(
    *,
    organization_id: UUID,
    schema_version: int,
    policy_document: GovernancePolicyDocumentV1,
    effective_at: datetime,
    reason: str,
) -> str:
    return canonical_fingerprint(
        {
            "effective_at": effective_at.isoformat(),
            "organization_id": str(organization_id),
            "policy_document": policy_document.model_dump_json(),
            "reason": reason.strip(),
            "schema_version": str(schema_version),
        }
    )


def profile_version_publish_fingerprint(
    *,
    organization_id: UUID,
    profile_version_id: UUID,
) -> str:
    return canonical_fingerprint(
        {
            "organization_id": str(organization_id),
            "profile_version_id": str(profile_version_id),
        }
    )


def approval_evidence_fingerprint(
    *,
    organization_id: UUID,
    feature_id: str,
    provider_feature_version: str,
    approval_type: str,
    scope: str,
    decision_by_name: str,
    approval_date: date,
    artifact_reference: str | None,
    approver_role_category: str | None,
) -> str:
    return canonical_fingerprint(
        {
            "approval_date": approval_date.isoformat(),
            "approval_type": approval_type.strip(),
            "approver_role_category": (approver_role_category or "").strip(),
            "artifact_reference": (artifact_reference or "").strip(),
            "decision_by_name": decision_by_name.strip(),
            "feature_id": feature_id.strip(),
            "organization_id": str(organization_id),
            "provider_feature_version": provider_feature_version.strip(),
            "scope": scope.strip(),
        }
    )
