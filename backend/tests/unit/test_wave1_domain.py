from datetime import date
from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.mpi.domain.enums import (
    IdentifierType,
    IdentifierVerificationStatus,
    IdentityLifecycle,
    MatchDecision,
)
from app.modules.mpi.domain.identifiers import (
    mask_identifier,
    normalize_identifier,
    normalize_person_name,
)
from app.modules.mpi.domain.lifecycle import assert_transition
from app.modules.mpi.domain.matching import (
    DeterministicMatchingEngine,
    IdentifierProbe,
    IdentityProbe,
    StoredIdentity,
)
from app.modules.mpi.domain.merge import MergeValidation, validate_merge, validate_unmerge
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_nik_normalization_strips_formatting_and_preserves_digits() -> None:
    result = normalize_identifier("id.nik", IdentifierType.NIK, "1234-5678-9012-3456")
    assert result.raw_value == "1234-5678-9012-3456"
    assert result.normalized_value == "1234567890123456"
    assert result.matching_value == "1234567890123456"


def test_nik_rejects_wrong_length() -> None:
    with pytest.raises(AppError, match="16 digits"):
        normalize_identifier("id.nik", IdentifierType.NIK, "123")


def test_mrn_is_not_forced_numeric() -> None:
    result = normalize_identifier("hospital-a-mrn", IdentifierType.MRN, "  MRN-00A  ")
    assert result.raw_value == "MRN-00A"
    assert result.normalized_value == "MRN-00A"


def test_email_and_phone_normalization() -> None:
    email = normalize_identifier("email", IdentifierType.EMAIL, "  Ada.Lovelace@Example.COM ")
    assert email.normalized_value == "ada.lovelace@example.com"
    phone = normalize_identifier("phone.e164", IdentifierType.PHONE, "+62 812-3456-7890")
    assert phone.normalized_value == "+6281234567890"


def test_mask_identifier_hides_leading_characters() -> None:
    masked = mask_identifier("1234567890123456")
    assert masked.endswith("3456")
    assert "123456789012" not in masked
    assert set(masked[:-4]) == {"*"}


def test_name_normalization_is_deterministic() -> None:
    assert normalize_person_name("John", "Doe") == normalize_person_name("john", "doe")


def test_lifecycle_rejects_arbitrary_transitions() -> None:
    with pytest.raises(AppError, match="cannot transition"):
        assert_transition(IdentityLifecycle.RETIRED, IdentityLifecycle.ACTIVE)
    assert_transition(IdentityLifecycle.ANONYMOUS, IdentityLifecycle.ACTIVE)
    assert_transition(IdentityLifecycle.ACTIVE, IdentityLifecycle.MERGED)
    assert_transition(IdentityLifecycle.MERGED, IdentityLifecycle.ACTIVE)


def test_same_name_and_dob_without_trusted_id_requires_review() -> None:
    engine = DeterministicMatchingEngine()
    probe = IdentityProbe(
        identity_id=uuid4(),
        given_name="John",
        family_name="Doe",
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(),
    )
    candidate = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(),
    )
    results = engine.match(probe, [candidate])
    assert len(results) == 1
    assert results[0].decision is MatchDecision.POSSIBLE_MATCH
    assert results[0].score < 1.0


def test_different_verified_niks_do_not_match() -> None:
    engine = DeterministicMatchingEngine()
    org = None
    probe = IdentityProbe(
        identity_id=uuid4(),
        given_name="John",
        family_name="Doe",
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(
            IdentifierProbe(
                identifier_system="id.nik",
                identifier_type=IdentifierType.NIK,
                normalized_value="1234567890123456",
                organization_id=org,
                verification_status=IdentifierVerificationStatus.VERIFIED,
            ),
        ),
    )
    candidate = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(
            IdentifierProbe(
                identifier_system="id.nik",
                identifier_type=IdentifierType.NIK,
                normalized_value="6543210987654321",
                organization_id=org,
                verification_status=IdentifierVerificationStatus.VERIFIED,
            ),
        ),
    )
    results = engine.match(probe, [candidate])
    assert results[0].decision is MatchDecision.NO_MATCH


