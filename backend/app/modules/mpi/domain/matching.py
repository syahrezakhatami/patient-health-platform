from dataclasses import dataclass
from datetime import date
from uuid import UUID

from app.modules.mpi.domain.enums import (
    IdentifierType,
    IdentifierVerificationStatus,
    IdentityLifecycle,
    MatchDecision,
)
from app.modules.mpi.domain.identifiers import is_global_identifier

ALGORITHM_VERSION = "deterministic-v1"


@dataclass(frozen=True, slots=True)
class IdentifierProbe:
    identifier_system: str
    identifier_type: IdentifierType
    normalized_value: str
    organization_id: UUID | None
    verification_status: IdentifierVerificationStatus = IdentifierVerificationStatus.UNVERIFIED


@dataclass(frozen=True, slots=True)
class IdentityProbe:
    identity_id: UUID | None
    given_name: str | None
    family_name: str | None
    name_normalized: str | None
    birth_date: date | None
    identifiers: tuple[IdentifierProbe, ...]


@dataclass(frozen=True, slots=True)
class StoredIdentity:
    identity_id: UUID
    lifecycle_status: IdentityLifecycle
    name_normalized: str | None
    birth_date: date | None
    identifiers: tuple[IdentifierProbe, ...]


@dataclass(frozen=True, slots=True)
class MatchResult:
    candidate_patient_id: UUID
    score: float
    confidence: str
    decision: MatchDecision
    reasons: tuple[str, ...]
    evidence: tuple[str, ...]
    algorithm_version: str = ALGORITHM_VERSION


class DeterministicMatchingEngine:
    """Rule-based matcher. Score is evidence, never automatic truth."""

    def match(self, probe: IdentityProbe, candidates: list[StoredIdentity]) -> list[MatchResult]:
        results: list[MatchResult] = []
        for candidate in candidates:
            if probe.identity_id is not None and candidate.identity_id == probe.identity_id:
                continue
            if candidate.lifecycle_status in {
                IdentityLifecycle.RETIRED,
                IdentityLifecycle.MERGED,
            }:
                continue
            result = self._compare(probe, candidate)
            if result is not None:
                results.append(result)
        return results

    def _compare(self, probe: IdentityProbe, candidate: StoredIdentity) -> MatchResult | None:
        verified_conflicts = _verified_identifier_conflicts(
            probe.identifiers,
            candidate.identifiers,
        )
        if verified_conflicts:
            return MatchResult(
                candidate_patient_id=candidate.identity_id,
                score=0.0,
                confidence="high",
                decision=MatchDecision.NO_MATCH,
                reasons=("verified_identifier_conflict",),
                evidence=verified_conflicts,
            )

        trusted_hits = _trusted_identifier_hits(probe.identifiers, candidate.identifiers)
        if trusted_hits:
            return MatchResult(
                candidate_patient_id=candidate.identity_id,
                score=1.0,
                confidence="high",
                decision=MatchDecision.CONFIRMED_MATCH,
                reasons=("trusted_verified_identifier",),
                evidence=trusted_hits,
            )

        unverified_hits = _unverified_identifier_hits(probe.identifiers, candidate.identifiers)
        demographic = _demographic_overlap(probe, candidate)
        if unverified_hits and demographic:
            return MatchResult(
                candidate_patient_id=candidate.identity_id,
                score=0.55,
                confidence="medium",
                decision=MatchDecision.REQUIRES_REVIEW,
                reasons=("unverified_identifier_and_demographics",),
                evidence=unverified_hits + demographic,
            )
        if unverified_hits:
            return MatchResult(
                candidate_patient_id=candidate.identity_id,
                score=0.5,
                confidence="medium",
                decision=MatchDecision.REQUIRES_REVIEW,
                reasons=("unverified_identifier_overlap",),
                evidence=unverified_hits,
            )
        if demographic:
            return MatchResult(
                candidate_patient_id=candidate.identity_id,
                score=0.4,
                confidence="low",
                decision=MatchDecision.POSSIBLE_MATCH,
                reasons=("name_and_birth_date_overlap", "insufficient_trusted_identifier"),
                evidence=demographic,
            )
        return None


def _same_scope(left: IdentifierProbe, right: IdentifierProbe) -> bool:
    if left.identifier_system != right.identifier_system:
        return False
    if left.identifier_type != right.identifier_type:
        return False
    if is_global_identifier(left.identifier_type):
        return True
    return left.organization_id is not None and left.organization_id == right.organization_id


def _trusted_identifier_hits(
    probe_ids: tuple[IdentifierProbe, ...],
    candidate_ids: tuple[IdentifierProbe, ...],
) -> tuple[str, ...]:
    hits: list[str] = []
    for probe in probe_ids:
        for stored in candidate_ids:
            if not _same_scope(probe, stored):
                continue
            if probe.normalized_value != stored.normalized_value:
                continue
            if stored.verification_status is IdentifierVerificationStatus.VERIFIED:
                hits.append(f"{probe.identifier_system}:verified")
    return tuple(hits)


def _unverified_identifier_hits(
    probe_ids: tuple[IdentifierProbe, ...],
    candidate_ids: tuple[IdentifierProbe, ...],
) -> tuple[str, ...]:
    hits: list[str] = []
    for probe in probe_ids:
        for stored in candidate_ids:
            if not _same_scope(probe, stored):
                continue
            if probe.normalized_value != stored.normalized_value:
                continue
            if (
                probe.verification_status is IdentifierVerificationStatus.VERIFIED
                and stored.verification_status is IdentifierVerificationStatus.VERIFIED
            ):
                continue
            if IdentifierVerificationStatus.REJECTED in {
                probe.verification_status,
                stored.verification_status,
            }:
                continue
            hits.append(f"{probe.identifier_system}:unverified")
    return tuple(hits)


def _verified_identifier_conflicts(
    probe_ids: tuple[IdentifierProbe, ...],
    candidate_ids: tuple[IdentifierProbe, ...],
) -> tuple[str, ...]:
    conflicts: list[str] = []
    for probe in probe_ids:
        if probe.verification_status is not IdentifierVerificationStatus.VERIFIED:
            continue
        for stored in candidate_ids:
            if stored.verification_status is not IdentifierVerificationStatus.VERIFIED:
                continue
            if not _same_scope(probe, stored):
                continue
            if probe.normalized_value != stored.normalized_value:
                conflicts.append(f"{probe.identifier_system}:distinct_verified_values")
    return tuple(conflicts)


def _demographic_overlap(probe: IdentityProbe, candidate: StoredIdentity) -> tuple[str, ...]:
    if not probe.name_normalized or not candidate.name_normalized:
        return ()
    if not probe.birth_date or not candidate.birth_date:
        return ()
    if (
        probe.name_normalized == candidate.name_normalized
        and probe.birth_date == candidate.birth_date
    ):
        return ("normalized_name", "birth_date")
    return ()
