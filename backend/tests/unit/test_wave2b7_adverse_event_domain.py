from uuid import uuid4

import pytest
from app.api.v1.schemas import CreateAdverseEventRequest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import AdverseEventStatus
from app.modules.clinical.domain.lifecycle import (
    ADVERSE_EVENT_TRANSITIONS,
    assert_adverse_event_can_amend,
    assert_adverse_event_mutable,
)
from app.shared.enums import PrincipalType
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_adverse_event_lifecycle_and_immutability() -> None:
    assert AdverseEventStatus.AMENDED in ADVERSE_EVENT_TRANSITIONS[AdverseEventStatus.ACTIVE]
    assert (
        AdverseEventStatus.ENTERED_IN_ERROR in ADVERSE_EVENT_TRANSITIONS[AdverseEventStatus.ACTIVE]
    )
    assert (
        AdverseEventStatus.ENTERED_IN_ERROR in ADVERSE_EVENT_TRANSITIONS[AdverseEventStatus.AMENDED]
    )
    assert ADVERSE_EVENT_TRANSITIONS[AdverseEventStatus.ENTERED_IN_ERROR] == frozenset()
    assert AdverseEventStatus.ACTIVE not in ADVERSE_EVENT_TRANSITIONS[AdverseEventStatus.AMENDED]
    assert_adverse_event_can_amend(AdverseEventStatus.ACTIVE)
    assert_adverse_event_can_amend(AdverseEventStatus.AMENDED)
    with pytest.raises(AppError, match="immutable"):
        assert_adverse_event_mutable(AdverseEventStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_adverse_event_can_amend(AdverseEventStatus.ENTERED_IN_ERROR)


def test_pdp_allows_adverse_event_permission_and_denies_unknown_aliases() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_ADVERSE_EVENT_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="AdverseEvent",
            action=Permission.CLINICAL_ADVERSE_EVENT_CREATE,
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
            scopes=("clinical.care_plan.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="CarePlan",
            action="clinical.care_plan.create",
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


def test_adverse_event_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "code_display": "Anaphylaxis",
            "adverse_event_display": "Anaphylaxis",
            "adverse_event_code": "39579001",
            "note": "Hives after first dose",
            "note_text": "Hives after first dose",
            "adverse_event_note": "Hives after first dose",
            "severity": "SEVERE",
            "event": "request",
        },
    )
    assert redacted["code_display"] == "[REDACTED]"
    assert redacted["adverse_event_display"] == "[REDACTED]"
    assert redacted["adverse_event_code"] == "[REDACTED]"
    assert redacted["note"] == "[REDACTED]"
    assert redacted["note_text"] == "[REDACTED]"
    assert redacted["adverse_event_note"] == "[REDACTED]"
    assert redacted["severity"] == "[REDACTED]"
    assert redacted["event"] == "request"


def test_create_request_rejects_more_than_one_related_fact() -> None:
    patient_id = uuid4()
    medication_id = uuid4()
    device_id = uuid4()
    procedure_id = uuid4()
    base = {
        "patient_identity_id": patient_id,
        "category": "DOCUMENTED",
        "code": {"system": "http://snomed.info/sct", "code": "39579001"},
        "severity": "MILD",
    }
    CreateAdverseEventRequest.model_validate(base)
    CreateAdverseEventRequest.model_validate({**base, "medication_id": medication_id})
    CreateAdverseEventRequest.model_validate({**base, "medical_device_id": device_id})
    CreateAdverseEventRequest.model_validate({**base, "procedure_id": procedure_id})
    with pytest.raises(ValidationError, match="at most one related clinical fact"):
        CreateAdverseEventRequest.model_validate(
            {**base, "medication_id": medication_id, "medical_device_id": device_id}
        )
    with pytest.raises(ValidationError, match="at most one related clinical fact"):
        CreateAdverseEventRequest.model_validate(
            {**base, "medication_id": medication_id, "procedure_id": procedure_id}
        )
    with pytest.raises(ValidationError, match="at most one related clinical fact"):
        CreateAdverseEventRequest.model_validate(
            {**base, "medical_device_id": device_id, "procedure_id": procedure_id}
        )
