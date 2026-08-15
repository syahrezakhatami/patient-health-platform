from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.application.services import _parse_optional_consent_code
from app.modules.clinical.domain.enums import ConsentStatus
from app.modules.clinical.domain.lifecycle import (
    CONSENT_TRANSITIONS,
    assert_consent_can_amend,
    assert_consent_can_revoke,
    assert_consent_mutable,
    assert_consent_period,
    consent_is_effective,
)
from app.modules.clinical.domain.terminology import CodeableConcept
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_consent_code_requires_both_or_neither() -> None:
    assert _parse_optional_consent_code(None) == (None, None, None)
    assert _parse_optional_consent_code(
        CodeableConcept(system="http://loinc.org", code="59284-0", display="Consent")
    ) == ("http://loinc.org", "59284-0", "Consent")
    with pytest.raises(AppError, match="system and code"):
        _parse_optional_consent_code(CodeableConcept(system=" ", code="59284-0", display=None))
    with pytest.raises(AppError, match="system and code"):
        _parse_optional_consent_code(
            CodeableConcept(system="http://loinc.org", code=" ", display=None)
        )


def test_consent_lifecycle_rejects_terminal_and_reactivation() -> None:
    assert ConsentStatus.AMENDED in CONSENT_TRANSITIONS[ConsentStatus.ACTIVE]
    assert ConsentStatus.REVOKED in CONSENT_TRANSITIONS[ConsentStatus.ACTIVE]
    assert ConsentStatus.ENTERED_IN_ERROR in CONSENT_TRANSITIONS[ConsentStatus.ACTIVE]
    assert ConsentStatus.REVOKED in CONSENT_TRANSITIONS[ConsentStatus.AMENDED]
    assert CONSENT_TRANSITIONS[ConsentStatus.REVOKED] == frozenset()
    assert CONSENT_TRANSITIONS[ConsentStatus.ENTERED_IN_ERROR] == frozenset()
    assert ConsentStatus.ACTIVE not in CONSENT_TRANSITIONS[ConsentStatus.AMENDED]
    assert_consent_can_amend(ConsentStatus.ACTIVE)
    assert_consent_can_amend(ConsentStatus.AMENDED)
    assert_consent_can_revoke(ConsentStatus.ACTIVE)
    with pytest.raises(AppError, match="terminal"):
        assert_consent_mutable(ConsentStatus.REVOKED)
    with pytest.raises(AppError, match="immutable"):
        assert_consent_mutable(ConsentStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="terminal"):
        assert_consent_can_amend(ConsentStatus.REVOKED)
    with pytest.raises(AppError, match="immutable"):
        assert_consent_can_revoke(ConsentStatus.ENTERED_IN_ERROR)


def test_consent_period_and_effectiveness_without_expired_status() -> None:
    now = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
    start = now - timedelta(days=1)
    end = now + timedelta(days=1)
    past_end = now - timedelta(hours=1)
    assert_consent_period(start, end)
    with pytest.raises(AppError, match="period_end"):
        assert_consent_period(end, start)
    assert consent_is_effective(ConsentStatus.ACTIVE, None, None, now) is True
    assert consent_is_effective(ConsentStatus.AMENDED, start, end, now) is True
    assert consent_is_effective(ConsentStatus.ACTIVE, start, past_end, now) is False
    assert consent_is_effective(ConsentStatus.REVOKED, start, end, now) is False
    assert consent_is_effective(ConsentStatus.ENTERED_IN_ERROR, None, None, now) is False
    assert ConsentStatus.REVOKED.value != "EXPIRED"


def test_pdp_allows_consent_permission_and_denies_unknown_alias() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_CONSENT_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Consent",
            action=Permission.CLINICAL_CONSENT_CREATE,
            actor_organization_ids=(org_id,),
        )
    )
    assert allowed.allowed is True
    unknown = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=("clinical.diagnosis.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Diagnosis",
            action="clinical.diagnosis.create",
            actor_organization_ids=(org_id,),
        )
    )
    assert unknown.allowed is False
    assert unknown.reason == "deny_by_default"


def test_consent_note_and_display_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "code_display": "Informed treatment consent",
            "note": "Patient signed form A",
            "note_text": "Patient signed form A",
            "consent_note": "Patient signed form A",
            "event": "request",
        },
    )
    assert redacted["code_display"] == "[REDACTED]"
    assert redacted["note"] == "[REDACTED]"
    assert redacted["note_text"] == "[REDACTED]"
    assert redacted["consent_note"] == "[REDACTED]"
    assert redacted["event"] == "request"
