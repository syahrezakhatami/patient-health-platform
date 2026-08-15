from decimal import Decimal
from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.core.logging import _redact_secrets
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import (
    LaboratoryOrderStatus,
    LaboratoryResultStatus,
    LaboratoryResultValueType,
    LaboratorySpecimenStatus,
)
from app.modules.clinical.domain.laboratory_values import parse_laboratory_result_value
from app.modules.clinical.domain.lifecycle import (
    LAB_ORDER_TRANSITIONS,
    LAB_RESULT_TRANSITIONS,
    LAB_SPECIMEN_TRANSITIONS,
    assert_lab_order_open,
    assert_lab_order_transition,
    assert_lab_result_can_amend,
    assert_lab_result_mutable,
    assert_lab_specimen_collectable,
    assert_lab_specimen_transition,
)
from app.modules.clinical.domain.terminology import parse_codeable_concept
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_laboratory_result_value_types_and_terminology_stub() -> None:
    numeric = parse_laboratory_result_value(
        value_type=LaboratoryResultValueType.NUMERIC,
        value_numeric=Decimal("5.4"),
        value_text=None,
        value_boolean=None,
        value_coded=None,
        unit="mmol/L",
        range_low=Decimal("3.9"),
        range_high=Decimal("5.8"),
    )
    assert numeric.numeric == Decimal("5.4")
    with pytest.raises(AppError, match="value_numeric only"):
        parse_laboratory_result_value(
            value_type=LaboratoryResultValueType.NUMERIC,
            value_numeric=Decimal("5.4"),
            value_text="5.4",
            value_boolean=None,
            value_coded=None,
            unit="mmol/L",
            range_low=None,
            range_high=None,
        )
    with pytest.raises(AppError, match="requires a unit"):
        parse_laboratory_result_value(
            value_type=LaboratoryResultValueType.NUMERIC,
            value_numeric=Decimal("5.4"),
            value_text=None,
            value_boolean=None,
            value_coded=None,
            unit=None,
            range_low=None,
            range_high=None,
        )
    with pytest.raises(AppError, match="value_text only"):
        parse_laboratory_result_value(
            value_type=LaboratoryResultValueType.TEXT,
            value_numeric=Decimal("1"),
            value_text="detected",
            value_boolean=None,
            value_coded=None,
            unit=None,
            range_low=None,
            range_high=None,
        )
    coded = parse_laboratory_result_value(
        value_type=LaboratoryResultValueType.CODED,
        value_numeric=None,
        value_text=None,
        value_boolean=None,
        value_coded={"system": "http://example.org", "code": "POS", "display": "Positive"},
        unit=None,
        range_low=None,
        range_high=None,
    )
    assert coded.coded is not None
    assert coded.coded.code == "POS"
    with pytest.raises(AppError, match="system and code"):
        parse_codeable_concept({"system": "http://example.org", "code": ""})
    with pytest.raises(AppError, match="system and code"):
        parse_laboratory_result_value(
            value_type=LaboratoryResultValueType.CODED,
            value_numeric=None,
            value_text=None,
            value_boolean=None,
            value_coded={"system": "", "code": "POS"},
            unit=None,
            range_low=None,
            range_high=None,
        )


