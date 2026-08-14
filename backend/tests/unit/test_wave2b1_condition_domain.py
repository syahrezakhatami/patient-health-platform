from uuid import uuid4

import pytest
from app.core.errors import AppError
from app.modules.authorization.application.wave1_pdp import Wave1PolicyPDP
from app.modules.authorization.domain.catalog import Permission
from app.modules.authorization.domain.models import AuthorizationContext
from app.modules.clinical.domain.enums import (
    ConditionClinicalStatus,
    ConditionVerificationStatus,
)
from app.modules.clinical.domain.lifecycle import (
    assert_condition_clinical_transition,
    assert_condition_mutable,
    assert_condition_verification_transition,
)
from app.shared.enums import PrincipalType

pytestmark = pytest.mark.unit


def test_condition_clinical_status_machine() -> None:
    assert_condition_clinical_transition(
        ConditionClinicalStatus.ACTIVE, ConditionClinicalStatus.RESOLVED
    )
    assert_condition_clinical_transition(
        ConditionClinicalStatus.RESOLVED, ConditionClinicalStatus.RECURRENCE
    )
    with pytest.raises(AppError, match="cannot transition"):
        assert_condition_clinical_transition(
            ConditionClinicalStatus.INACTIVE, ConditionClinicalStatus.RESOLVED
        )


def test_condition_verification_and_immutability() -> None:
    assert_condition_verification_transition(
        ConditionVerificationStatus.UNCONFIRMED, ConditionVerificationStatus.CONFIRMED
    )
    with pytest.raises(AppError, match="cannot transition"):
        assert_condition_verification_transition(
            ConditionVerificationStatus.REFUTED, ConditionVerificationStatus.CONFIRMED
        )
    with pytest.raises(AppError, match="immutable"):
        assert_condition_mutable(ConditionVerificationStatus.ENTERED_IN_ERROR)
    assert_condition_mutable(ConditionVerificationStatus.CONFIRMED)


def test_pdp_allows_condition_permission_and_still_denies_unknown_diagnosis_alias() -> None:
    pdp = Wave1PolicyPDP()
    org_id = uuid4()
    allowed = pdp.evaluate(
        AuthorizationContext(
            actor_id=uuid4(),
            principal_type=PrincipalType.STAFF,
            organization_id=org_id,
            facility_id=None,
            roles=("CLINICIAN",),
            scopes=(Permission.CLINICAL_CONDITION_CREATE,),
            patient_id=None,
            purpose="TREATMENT",
            emergency_access_id=None,
            resource_type="Condition",
            action=Permission.CLINICAL_CONDITION_CREATE,
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
