from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.core.errors import AppError


class MergeEvidenceType(StrEnum):
    VERIFIED_IDENTIFIER = "VERIFIED_IDENTIFIER"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    PATIENT_CONFIRMATION = "PATIENT_CONFIRMATION"
    FACILITY_RECORD = "FACILITY_RECORD"
    STAFF_REVIEW = "STAFF_REVIEW"
    OTHER = "OTHER"


SENSITIVE_EVIDENCE_KEYS = frozenset(
    {"nik", "bpjs", "passport", "phone", "email", "identifier_value", "raw_value"}
)


@dataclass(frozen=True, slots=True)
class MergeEvidenceItem:
    evidence_type: MergeEvidenceType
    evidence_source: str
    evidence_reference: str
    reviewer_reason: str
    reviewed_at: datetime

    def as_stored(self) -> dict[str, str]:
        return {
            "evidence_type": self.evidence_type.value,
            "evidence_source": self.evidence_source,
            "evidence_reference": self.evidence_reference,
            "reviewer_reason": self.reviewer_reason,
            "reviewed_at": self.reviewed_at.isoformat(),
        }


def parse_merge_evidence(items: list[dict[str, str]] | None) -> tuple[MergeEvidenceItem, ...]:
    if not items:
        raise AppError("evidence_required", "Merge evidence is required", status_code=422)
    parsed: list[MergeEvidenceItem] = []
    for item in items:
        _reject_sensitive_payload(item)
        evidence_type_raw = (item.get("evidence_type") or "").strip().upper()
        try:
            evidence_type = MergeEvidenceType(evidence_type_raw)
        except ValueError as exc:
            raise AppError(
                "invalid_evidence_type",
                "Merge evidence_type is not allowed",
                status_code=422,
            ) from exc
        source = (item.get("evidence_source") or "").strip()
        reference = (item.get("evidence_reference") or "").strip()
        reason = (item.get("reviewer_reason") or "").strip()
        reviewed_raw = (item.get("reviewed_at") or "").strip()
        if not source or not reference or not reason or not reviewed_raw:
            raise AppError(
                "invalid_evidence",
                "Each evidence item requires source, reference, reviewer_reason, and reviewed_at",
                status_code=422,
            )
        try:
            reviewed_at = datetime.fromisoformat(reviewed_raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AppError(
                "invalid_evidence",
                "reviewed_at must be an ISO-8601 timestamp",
                status_code=422,
            ) from exc
        parsed.append(
            MergeEvidenceItem(
                evidence_type=evidence_type,
                evidence_source=source,
                evidence_reference=reference,
                reviewer_reason=reason,
                reviewed_at=reviewed_at,
            )
        )
    return tuple(parsed)


def _reject_sensitive_payload(item: dict[str, str]) -> None:
    for key, value in item.items():
        if key.lower() in SENSITIVE_EVIDENCE_KEYS:
            raise AppError(
                "sensitive_evidence_forbidden",
                "Merge evidence must not contain raw sensitive identifiers",
                status_code=422,
            )
        lowered = value.lower() if value else ""
        if "nik=" in lowered or "bpjs=" in lowered:
            raise AppError(
                "sensitive_evidence_forbidden",
                "Merge evidence must not contain raw sensitive identifiers",
                status_code=422,
            )
