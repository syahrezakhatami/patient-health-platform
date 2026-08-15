from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import ImmunizationStatus
from app.modules.clinical.domain.lifecycle import (
    IMMUNIZATION_TRANSITIONS,
    assert_immunization_can_amend,
    assert_immunization_mutable,
)
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_immunization_lifecycle_and_immutability() -> None:
    assert ImmunizationStatus.AMENDED in IMMUNIZATION_TRANSITIONS[ImmunizationStatus.ACTIVE]
    assert (
        ImmunizationStatus.ENTERED_IN_ERROR in IMMUNIZATION_TRANSITIONS[ImmunizationStatus.ACTIVE]
    )
    assert (
        ImmunizationStatus.ENTERED_IN_ERROR in IMMUNIZATION_TRANSITIONS[ImmunizationStatus.AMENDED]
    )
    assert IMMUNIZATION_TRANSITIONS[ImmunizationStatus.ENTERED_IN_ERROR] == frozenset()
    assert ImmunizationStatus.ACTIVE not in IMMUNIZATION_TRANSITIONS[ImmunizationStatus.AMENDED]
    assert_immunization_can_amend(ImmunizationStatus.ACTIVE)
    assert_immunization_can_amend(ImmunizationStatus.AMENDED)
    with pytest.raises(AppError, match="immutable"):
        assert_immunization_mutable(ImmunizationStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_immunization_can_amend(ImmunizationStatus.ENTERED_IN_ERROR)


def test_pdp_allows_immunization_permission_and_denies_unknown_aliases() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_IMMUNIZATION_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Immunization",
            action=Permission.CLINICAL_IMMUNIZATION_CREATE,
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
            scopes=("clinical.procedure.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Procedure",
            action="clinical.procedure.create",
            actor_organization_ids=(org_id,),
        )
    )
    assert unknown.allowed is False
    assert unknown.reason == "deny_by_default"
    unknown_dx = pdp.evaluate(
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
    assert unknown_dx.allowed is False
    assert unknown_dx.reason == "deny_by_default"


def test_immunization_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "code_display": "COVID-19 vaccine",
            "vaccine_display": "COVID-19 vaccine",
            "vaccine_code": "208",
            "note": "Given in left arm",
            "note_text": "Given in left arm",
            "immunization_note": "Given in left arm",
            "event": "request",
        },
    )
    assert redacted["code_display"] == "[REDACTED]"
    assert redacted["vaccine_display"] == "[REDACTED]"
    assert redacted["vaccine_code"] == "[REDACTED]"
    assert redacted["note"] == "[REDACTED]"
    assert redacted["note_text"] == "[REDACTED]"
    assert redacted["immunization_note"] == "[REDACTED]"
    assert redacted["event"] == "request"
