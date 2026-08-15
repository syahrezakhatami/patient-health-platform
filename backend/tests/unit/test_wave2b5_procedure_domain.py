from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import ProcedureStatus
from app.modules.clinical.domain.lifecycle import (
    PROCEDURE_TRANSITIONS,
    assert_procedure_can_amend,
    assert_procedure_mutable,
)
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_procedure_lifecycle_and_immutability() -> None:
    assert ProcedureStatus.AMENDED in PROCEDURE_TRANSITIONS[ProcedureStatus.ACTIVE]
    assert ProcedureStatus.ENTERED_IN_ERROR in PROCEDURE_TRANSITIONS[ProcedureStatus.ACTIVE]
    assert ProcedureStatus.ENTERED_IN_ERROR in PROCEDURE_TRANSITIONS[ProcedureStatus.AMENDED]
    assert PROCEDURE_TRANSITIONS[ProcedureStatus.ENTERED_IN_ERROR] == frozenset()
    assert ProcedureStatus.ACTIVE not in PROCEDURE_TRANSITIONS[ProcedureStatus.AMENDED]
    assert_procedure_can_amend(ProcedureStatus.ACTIVE)
    assert_procedure_can_amend(ProcedureStatus.AMENDED)
    with pytest.raises(AppError, match="immutable"):
        assert_procedure_mutable(ProcedureStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_procedure_can_amend(ProcedureStatus.ENTERED_IN_ERROR)


def test_pdp_allows_procedure_permission_and_denies_unknown_aliases() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_PROCEDURE_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Procedure",
            action=Permission.CLINICAL_PROCEDURE_CREATE,
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


def test_procedure_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "code_display": "Appendectomy",
            "procedure_display": "Appendectomy",
            "procedure_code": "80146002",
            "note": "Uneventful recovery",
            "note_text": "Uneventful recovery",
            "procedure_note": "Uneventful recovery",
            "event": "request",
        },
    )
    assert redacted["code_display"] == "[REDACTED]"
    assert redacted["procedure_display"] == "[REDACTED]"
    assert redacted["procedure_code"] == "[REDACTED]"
    assert redacted["note"] == "[REDACTED]"
    assert redacted["note_text"] == "[REDACTED]"
    assert redacted["procedure_note"] == "[REDACTED]"
    assert redacted["event"] == "request"
