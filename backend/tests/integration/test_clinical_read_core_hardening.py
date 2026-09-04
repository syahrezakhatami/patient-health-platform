import hashlib
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from app.api.v1 import clinical_read as clinical_read_api
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.clinical.infrastructure.models import ClinicalProvenanceModel
from app.modules.clinical_read.application.services import ClinicalReadService
from app.modules.clinical_read.domain.catalog import SECTION_PERMISSIONS
from app.modules.clinical_read.domain.enums import ChartSection
from app.modules.clinical_read.infrastructure.queries import ClinicalReadQueryRepository
from app.modules.mpi.domain.enums import ProvenanceSubjectType
from app.modules.mpi.infrastructure.models import IdentityProvenanceModel, PatientIdentifierModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.enums import AuthorshipKind, InformationSource
from app.shared.types.ids import new_id
from sqlalchemy import func, select, text
from tests.conftest import TEST_SECRET, mint_token
from tests.integration.clinical_notes import (
    create_note_body,
    new_idempotency_key,
    note_write_headers,
)
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_clinical_read_core import _chart, _seed_limited, _staff_headers
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b1_condition import _pneumonia
from tests.integration.test_wave2b2a_observation import _generic_exam_observation
from tests.integration.test_wave2b2b_laboratory import _collect_specimen, _glucose, _lab_order
from tests.integration.test_wave2b3a_medication import _paracetamol
from tests.integration.test_wave2b3b_allergy import _penicillin
from tests.integration.test_wave2b3c_consent import _consent
from tests.integration.test_wave2b4_immunization import _vaccine
from tests.integration.test_wave2b5_procedure import _procedure
from tests.integration.test_wave2b6_medical_device import _device
from tests.integration.test_wave2b7_adverse_event import _event
from tests.integration.test_wave2b8_family_history import _history

pytestmark = pytest.mark.integration

APP_ROOT = Path(__file__).resolve().parents[2] / "app"
WAVE1_SHA256 = "f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd"
SHELL_PERMS = (
    Permission.MPI_IDENTITY_READ,
    Permission.IAM_USER_READ,
    Permission.ORG_ORGANIZATION_READ,
)


def _assert_no_leak(response) -> None:
    blob = response.text.lower()
    assert "traceback" not in blob
    assert "sqlalchemy" not in blob
    assert "bearer " not in blob
    assert "password" not in blob


def test_hardening_static_surface_and_auth_order() -> None:
    digest = hashlib.sha256(
        (APP_ROOT / "modules" / "authorization" / "application" / "wave1_pdp.py").read_bytes()
    ).hexdigest()
    assert digest == WAVE1_SHA256
    catalog = (APP_ROOT / "modules" / "authorization" / "domain" / "catalog.py").read_text()
    assert "clinical.chart.read" not in catalog
    module_root = APP_ROOT / "modules" / "clinical_read"
    for path in module_root.rglob("*.py"):
        text_body = path.read_text(encoding="utf-8")
        assert "import redis" not in text_body
        assert "from redis" not in text_body
        assert "Redis(" not in text_body
    settings_src = (APP_ROOT / "core" / "config.py").read_text(encoding="utf-8")
    assert "rate_limit_per_minute: int = 120" in settings_src
    methods = {
        (route.path, frozenset(route.methods or ()))  # type: ignore[attr-defined]
        for route in clinical_read_api.router.routes
    }
    expected = {
        ("/clinical/patients/{patient_identity_id}/chart", frozenset({"GET"})),
        ("/clinical/patients/{patient_identity_id}/chart/summary", frozenset({"GET"})),
        ("/clinical/patients/{patient_identity_id}/chart/timeline", frozenset({"GET"})),
        (
            "/clinical/patients/{patient_identity_id}/chart/sections/{section}",
            frozenset({"GET"}),
        ),
    }
    assert expected <= methods
    for _path, verbs in methods:
        assert verbs <= {"GET", "HEAD"}
    section_src = inspect.getsource(ClinicalReadService.get_section)
    assert section_src.index("authorize(") < section_src.index("_project_section")
    assert section_src.index("validate_section_filters") < section_src.index("_project_section")
    query_src = inspect.getsource(ClinicalReadQueryRepository._base_select)
    assert "model.organization_id == query.organization_id" in query_src
    assert "patient_identity_id.in_(query.cluster_ids)" in query_src
    dto_src = (module_root / "application" / "schemas.py").read_text()
    assert "provenance_id" not in dto_src
    assert "body_text" not in dto_src
    assert "nik" not in dto_src.lower()
    assert "bpjs" not in dto_src.lower()
    assert set(SECTION_PERMISSIONS) == set(ChartSection)


