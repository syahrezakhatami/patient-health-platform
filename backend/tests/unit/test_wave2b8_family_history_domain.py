from uuid import uuid4

import pytest
from app.api.v1.schemas import CreateFamilyHistoryRequest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import FamilyHistoryStatus
from app.modules.clinical.domain.lifecycle import (
    FAMILY_HISTORY_TRANSITIONS,
    assert_family_history_can_amend,
    assert_family_history_mutable,
)
from app.shared.enums import PrincipalType
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_family_history_lifecycle_and_immutability() -> None:
    assert FamilyHistoryStatus.AMENDED in FAMILY_HISTORY_TRANSITIONS[FamilyHistoryStatus.ACTIVE]
    assert (
        FamilyHistoryStatus.ENTERED_IN_ERROR
        in FAMILY_HISTORY_TRANSITIONS[FamilyHistoryStatus.ACTIVE]
    )
    assert (
        FamilyHistoryStatus.ENTERED_IN_ERROR
        in FAMILY_HISTORY_TRANSITIONS[FamilyHistoryStatus.AMENDED]
    )
    assert FAMILY_HISTORY_TRANSITIONS[FamilyHistoryStatus.ENTERED_IN_ERROR] == frozenset()
    assert FamilyHistoryStatus.ACTIVE not in FAMILY_HISTORY_TRANSITIONS[FamilyHistoryStatus.AMENDED]
    assert_family_history_can_amend(FamilyHistoryStatus.ACTIVE)
    assert_family_history_can_amend(FamilyHistoryStatus.AMENDED)
    with pytest.raises(AppError, match="immutable"):
        assert_family_history_mutable(FamilyHistoryStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_family_history_can_amend(FamilyHistoryStatus.ENTERED_IN_ERROR)


def test_pdp_allows_family_history_permission_and_denies_unknown_aliases() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_FAMILY_HISTORY_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="FamilyHistory",
            action=Permission.CLINICAL_FAMILY_HISTORY_CREATE,
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


def test_family_history_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "code_display": "Breast cancer",
            "family_history_display": "Breast cancer",
            "family_history_code": "254837009",
            "note": "Mother diagnosed at 42",
            "note_text": "Mother diagnosed at 42",
            "family_history_note": "Mother diagnosed at 42",
            "event": "request",
        },
    )
    assert redacted["code_display"] == "[REDACTED]"
    assert redacted["family_history_display"] == "[REDACTED]"
    assert redacted["family_history_code"] == "[REDACTED]"
    assert redacted["note"] == "[REDACTED]"
    assert redacted["note_text"] == "[REDACTED]"
    assert redacted["family_history_note"] == "[REDACTED]"
    assert redacted["event"] == "request"


def test_create_request_rejects_sex_specific_relationships() -> None:
    base = {
        "patient_identity_id": uuid4(),
        "relationship": "PARENT",
        "category": "DOCUMENTED",
        "code": {"system": "http://snomed.info/sct", "code": "254837009"},
    }
    CreateFamilyHistoryRequest.model_validate(base)
    with pytest.raises(ValidationError):
        CreateFamilyHistoryRequest.model_validate({**base, "relationship": "MOTHER"})
    with pytest.raises(ValidationError):
        CreateFamilyHistoryRequest.model_validate({**base, "relationship": "FATHER"})
    with pytest.raises(ValidationError):
        CreateFamilyHistoryRequest.model_validate({**base, "relationship": "SPOUSE"})
