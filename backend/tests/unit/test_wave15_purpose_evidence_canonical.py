from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.modules.authorization.domain.purpose import Purpose, parse_purpose
from app.modules.mpi.domain.canonical import resolve_canonical_id
from app.modules.mpi.domain.enums import IdentityLifecycle, MatchDecision
from app.modules.mpi.domain.evidence import parse_merge_evidence
from app.modules.mpi.domain.matching import (
    DeterministicMatchingEngine,
    IdentityProbe,
    StoredIdentity,
)

pytestmark = pytest.mark.unit


def test_missing_and_empty_purpose_are_rejected() -> None:
    with pytest.raises(AppError, match="required"):
        parse_purpose(None)
    with pytest.raises(AppError, match="required"):
        parse_purpose("")
    with pytest.raises(AppError, match="required"):
        parse_purpose("   ")


def test_unknown_purpose_is_rejected() -> None:
    with pytest.raises(AppError, match="not an allowed purpose"):
        parse_purpose("billing")
    with pytest.raises(AppError, match="not an allowed purpose"):
        parse_purpose("identity_merge")
    assert parse_purpose("treatment") is Purpose.TREATMENT


def test_purpose_normalization_is_deterministic() -> None:
    assert parse_purpose("registration") is Purpose.REGISTRATION
    assert parse_purpose("IDENTITY-RESOLUTION") is Purpose.IDENTITY_RESOLUTION
    assert parse_purpose(" care coordination ") is Purpose.CARE_COORDINATION
    assert parse_purpose("EMERGENCY") is Purpose.EMERGENCY


def test_merge_evidence_rejects_empty_and_invalid() -> None:
    with pytest.raises(AppError, match="required"):
        parse_merge_evidence([])
    with pytest.raises(AppError, match="required"):
        parse_merge_evidence(None)
    with pytest.raises(AppError, match="not allowed"):
        parse_merge_evidence(
            [
                {
                    "evidence_type": "GUESS",
                    "evidence_source": "staff",
                    "evidence_reference": "x",
                    "reviewer_reason": "reason",
                    "reviewed_at": "2026-08-13T17:00:00+00:00",
                }
            ]
        )
    with pytest.raises(AppError, match="reviewer_reason"):
        parse_merge_evidence(
            [
                {
                    "evidence_type": "STAFF_REVIEW",
                    "evidence_source": "staff",
                    "evidence_reference": "x",
                    "reviewer_reason": "  ",
                    "reviewed_at": "2026-08-13T17:00:00+00:00",
                }
            ]
        )


def test_merge_evidence_rejects_raw_sensitive_keys() -> None:
    with pytest.raises(AppError, match="sensitive"):
        parse_merge_evidence(
            [
                {
                    "evidence_type": "VERIFIED_IDENTIFIER",
                    "evidence_source": "staff",
                    "evidence_reference": "doc-1",
                    "reviewer_reason": "same person",
                    "reviewed_at": "2026-08-13T17:00:00+00:00",
                    "nik": "1234567890123456",
                }
            ]
        )


def test_merge_evidence_accepts_structured_items() -> None:
    items = parse_merge_evidence(
        [
            {
                "evidence_type": "staff_review",
                "evidence_source": "identity-officer",
                "evidence_reference": "MPI-9",
                "reviewer_reason": "Duplicate registration",
                "reviewed_at": "2026-08-13T17:00:00+00:00",
            }
        ]
    )
    assert len(items) == 1
    assert items[0].as_stored()["evidence_type"] == "STAFF_REVIEW"
    assert "nik" not in items[0].as_stored()


def test_canonical_resolution_walks_merge_chain() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    status = {
        a: IdentityLifecycle.MERGED,
        b: IdentityLifecycle.MERGED,
        c: IdentityLifecycle.ACTIVE,
    }
    surviving = {a: b, b: c}
    assert (
        resolve_canonical_id(
            a,
            status_of=status.get,
            surviving_of=surviving.get,
        )
        == c
    )


def test_canonical_resolution_fails_safely_on_cycle_and_broken_link() -> None:
    a, b, missing = uuid4(), uuid4(), uuid4()
    cycle_status = {a: IdentityLifecycle.MERGED, b: IdentityLifecycle.MERGED}
    cycle_surviving = {a: b, b: a}
    assert (
        resolve_canonical_id(
            a,
            status_of=cycle_status.get,
            surviving_of=cycle_surviving.get,
        )
        is None
    )
    broken_status = {a: IdentityLifecycle.MERGED}
    broken_surviving = {a: missing}
    assert (
        resolve_canonical_id(
            a,
            status_of=broken_status.get,
            surviving_of=broken_surviving.get,
        )
        is None
    )
    retired = {a: IdentityLifecycle.RETIRED}
    assert resolve_canonical_id(a, status_of=retired.get, surviving_of=lambda _: None) is None


def test_matcher_skips_merged_and_retired_rows() -> None:
    engine = DeterministicMatchingEngine()
    probe = IdentityProbe(
        identity_id=uuid4(),
        given_name="Ada",
        family_name="Lee",
        name_normalized="ADA LEE",
        birth_date=datetime(1984, 4, 4, tzinfo=UTC).date(),
        identifiers=(),
    )
    merged = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.MERGED,
        name_normalized="ADA LEE",
        birth_date=probe.birth_date,
        identifiers=(),
    )
    retired = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.RETIRED,
        name_normalized="ADA LEE",
        birth_date=probe.birth_date,
        identifiers=(),
    )
    active = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized="ADA LEE",
        birth_date=probe.birth_date,
        identifiers=(),
    )
    results = engine.match(probe, [merged, retired, active])
    assert [item.candidate_patient_id for item in results] == [active.identity_id]
    assert results[0].decision is MatchDecision.POSSIBLE_MATCH