def test_laboratory_lifecycles_and_invalid_transitions() -> None:
    assert (
        LaboratoryOrderStatus.IN_PROGRESS in LAB_ORDER_TRANSITIONS[LaboratoryOrderStatus.REGISTERED]
    )
    assert (
        LaboratoryOrderStatus.CANCELLED in LAB_ORDER_TRANSITIONS[LaboratoryOrderStatus.REGISTERED]
    )
    assert (
        LaboratoryOrderStatus.CANCELLED
        not in LAB_ORDER_TRANSITIONS[LaboratoryOrderStatus.IN_PROGRESS]
    )
    assert LAB_ORDER_TRANSITIONS[LaboratoryOrderStatus.CANCELLED] == frozenset()
    assert LAB_ORDER_TRANSITIONS[LaboratoryOrderStatus.ENTERED_IN_ERROR] == frozenset()
    assert_lab_order_transition(LaboratoryOrderStatus.REGISTERED, LaboratoryOrderStatus.CANCELLED)
    with pytest.raises(AppError, match="cannot transition"):
        assert_lab_order_transition(
            LaboratoryOrderStatus.IN_PROGRESS, LaboratoryOrderStatus.CANCELLED
        )
    with pytest.raises(AppError, match="cannot receive"):
        assert_lab_order_open(LaboratoryOrderStatus.CANCELLED)
    with pytest.raises(AppError, match="cannot receive"):
        assert_lab_order_open(LaboratoryOrderStatus.ENTERED_IN_ERROR)

    assert (
        LaboratorySpecimenStatus.REJECTED
        in LAB_SPECIMEN_TRANSITIONS[LaboratorySpecimenStatus.COLLECTED]
    )
    assert LAB_SPECIMEN_TRANSITIONS[LaboratorySpecimenStatus.REJECTED] == frozenset()
    assert_lab_specimen_collectable(LaboratorySpecimenStatus.COLLECTED)
    with pytest.raises(AppError, match="cannot transition"):
        assert_lab_specimen_transition(
            LaboratorySpecimenStatus.REJECTED, LaboratorySpecimenStatus.COLLECTED
        )
    with pytest.raises(AppError, match="COLLECTED specimen"):
        assert_lab_specimen_collectable(LaboratorySpecimenStatus.REJECTED)

    assert LaboratoryResultStatus.AMENDED in LAB_RESULT_TRANSITIONS[LaboratoryResultStatus.FINAL]
    assert_lab_result_can_amend(LaboratoryResultStatus.FINAL)
    assert_lab_result_can_amend(LaboratoryResultStatus.AMENDED)
    with pytest.raises(AppError, match="immutable"):
        assert_lab_result_mutable(LaboratoryResultStatus.ENTERED_IN_ERROR)
    with pytest.raises(AppError, match="immutable"):
        assert_lab_result_can_amend(LaboratoryResultStatus.ENTERED_IN_ERROR)


def test_pdp_allows_laboratory_permissions_and_denies_unknown_aliases() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_LAB_ORDER_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="LaboratoryOrder",
            action=Permission.CLINICAL_LAB_ORDER_CREATE,
            actor_organization_ids=(org_id,),
        )
    )
    assert allowed.allowed is True
    unknown_lab = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=("clinical.laboratory.create",),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Laboratory",
            action="clinical.laboratory.create",
            actor_organization_ids=(org_id,),
        )
    )
    assert unknown_lab.allowed is False
    assert unknown_lab.reason == "deny_by_default"
    unknown_dx = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=("clinical.laboratory.order.create",),
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
    unknown_med = pdp.evaluate(
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
    assert unknown_med.allowed is False
    assert unknown_med.reason == "deny_by_default"


def test_laboratory_values_are_redacted_from_log_events() -> None:
    redacted = _redact_secrets(
        None,  # type: ignore[arg-type]
        "info",
        {
            "value_text": "detected",
            "value_numeric": "5.4",
            "value_boolean": True,
            "value_code": "2345-7",
            "value_code_system": "http://loinc.org",
            "value_code_display": "Glucose",
            "value_coded": {"system": "http://loinc.org", "code": "2345-7"},
            "reference_range_low": "3.9",
            "reference_range_high": "5.8",
            "event": "request",
        },
    )
    assert redacted["value_text"] == "[REDACTED]"
    assert redacted["value_numeric"] == "[REDACTED]"
    assert redacted["value_boolean"] == "[REDACTED]"
    assert redacted["value_code"] == "[REDACTED]"
    assert redacted["value_coded"] == "[REDACTED]"
    assert redacted["reference_range_low"] == "[REDACTED]"
    assert redacted["reference_range_high"] == "[REDACTED]"
    assert redacted["event"] == "request"