@requires_db
async def test_hardening_audience_purpose_shell_and_header(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "No",
            "family_name": "Dob",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("NOD"),
                }
            ],
        },
    )
    assert created.status_code in {200, 201}
    no_dob_id = created.json()["id"]
    allergy = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    assert allergy.status_code in {200, 201}

    ok = await db_client.get(_chart(patient_id), headers=_staff_headers(clinician))
    assert ok.status_code == 200
    _assert_no_leak(ok)
    assert ok.json()["header"]["documented_allergy_exists"] is True
    assert "nik" not in ok.text.lower()
    assert "bpjs" not in ok.text.lower()

    no_dob = await db_client.get(_chart(no_dob_id), headers=_staff_headers(clinician))
    assert no_dob.status_code == 200
    assert "age_years" in no_dob.json()["header"]
    assert no_dob.json()["header"]["age_years"] is None
    assert no_dob.json()["header"]["documented_allergy_exists"] is False

    for aud in ("php-patient", "php-platform"):
        denied = await db_client.get(
            _chart(patient_id),
            headers={
                "Authorization": f"Bearer {mint_token(sub=clinician.subject, aud=aud)}",
                "X-Organization-Id": str(clinician.organization_id),
                "X-Purpose": "TREATMENT",
            },
        )
        assert denied.status_code == 401
        _assert_no_leak(denied)

    mixed = mint_token(sub=clinician.subject, extra={"aud": ["php-api", "php-patient"]})
    mixed_denied = await db_client.get(
        _chart(patient_id),
        headers={
            "Authorization": f"Bearer {mixed}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert mixed_denied.status_code == 401

    missing_aud = jwt.encode(
        {
            "sub": clinician.subject,
            "iss": "http://localhost:8080/realms/php-dev",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iat": datetime.now(UTC),
        },
        TEST_SECRET,
        algorithm="HS256",
    )
    no_aud = await db_client.get(
        _chart(patient_id),
        headers={
            "Authorization": f"Bearer {missing_aud}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert no_aud.status_code == 401

    for target in (patient_id, str(uuid4())):
        purpose_denied = await db_client.get(
            _chart(target),
            headers=_staff_headers(clinician, "PATIENT_ACCESS"),
        )
        assert purpose_denied.status_code == 403
        assert purpose_denied.json()["error"]["code"] == "purpose_principal_mismatch"
        _assert_no_leak(purpose_denied)

    no_mpi = await _seed_limited(
        db_engine,
        clinician.organization_id,
        (Permission.IAM_USER_READ, Permission.ORG_ORGANIZATION_READ),
    )
    missing_identity = await db_client.get(_chart(patient_id), headers=_staff_headers(no_mpi))
    assert missing_identity.status_code == 403

    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    platform_chart = await db_client.get(_chart(patient_id), headers=_staff_headers(platform))
    assert platform_chart.status_code == 403

    outsider = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    cross_header = await db_client.get(
        _chart(patient_id),
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(outsider.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert cross_header.status_code in {403, 404}
    _assert_no_leak(cross_header)
    foreign_patient = await db_client.get(_chart(patient_id), headers=_staff_headers(outsider))
    assert foreign_patient.status_code == 404

    for method in ("POST", "PUT", "PATCH", "DELETE"):
        mutation = await db_client.request(
            method, _chart(patient_id), headers=_staff_headers(clinician)
        )
        assert mutation.status_code in {404, 405}


@requires_db
async def test_hardening_section_permissions_lab_and_query_guard(
    db_client, db_engine, monkeypatch
) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    auditor = await seed_actor(
        db_engine, role_code=RoleCode.AUDITOR, organization_id=clinician.organization_id
    )
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    for factory, path in (
        (_pneumonia(patient_id), "/api/v1/clinical/conditions"),
        (_paracetamol(patient_id), "/api/v1/clinical/medications"),
        (_penicillin(patient_id), "/api/v1/clinical/allergies"),
    ):
        created = await db_client.post(
            path, headers=clinician.headers(purpose="TREATMENT"), json=factory
        )
        assert created.status_code in {200, 201}
    order = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, encounter_id),
    )
    assert order.status_code in {200, 201}
    specimen = await _collect_specimen(db_client, clinician, order.json()["id"])
    assert specimen.status_code in {200, 201}
    result = await db_client.post(
        "/api/v1/clinical/laboratory/results",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_glucose(specimen.json()["id"]),
    )
    assert result.status_code in {200, 201}

    queried: list[str] = []
    original = ClinicalReadQueryRepository.page_source

    async def tracked(self, source_type, query):
        queried.append(source_type.value)
        return await original(self, source_type, query)

    monkeypatch.setattr(ClinicalReadQueryRepository, "page_source", tracked)

    limited = await _seed_limited(
        db_engine,
        clinician.organization_id,
        (*SHELL_PERMS, Permission.CLINICAL_CONDITION_READ, Permission.CLINICAL_MEDICATION_READ),
    )
    shell = await db_client.get(_chart(patient_id), headers=_staff_headers(limited))
    assert shell.status_code == 200
    assert shell.json()["authorized_sections"] == ["conditions", "medications"]
    assert "documented_allergy_exists" not in shell.json()["header"]
    queried.clear()
    forbidden = await db_client.get(
        _chart(patient_id, "/sections/allergies"), headers=_staff_headers(limited)
    )
    assert forbidden.status_code == 403
    assert "allergy" not in queried
    allowed = await db_client.get(
        _chart(patient_id, "/sections/conditions"), headers=_staff_headers(limited)
    )
    assert allowed.status_code == 200
    assert "condition" in queried
    summary = await db_client.get(_chart(patient_id, "/summary"), headers=_staff_headers(limited))
    assert "active_conditions" in summary.json()
    assert "active_allergies" not in summary.json()

    order_only = await _seed_limited(
        db_engine, clinician.organization_id, (*SHELL_PERMS, Permission.CLINICAL_LAB_ORDER_READ)
    )
    lab_orders = await db_client.get(
        _chart(patient_id, "/sections/laboratory"), headers=_staff_headers(order_only)
    )
    assert lab_orders.status_code == 200
    assert "specimens" not in lab_orders.json()["items"][0]
    assert "results" not in lab_orders.json()["items"][0]
    result_only = await _seed_limited(
        db_engine, clinician.organization_id, (*SHELL_PERMS, Permission.CLINICAL_LAB_RESULT_READ)
    )
    lab_results = await db_client.get(
        _chart(patient_id, "/sections/laboratory"), headers=_staff_headers(result_only)
    )
    assert lab_results.status_code == 200
    assert lab_results.json()["items"][0]["laboratory_order_id"] == order.json()["id"]
    assert "ordered_at" not in lab_results.json()["items"][0]

    registrar_shell = await db_client.get(
        _chart(patient_id), headers=_staff_headers(registrar, "REGISTRATION")
    )
    assert registrar_shell.json()["authorized_sections"] == ["encounters"]
    assert (
        await db_client.get(
            _chart(patient_id, "/sections/conditions"),
            headers=_staff_headers(registrar, "REGISTRATION"),
        )
    ).status_code == 403
    officer_shell = await db_client.get(
        _chart(patient_id), headers=_staff_headers(officer, "IDENTITY_RESOLUTION")
    )
    assert officer_shell.json()["authorized_sections"] == []
    assert (
        await db_client.get(
            _chart(patient_id, "/sections/encounters"),
            headers=_staff_headers(officer, "IDENTITY_RESOLUTION"),
        )
    ).status_code == 403
    for actor, purpose in ((auditor, "AUDIT"), (org_admin, "ADMINISTRATION")):
        visible = await db_client.get(
            _chart(patient_id, "/sections/conditions"), headers=_staff_headers(actor, purpose)
        )
        assert visible.status_code == 200

    for slug in ("vitals", "condition", "CONDITIONS", "../notes", "sql"):
        unknown = await db_client.get(
            _chart(patient_id, f"/sections/{slug}"), headers=_staff_headers(clinician)
        )
        assert unknown.status_code == 404
        _assert_no_leak(unknown)
    bad_status = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"status": "NOPE"},
    )
    assert bad_status.status_code == 422
    assert bad_status.json()["error"]["code"] == "invalid_status"
    bad_category = await db_client.get(
        _chart(patient_id, "/sections/observations"),
        headers=_staff_headers(clinician),
        params={"category": "LAB"},
    )
    assert bad_category.status_code == 422
    ok_vitals = await db_client.get(
        _chart(patient_id, "/sections/observations"),
        headers=_staff_headers(clinician),
        params={"category": "VITAL_SIGNS"},
    )
    assert ok_vitals.status_code == 200


@requires_db
async def test_hardening_cluster_tenant_notes_mrn_and_duplicates(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    officer_b = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=hospital_b.organization_id
    )
    mrn_a = unique_mrn("HA")
    identity_a = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Chain",
            "family_name": "Alpha",
            "birth_date": "1991-01-01",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": mrn_a,
                }
            ],
        },
    )
    assert identity_a.status_code in {200, 201}
    id_a = identity_a.json()["id"]
    fact_a = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(id_a),
    )
    assert fact_a.status_code in {200, 201}
    identity_b = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Chain", family="Beta", birth="1991-01-01"),
    )
    id_b = identity_b.json()["id"]
    merge_ab = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": id_a,
            "target_identity_id": id_b,
            "reason": "A into B",
            "evidence": merge_evidence("crc-hard-ab"),
        },
    )
    assert merge_ab.status_code in {200, 201}
    fact_b = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(id_b),
    )
    assert fact_b.status_code in {200, 201}
    dup = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(id_b),
    )
    assert dup.status_code in {200, 201}
    encounter = await _open_encounter(db_client, clinician, id_b)
    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("crc-h-a")),
        json=create_note_body(
            id_b,
            encounter.json()["id"],
            body_text="Hardening secret narrative",
        ),
    )
    assert note.status_code in {200, 201}
    async with db_engine.begin() as connection:
        await connection.execute(
            IdentityProvenanceModel.__table__.insert().values(
                id=new_id(),
                subject_type=ProvenanceSubjectType.PATIENT_IDENTITY,
                subject_id=id_b,
                source_organization_id=hospital_b.organization_id,
                source_facility_id=None,
                source_system=None,
                source_record_id=None,
                actor_id=officer_b.user_id,
                recorded_at=datetime.now(UTC),
                imported_at=None,
                verification_method=None,
                authorship_kind=AuthorshipKind.NATIVE,
                information_source=InformationSource.CLINICIAN,
            )
        )
        await connection.execute(
            PatientIdentifierModel.__table__.insert().values(
                id=new_id(),
                patient_identity_id=id_b,
                organization_id=hospital_b.organization_id,
                identifier_system="hospital-mrn",
                identifier_type="MRN",
                identifier_value="MRN-HOSP-B-HIDDEN",
                normalized_value="MRNHOSPBHIDDEN",
                matching_value="mrn-hosp-b-hidden",
                verification_status="UNVERIFIED",
                valid_from=datetime.now(UTC),
                valid_to=None,
            )
        )
    foreign_condition = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=hospital_b.headers(purpose="TREATMENT"),
        json=_pneumonia(id_b),
    )
    assert foreign_condition.status_code in {200, 201}
    encounter_b = await _open_encounter(db_client, hospital_b, id_b)
    note_b = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(hospital_b, idempotency_key=new_idempotency_key("crc-h-b")),
        json=create_note_body(
            id_b,
            encounter_b.json()["id"],
            body_text="Hospital B narrative must not leak",
        ),
    )
    assert note_b.status_code in {200, 201}

    shell_a = await db_client.get(_chart(id_a), headers=_staff_headers(clinician))
    assert shell_a.status_code == 200
    assert shell_a.json()["canonical_patient_identity_id"] == id_b
    assert mrn_a in shell_a.json()["header"]["mrn"]
    assert "MRN-HOSP-B-HIDDEN" not in shell_a.json()["header"]["mrn"]
    a_conditions = await db_client.get(
        _chart(id_b, "/sections/conditions"), headers=_staff_headers(clinician)
    )
    ids = {item["id"] for item in a_conditions.json()["items"]}
    assert {fact_a.json()["id"], fact_b.json()["id"], dup.json()["id"]} <= ids
    assert foreign_condition.json()["id"] not in ids
    assert len(ids) == len(a_conditions.json()["items"])
    b_conditions = await db_client.get(
        _chart(id_b, "/sections/conditions"), headers=_staff_headers(hospital_b)
    )
    b_ids = {item["id"] for item in b_conditions.json()["items"]}
    assert foreign_condition.json()["id"] in b_ids
    assert fact_b.json()["id"] not in b_ids
    notes_a = await db_client.get(
        _chart(id_b, "/sections/notes"), headers=_staff_headers(clinician)
    )
    assert "body_text" not in notes_a.json()["items"][0]
    assert "Hardening secret narrative" not in notes_a.text
    assert "Hospital B narrative" not in notes_a.text
    other_patient = await _active_patient(db_client, registrar)
    other_encounter = await _open_encounter(db_client, clinician, other_patient)
    assert (
        await db_client.get(
            _chart(id_b, "/sections/notes"),
            headers=_staff_headers(clinician),
            params={"encounter_id": other_encounter.json()["id"]},
        )
    ).status_code == 404
    assert (
        await db_client.get(
            _chart(id_b, "/sections/notes"),
            headers=_staff_headers(clinician),
            params={"encounter_id": encounter_b.json()["id"]},
        )
    ).status_code == 404
    cancelled = await db_client.post(
        f"/api/v1/clinical/encounters/{encounter.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancelled.status_code in {200, 201}
    assert (
        await db_client.get(
            _chart(id_b, "/sections/notes"),
            headers=_staff_headers(clinician),
            params={"encounter_id": encounter.json()["id"]},
        )
    ).status_code == 200


@requires_db
async def test_hardening_filters_pagination_timeline_audit_provenance(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    encounter_a_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    encounter_b_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    facility_id = new_id()
    other_facility = new_id()
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    async with db_engine.begin() as connection:
        for item_id, name, code in (
            (facility_id, "Ward A", "WA"),
            (other_facility, "Ward B", "WB"),
        ):
            await connection.execute(
                FacilityModel.__table__.insert().values(
                    id=item_id,
                    organization_id=clinician.organization_id,
                    name=name,
                    code=f"{code}{item_id.hex[:6].upper()}",
                    facility_type=FacilityType.CLINIC_SITE,
                    status=FacilityStatus.ACTIVE,
                )
            )
    null_fact = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    site_headers = {**clinician.headers(purpose="TREATMENT"), "X-Facility-Id": str(facility_id)}
    site_fact = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=site_headers,
        json=_pneumonia(patient_id, encounter_a_id),
    )
    other_site_headers = {
        **clinician.headers(purpose="TREATMENT"),
        "X-Facility-Id": str(other_facility),
    }
    other_site_fact = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=other_site_headers,
        json=_pneumonia(patient_id, encounter_b_id),
    )
    assert null_fact.status_code in {200, 201}
    assert site_fact.status_code in {200, 201}
    assert other_site_fact.status_code in {200, 201}
    await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_generic_exam_observation(patient_id, encounter_a_id),
    )
    await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id),
    )
    await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id),
    )
    await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id),
    )
    await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id),
    )
    await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id),
    )
    extra_site = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=site_headers,
        json=_pneumonia(patient_id, encounter_a_id),
    )
    assert extra_site.status_code in {200, 201}
    for _ in range(12):
        extra = await db_client.post(
            "/api/v1/clinical/conditions",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_pneumonia(patient_id),
        )
        assert extra.status_code in {200, 201}

    async with db_engine.connect() as connection:
        provenance_before = (
            await connection.execute(select(func.count()).select_from(ClinicalProvenanceModel))
        ).scalar_one()

    org_ids = {
        item["id"]
        for item in (
            await db_client.get(
                _chart(patient_id, "/sections/conditions"), headers=_staff_headers(clinician)
            )
        ).json()["items"]
    }
    assert null_fact.json()["id"] in org_ids
    assert site_fact.json()["id"] in org_ids
    filtered_ids = {
        item["id"]
        for item in (
            await db_client.get(
                _chart(patient_id, "/sections/conditions"),
                headers=_staff_headers(clinician),
                params={"facility_id": str(facility_id)},
            )
        ).json()["items"]
    }
    assert site_fact.json()["id"] in filtered_ids
    assert null_fact.json()["id"] not in filtered_ids
    assert other_site_fact.json()["id"] not in filtered_ids
    assert (
        await db_client.get(
            _chart(patient_id, "/sections/conditions"),
            headers=_staff_headers(clinician),
            params={"facility_id": str(other.organization_id)},
        )
    ).status_code == 404

    summary_a = await db_client.get(
        _chart(patient_id, "/summary"),
        headers=_staff_headers(clinician),
        params={"encounter_id": encounter_a_id},
    )
    assert summary_a.status_code == 200
    assert len(summary_a.json().get("active_conditions", [])) <= 10
    assert (
        await db_client.get(
            _chart(patient_id, "/summary"),
            headers=_staff_headers(clinician),
            params={"encounter_id": str(uuid4())},
        )
    ).status_code == 404
    summary_facility = await db_client.get(
        _chart(patient_id, "/summary"),
        headers=_staff_headers(clinician),
        params={"facility_id": str(facility_id)},
    )
    for item in summary_facility.json().get("active_conditions", []):
        assert item["source_id"] != null_fact.json()["id"]
        assert "source_type" in item

    page1 = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"limit": 5},
    )
    page2 = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"limit": 5, "cursor": page1.json()["next_cursor"]},
    )
    page3 = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"limit": 5, "cursor": page2.json()["next_cursor"]},
    )
    paged_ids = [item["id"] for item in page1.json()["items"]]
    paged_ids.extend(item["id"] for item in page2.json()["items"])
    paged_ids.extend(item["id"] for item in page3.json()["items"])
    assert len(paged_ids) == len(set(paged_ids))
    assert page1.json()["has_more"] is True

    timeline1 = await db_client.get(
        _chart(patient_id, "/timeline"),
        headers=_staff_headers(clinician),
        params={"limit": 8},
    )
    assert "body_text" not in timeline1.json()["items"][0]
    timeline2 = await db_client.get(
        _chart(patient_id, "/timeline"),
        headers=_staff_headers(clinician),
        params={"limit": 8, "cursor": timeline1.json()["next_cursor"]},
    )
    t_ids = [item["source_id"] for item in timeline1.json()["items"]]
    t_ids.extend(item["source_id"] for item in timeline2.json()["items"])
    assert len(t_ids) == len(set(t_ids))
    again = await db_client.get(
        _chart(patient_id, "/timeline"),
        headers=_staff_headers(clinician),
        params={"limit": 8},
    )
    assert [item["source_id"] for item in again.json()["items"]] == [
        item["source_id"] for item in timeline1.json()["items"]
    ]
    other_patient = await _active_patient(db_client, registrar)
    reused = await db_client.get(
        _chart(other_patient, "/timeline"),
        headers=_staff_headers(clinician),
        params={"cursor": timeline1.json()["next_cursor"]},
    )
    assert reused.status_code == 200
    assert {item["source_id"] for item in reused.json()["items"]}.isdisjoint(set(t_ids))

    facility_page = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"facility_id": str(facility_id), "limit": 1},
    )
    assert facility_page.status_code == 200
    facility_cursor = facility_page.json()["next_cursor"]
    assert facility_cursor
    crossed_facility = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"facility_id": str(other_facility), "cursor": facility_cursor},
    )
    assert crossed_facility.status_code == 200
    crossed_ids = {item["id"] for item in crossed_facility.json()["items"]}
    assert site_fact.json()["id"] not in crossed_ids
    assert extra_site.json()["id"] not in crossed_ids
    assert null_fact.json()["id"] not in crossed_ids

    inverted = await db_client.get(
        _chart(patient_id, "/timeline"),
        headers=_staff_headers(clinician),
        params={
            "recorded_from": "2026-12-31T00:00:00Z",
            "recorded_to": "2020-01-01T00:00:00Z",
        },
    )
    assert inverted.status_code == 200
    assert inverted.json()["items"] == []

    concurrent = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    assert concurrent.status_code in {200, 201}
    after_write = await db_client.get(
        _chart(patient_id, "/sections/conditions"),
        headers=_staff_headers(clinician),
        params={"limit": 5, "cursor": page1.json()["next_cursor"]},
    )
    assert after_write.status_code == 200

    async with db_engine.connect() as connection:
        provenance_after = (
            await connection.execute(select(func.count()).select_from(ClinicalProvenanceModel))
        ).scalar_one()
        audits = (
            (
                await connection.execute(
                    text(
                        "SELECT metadata FROM audit_events "
                        "WHERE action = 'CLINICAL_CHART_ACCESSED' AND patient_id = :pid"
                    ),
                    {"pid": patient_id},
                )
            )
            .mappings()
            .all()
        )
        section_extra = (
            await connection.execute(
                text(
                    "SELECT count(*) FROM audit_events "
                    "WHERE action = 'CLINICAL_CHART_ACCESSED' AND patient_id = :pid "
                    "AND metadata->>'surface' = 'section'"
                ),
                {"pid": patient_id},
            )
        ).scalar_one()
    assert provenance_after == provenance_before + 1
    surfaces = {row["metadata"].get("surface") for row in audits}
    assert {"summary", "timeline"} <= surfaces
    assert section_extra == 0
    for row in audits:
        blob = json.dumps(row["metadata"]).lower()
        assert "nik" not in blob
        assert "bpjs" not in blob
        assert "bearer" not in blob
        assert "mrn" not in blob