def test_unverified_probe_matches_stored_verified_identifier() -> None:
    engine = DeterministicMatchingEngine()
    probe = IdentityProbe(
        identity_id=None,
        given_name="Jon",
        family_name="Dough",
        name_normalized="JON DOUGH",
        birth_date=date(1990, 1, 1),
        identifiers=(
            IdentifierProbe(
                identifier_system="id.nik",
                identifier_type=IdentifierType.NIK,
                normalized_value="1234567890123456",
                organization_id=None,
                verification_status=IdentifierVerificationStatus.UNVERIFIED,
            ),
        ),
    )
    candidate = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(
            IdentifierProbe(
                identifier_system="id.nik",
                identifier_type=IdentifierType.NIK,
                normalized_value="1234567890123456",
                organization_id=None,
                verification_status=IdentifierVerificationStatus.VERIFIED,
            ),
        ),
    )
    results = engine.match(probe, [candidate])
    assert results[0].decision is MatchDecision.CONFIRMED_MATCH


def test_verified_identifier_matches_despite_name_spelling() -> None:
    engine = DeterministicMatchingEngine()
    probe = IdentityProbe(
        identity_id=uuid4(),
        given_name="Jon",
        family_name="Dough",
        name_normalized="JON DOUGH",
        birth_date=date(1990, 1, 1),
        identifiers=(
            IdentifierProbe(
                identifier_system="id.nik",
                identifier_type=IdentifierType.NIK,
                normalized_value="1234567890123456",
                organization_id=None,
                verification_status=IdentifierVerificationStatus.VERIFIED,
            ),
        ),
    )
    candidate = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(
            IdentifierProbe(
                identifier_system="id.nik",
                identifier_type=IdentifierType.NIK,
                normalized_value="1234567890123456",
                organization_id=None,
                verification_status=IdentifierVerificationStatus.VERIFIED,
            ),
        ),
    )
    results = engine.match(probe, [candidate])
    assert results[0].decision is MatchDecision.CONFIRMED_MATCH


def test_org_scoped_mrn_is_not_globally_unique_for_matching() -> None:
    engine = DeterministicMatchingEngine()
    org_a = uuid4()
    org_b = uuid4()
    probe = IdentityProbe(
        identity_id=uuid4(),
        given_name=None,
        family_name=None,
        name_normalized=None,
        birth_date=None,
        identifiers=(
            IdentifierProbe(
                identifier_system="hospital-a-mrn",
                identifier_type=IdentifierType.MRN,
                normalized_value="1001",
                organization_id=org_a,
                verification_status=IdentifierVerificationStatus.VERIFIED,
            ),
        ),
    )
    candidate = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized=None,
        birth_date=None,
        identifiers=(
            IdentifierProbe(
                identifier_system="hospital-b-mrn",
                identifier_type=IdentifierType.MRN,
                normalized_value="1001",
                organization_id=org_b,
                verification_status=IdentifierVerificationStatus.VERIFIED,
            ),
        ),
    )
    assert engine.match(probe, [candidate]) == []


def test_same_name_different_dob_is_not_a_confirmed_match() -> None:
    engine = DeterministicMatchingEngine()
    probe = IdentityProbe(
        identity_id=uuid4(),
        given_name="John",
        family_name="Doe",
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(),
    )
    candidate = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized="JOHN DOE",
        birth_date=date(1991, 1, 1),
        identifiers=(),
    )
    assert engine.match(probe, [candidate]) == []


def test_missing_dob_does_not_increase_match_confidence() -> None:
    engine = DeterministicMatchingEngine()
    probe = IdentityProbe(
        identity_id=uuid4(),
        given_name="John",
        family_name="Doe",
        name_normalized="JOHN DOE",
        birth_date=None,
        identifiers=(),
    )
    candidate = StoredIdentity(
        identity_id=uuid4(),
        lifecycle_status=IdentityLifecycle.ACTIVE,
        name_normalized="JOHN DOE",
        birth_date=date(1990, 1, 1),
        identifiers=(),
    )
    assert engine.match(probe, [candidate]) == []


def test_merge_rejects_self_merge_and_identifier_conflicts() -> None:
    identity_id = uuid4()
    with pytest.raises(AppError, match="itself"):
        validate_merge(
            MergeValidation(
                source_id=identity_id,
                target_id=identity_id,
                source_status=IdentityLifecycle.ACTIVE,
                target_status=IdentityLifecycle.ACTIVE,
                source_surviving_id=None,
                target_surviving_id=None,
                source_identifiers=(),
                target_identifiers=(),
            )
        )
    with pytest.raises(AppError, match="identifier conflicts"):
        validate_merge(
            MergeValidation(
                source_id=uuid4(),
                target_id=uuid4(),
                source_status=IdentityLifecycle.ACTIVE,
                target_status=IdentityLifecycle.ACTIVE,
                source_surviving_id=None,
                target_surviving_id=None,
                source_identifiers=(
                    IdentifierProbe(
                        identifier_system="id.nik",
                        identifier_type=IdentifierType.NIK,
                        normalized_value="1111111111111111",
                        organization_id=None,
                        verification_status=IdentifierVerificationStatus.VERIFIED,
                    ),
                ),
                target_identifiers=(
                    IdentifierProbe(
                        identifier_system="id.nik",
                        identifier_type=IdentifierType.NIK,
                        normalized_value="2222222222222222",
                        organization_id=None,
                        verification_status=IdentifierVerificationStatus.VERIFIED,
                    ),
                ),
            )
        )


def test_unmerge_requires_merged_state() -> None:
    with pytest.raises(AppError, match="merged identity"):
        validate_unmerge(IdentityLifecycle.ACTIVE, None, uuid4())


def test_wave1_pdp_denies_unknown_actions_and_missing_org_scope() -> None:
    pdp = Wave1PolicyPDP()
    unknown = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=uuid4(),
            facility_id=None,
            roles=("REGISTRAR",),
            scopes=(Permission.MPI_IDENTITY_CREATE,),
            patient_id=None,
            purpose="registration",
            emergency_access_id=None,
            resource_type="AuthContext",
            action="read",
        )
    )
    assert unknown.allowed is False
    assert unknown.reason == "deny_by_default"

    org_a = uuid4()
    org_b = uuid4()
    denied = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_b,
            facility_id=None,
            roles=("REGISTRAR",),
            scopes=(Permission.MPI_IDENTITY_CREATE,),
            patient_id=None,
            purpose="registration",
            emergency_access_id=None,
            resource_type="PatientIdentity",
            action=Permission.MPI_IDENTITY_CREATE,
            actor_organization_ids=(org_a,),
        )
    )
    assert denied.allowed is False
    assert denied.reason == "organization_scope_denied"

    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_a,
            facility_id=None,
            roles=("REGISTRAR",),
            scopes=(Permission.MPI_IDENTITY_CREATE,),
            patient_id=None,
            purpose="registration",
            emergency_access_id=None,
            resource_type="PatientIdentity",
            action=Permission.MPI_IDENTITY_CREATE,
            actor_organization_ids=(org_a,),
        )
    )
    assert allowed.allowed is True


def test_wave1_pdp_does_not_use_doctor_role_shortcut() -> None:
    pdp = Wave1PolicyPDP()
    decision = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.PRACTITIONER,
            organization_id=uuid4(),
            facility_id=None,
            roles=("doctor",),
            scopes=(),
            patient_id=None,
            purpose="treatment",
            emergency_access_id=None,
            resource_type="PatientIdentity",
            action=Permission.MPI_MERGE_EXECUTE,
        )
    )
    assert decision.allowed is False
