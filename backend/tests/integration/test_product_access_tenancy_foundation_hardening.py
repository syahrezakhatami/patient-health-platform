import asyncio
import hashlib
import inspect
import os
from pathlib import Path
from uuid import uuid4

import pytest
from app.api.v1 import patient as patient_api
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.modules.patient_access.application.services import PatientAccessService
from app.modules.patient_access.infrastructure.repositories import PatientAccountRepository
from app.shared.types.ids import new_id
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import mint_token
from tests.integration.clinical_notes import (
    create_note_body,
    finalize_note_body,
    new_idempotency_key,
    note_write_headers,
    update_note_body,
)
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_product_access_tenancy_foundation import (
    _identity_payload,
    _patient_headers,
)
from tests.integration.test_wave1_mpi import merge_evidence, unique_mrn, unique_nik
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave2b1_condition import _pneumonia
from tests.integration.test_wave2b2a_observation import _generic_exam_observation
from tests.integration.test_wave2b2b_laboratory import _glucose, _lab_order
from tests.integration.test_wave2b3a_medication import _paracetamol
from tests.integration.test_wave2b3b_allergy import _amend_body as _allergy_amend
from tests.integration.test_wave2b3b_allergy import _penicillin
from tests.integration.test_wave2b3c_consent import _consent
from tests.integration.test_wave2b4_immunization import _amend_body as _imm_amend
from tests.integration.test_wave2b4_immunization import _vaccine
from tests.integration.test_wave2b5_procedure import _amend_body as _proc_amend
from tests.integration.test_wave2b5_procedure import _procedure
from tests.integration.test_wave2b6_medical_device import _amend_body as _device_amend
from tests.integration.test_wave2b6_medical_device import _device
from tests.integration.test_wave2b7_adverse_event import _amend_body as _ae_amend
from tests.integration.test_wave2b7_adverse_event import _event
from tests.integration.test_wave2b8_family_history import _amend_body as _fh_amend
from tests.integration.test_wave2b8_family_history import _history

pytestmark = pytest.mark.integration

APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)
WAVE1_SHA256 = "f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd"
APP_ROOT = Path(__file__).resolve().parents[2] / "app"


def _assert_no_leak(response) -> None:
    text_body = response.text.lower()
    assert "traceback" not in text_body
    assert "sqlalchemy" not in text_body
    assert "password" not in text_body
    assert "bpjs" not in text_body
    assert "bearer " not in text_body
    assert "php-patient" not in text_body or "aud" not in text_body


async def _assert_status(response, expected: int, *, path: str) -> None:
    assert response.status_code == expected, (path, response.status_code, response.text[:500])
    if expected in {401, 403, 404}:
        _assert_no_leak(response)


async def _bind(db_client, organization_id, identity_id: str, *, subject: str | None = None):
    token_subject = subject or f"patient-{uuid4()}"
    token = mint_token(sub=token_subject, aud="php-patient")
    headers = _patient_headers(token, organization_id)
    created = await db_client.post(
        "/api/v1/patient/accounts",
        headers=headers,
        json={"patient_identity_id": identity_id},
    )
    return token_subject, token, headers, created


def test_wave1_pdp_checksum_matches_published_baseline() -> None:
    source = (APP_ROOT / "modules" / "authorization" / "application" / "wave1_pdp.py").read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    assert digest == WAVE1_SHA256


def test_production_code_instantiates_wave1_pdp_only_from_wrapper() -> None:
    holders: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        text_body = path.read_text(encoding="utf-8")
        if "Wave1PolicyPDP()" not in text_body:
            continue
        holders.append(str(path.relative_to(APP_ROOT)))
    assert holders == ["modules/authorization/application/product_access_pdp.py"]
    default_source = (APP_ROOT / "core" / "dependencies.py").read_text(encoding="utf-8")
    assert "def default_pdp() -> ProductAccessPDP" in default_source
    assert "Wave1PolicyPDP()" not in default_source


def test_patient_api_surface_is_minimum_access_foundation() -> None:
    paths = sorted({route.path for route in patient_api.router.routes})
    assert paths == ["/patient/accounts", "/patient/me", "/patient/record-access"]
    source = inspect.getsource(patient_api)
    assert "/fhir" not in source
    assert "/api/v2" not in source
    assert "nik" not in source.lower()
    assert "bpjs" not in source.lower()
    assert "search" not in source.lower()


def test_account_locks_are_select_for_update_not_redis() -> None:
    repo = inspect.getsource(PatientAccountRepository)
    service = inspect.getsource(PatientAccessService)
    assert "with_for_update" in repo
    assert "redis" not in service.lower()
    assert "Wave1PolicyPDP()" not in service


def test_migration_0018_revises_0017_and_adds_binding_trigger() -> None:
    migration = (
        Path(__file__).resolve().parents[2]
        / "alembic"
        / "versions"
        / "20260814_0018_product_access_tenancy.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str | None = "20260814_0017"' in migration
    assert "prevent_patient_account_rebinding" in migration
    assert "subject is immutable" in migration
    assert "cannot be reactivated" in migration
    assert "may only rebind to canonical survivor" in migration


@requires_db
async def test_patient_accounts_live_schema_privileges_and_catalog(db_engine) -> None:
    async with db_engine.connect() as connection:
        columns = await connection.execute(
            text(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'patient_accounts'
                """
            )
        )
        colmap = {row[0]: row[1] for row in columns}
        assert set(colmap) >= {
            "id",
            "subject",
            "patient_identity_id",
            "status",
            "created_at",
            "updated_at",
        }
        assert colmap["id"] == "uuid"
        assert "nik" not in colmap
        assert "bpjs" not in colmap
        assert "given_name" not in colmap
        pk = await connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid = 'patient_accounts'::regclass AND contype = 'p'
                """
            )
        )
        assert "id" in pk.scalar_one().lower()
        uniques = await connection.execute(
            text(
                """
                SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid = 'patient_accounts'::regclass AND contype = 'u'
                """
            )
        )
        unique_defs = {row[0]: row[1] for row in uniques}
        assert any("subject" in definition.lower() for definition in unique_defs.values())
        indexes = await connection.execute(
            text(
                """
                SELECT indexname, indexdef FROM pg_indexes
                WHERE tablename = 'patient_accounts'
                """
            )
        )
        index_sql = " ".join(row[1] for row in indexes).lower()
        assert "uq_patient_accounts_active_identity" in index_sql
        assert "status" in index_sql and "active" in index_sql
        fk = await connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid = 'patient_accounts'::regclass AND contype = 'f'
                """
            )
        )
        fk_def = fk.scalar_one()
        assert "patient_identities" in fk_def
        assert "RESTRICT" in fk_def.upper()
        checks = await connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) FROM pg_constraint
                WHERE conrelid = 'patient_accounts'::regclass AND contype = 'c'
                """
            )
        )
        check_sql = " ".join(row[0] for row in checks)
        assert "ACTIVE" in check_sql and "DISABLED" in check_sql
        trigger = await connection.execute(
            text(
                """
                SELECT tgname FROM pg_trigger
                WHERE tgrelid = 'patient_accounts'::regclass AND NOT tgisinternal
                """
            )
        )
        assert "trg_patient_accounts_binding_immutable" in {row[0] for row in trigger}
        leftover = await connection.execute(
            text(
                """
                SELECT p.code FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.code = 'PLATFORM_ADMIN'
                  AND (p.code LIKE 'clinical.%' OR p.code LIKE 'mpi.%' OR p.code LIKE 'patient.%')
                """
            )
        )
        assert leftover.all() == []
        patient_on_staff = await connection.execute(
            text(
                """
                SELECT r.code, p.code FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE p.code LIKE 'patient.%'
                """
            )
        )
        assert patient_on_staff.all() == []
        dups = await connection.execute(
            text(
                """
                SELECT code, count(*) FROM permissions GROUP BY code HAVING count(*) > 1
                """
            )
        )
        assert dups.all() == []

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            privs = await connection.execute(
                text(
                    """
                    SELECT privilege_type FROM information_schema.role_table_grants
                    WHERE table_name = 'patient_accounts' AND grantee = 'app_dml'
                    """
                )
            )
            granted = {row[0] for row in privs}
            assert {"SELECT", "INSERT", "UPDATE"} <= granted
            assert "DELETE" not in granted
            assert "TRUNCATE" not in granted
    finally:
        await engine.dispose()


@requires_db
async def test_platform_admin_is_denied_across_frozen_clinical_apis(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]
    note = await db_client.post(
        "/api/v1/clinical/notes",
        headers=note_write_headers(clinician, idempotency_key=new_idempotency_key("plat")),
        json=create_note_body(patient_id, encounter_id, body_text="clinician note"),
    )
    condition = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    observation = await db_client.post(
        "/api/v1/clinical/observations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_generic_exam_observation(patient_id, encounter_id),
    )
    order = await db_client.post(
        "/api/v1/clinical/laboratory/orders",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_lab_order(patient_id, encounter_id),
    )
    specimen = await db_client.post(
        "/api/v1/clinical/laboratory/specimens",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"laboratory_order_id": order.json()["id"], "specimen_type": "BLOOD"},
    )
    result = await db_client.post(
        "/api/v1/clinical/laboratory/results",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_glucose(specimen.json()["id"]),
    )
    medication = await db_client.post(
        "/api/v1/clinical/medications",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_paracetamol(patient_id, encounter_id),
    )
    allergy = await db_client.post(
        "/api/v1/clinical/allergies",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_penicillin(patient_id),
    )
    consent = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    immunization = await db_client.post(
        "/api/v1/clinical/immunizations",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_vaccine(patient_id),
    )
    procedure = await db_client.post(
        "/api/v1/clinical/procedures",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_procedure(patient_id),
    )
    device = await db_client.post(
        "/api/v1/clinical/medical-devices",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_device(patient_id),
    )
    adverse = await db_client.post(
        "/api/v1/clinical/adverse-events",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_event(patient_id),
    )
    family = await db_client.post(
        "/api/v1/clinical/family-histories",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_history(patient_id),
    )
    for item in (
        note,
        condition,
        observation,
        order,
        specimen,
        result,
        medication,
        allergy,
        consent,
        immunization,
        procedure,
        device,
        adverse,
        family,
    ):
        assert item.status_code in {200, 201}, item.text[:300]

    headers = platform.headers(purpose="TREATMENT")
    headers["Idempotency-Key"] = new_idempotency_key("plat-deny")
    ids = {
        "encounter": encounter_id,
        "note": note.json()["id"],
        "condition": condition.json()["id"],
        "observation": observation.json()["id"],
        "order": order.json()["id"],
        "specimen": specimen.json()["id"],
        "result": result.json()["id"],
        "medication": medication.json()["id"],
        "allergy": allergy.json()["id"],
        "consent": consent.json()["id"],
        "immunization": immunization.json()["id"],
        "procedure": procedure.json()["id"],
        "device": device.json()["id"],
        "adverse": adverse.json()["id"],
        "family": family.json()["id"],
    }
    calls = [
        (
            "post",
            "/api/v1/clinical/encounters",
            {"json": {"patient_identity_id": patient_id, "encounter_class": "AMB"}},
        ),
        ("get", "/api/v1/clinical/encounters", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/encounters/{ids['encounter']}", {}),
        (
            "post",
            f"/api/v1/clinical/encounters/{ids['encounter']}/status",
            {"json": {"status": "FINISHED"}},
        ),
        (
            "post",
            "/api/v1/clinical/notes",
            {
                "json": create_note_body(patient_id, encounter_id, body_text="platform"),
            },
        ),
        ("get", f"/api/v1/clinical/notes/{ids['note']}", {}),
        (
            "post",
            f"/api/v1/clinical/notes/{ids['note']}",
            {"json": update_note_body(patient_id, 1, "edit")},
        ),
        (
            "post",
            f"/api/v1/clinical/notes/{ids['note']}/finalize",
            {"json": finalize_note_body(patient_id)},
        ),
        ("post", f"/api/v1/clinical/notes/{ids['note']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/conditions", {"json": _pneumonia(patient_id)}),
        ("get", "/api/v1/clinical/conditions", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/conditions/{ids['condition']}", {}),
        (
            "post",
            f"/api/v1/clinical/conditions/{ids['condition']}/status",
            {"json": {"clinical_status": "RESOLVED"}},
        ),
        ("post", f"/api/v1/clinical/conditions/{ids['condition']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/observations", {"json": _generic_exam_observation(patient_id)}),
        ("get", "/api/v1/clinical/observations", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/observations/{ids['observation']}", {}),
        (
            "post",
            f"/api/v1/clinical/observations/{ids['observation']}/amend",
            {
                "json": {
                    "value_type": "NUMERIC",
                    "value_numeric": 80,
                    "unit": "beats/min",
                }
            },
        ),
        ("post", f"/api/v1/clinical/observations/{ids['observation']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/laboratory/orders", {"json": _lab_order(patient_id)}),
        (
            "get",
            "/api/v1/clinical/laboratory/orders",
            {"params": {"patient_identity_id": patient_id}},
        ),
        ("get", f"/api/v1/clinical/laboratory/orders/{ids['order']}", {}),
        ("post", f"/api/v1/clinical/laboratory/orders/{ids['order']}/cancel", {}),
        ("post", f"/api/v1/clinical/laboratory/orders/{ids['order']}/entered-in-error", {}),
        (
            "post",
            "/api/v1/clinical/laboratory/specimens",
            {"json": {"laboratory_order_id": ids["order"], "specimen_type": "BLOOD"}},
        ),
        (
            "get",
            "/api/v1/clinical/laboratory/specimens",
            {"params": {"patient_identity_id": patient_id}},
        ),
        ("get", f"/api/v1/clinical/laboratory/specimens/{ids['specimen']}", {}),
        ("post", f"/api/v1/clinical/laboratory/specimens/{ids['specimen']}/reject", {}),
        ("post", f"/api/v1/clinical/laboratory/specimens/{ids['specimen']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/laboratory/results", {"json": _glucose(ids["specimen"])}),
        (
            "get",
            "/api/v1/clinical/laboratory/results",
            {"params": {"patient_identity_id": patient_id}},
        ),
        ("get", f"/api/v1/clinical/laboratory/results/{ids['result']}", {}),
        (
            "post",
            f"/api/v1/clinical/laboratory/results/{ids['result']}/amend",
            {
                "json": {
                    "value_type": "NUMERIC",
                    "value_numeric": 5.5,
                    "unit": "mmol/L",
                }
            },
        ),
        ("post", f"/api/v1/clinical/laboratory/results/{ids['result']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/medications", {"json": _paracetamol(patient_id)}),
        ("get", "/api/v1/clinical/medications", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/medications/{ids['medication']}", {}),
        ("post", f"/api/v1/clinical/medications/{ids['medication']}/stop", {}),
        ("post", f"/api/v1/clinical/medications/{ids['medication']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/allergies", {"json": _penicillin(patient_id)}),
        ("get", "/api/v1/clinical/allergies", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/allergies/{ids['allergy']}", {}),
        ("post", f"/api/v1/clinical/allergies/{ids['allergy']}/amend", {"json": _allergy_amend()}),
        ("post", f"/api/v1/clinical/allergies/{ids['allergy']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/consents", {"json": _consent(patient_id)}),
        ("get", "/api/v1/clinical/consents", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/consents/{ids['consent']}", {}),
        (
            "post",
            f"/api/v1/clinical/consents/{ids['consent']}/amend",
            {"json": {"note_text": "platform"}},
        ),
        ("post", f"/api/v1/clinical/consents/{ids['consent']}/revoke", {}),
        ("post", f"/api/v1/clinical/consents/{ids['consent']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/immunizations", {"json": _vaccine(patient_id)}),
        ("get", "/api/v1/clinical/immunizations", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/immunizations/{ids['immunization']}", {}),
        (
            "post",
            f"/api/v1/clinical/immunizations/{ids['immunization']}/amend",
            {"json": _imm_amend()},
        ),
        ("post", f"/api/v1/clinical/immunizations/{ids['immunization']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/procedures", {"json": _procedure(patient_id)}),
        ("get", "/api/v1/clinical/procedures", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/procedures/{ids['procedure']}", {}),
        (
            "post",
            f"/api/v1/clinical/procedures/{ids['procedure']}/amend",
            {"json": _proc_amend()},
        ),
        ("post", f"/api/v1/clinical/procedures/{ids['procedure']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/medical-devices", {"json": _device(patient_id)}),
        (
            "get",
            "/api/v1/clinical/medical-devices",
            {"params": {"patient_identity_id": patient_id}},
        ),
        ("get", f"/api/v1/clinical/medical-devices/{ids['device']}", {}),
        (
            "post",
            f"/api/v1/clinical/medical-devices/{ids['device']}/amend",
            {"json": _device_amend()},
        ),
        ("post", f"/api/v1/clinical/medical-devices/{ids['device']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/adverse-events", {"json": _event(patient_id)}),
        ("get", "/api/v1/clinical/adverse-events", {"params": {"patient_identity_id": patient_id}}),
        ("get", f"/api/v1/clinical/adverse-events/{ids['adverse']}", {}),
        (
            "post",
            f"/api/v1/clinical/adverse-events/{ids['adverse']}/amend",
            {"json": _ae_amend()},
        ),
        ("post", f"/api/v1/clinical/adverse-events/{ids['adverse']}/entered-in-error", {}),
        ("post", "/api/v1/clinical/family-histories", {"json": _history(patient_id)}),
        (
            "get",
            "/api/v1/clinical/family-histories",
            {"params": {"patient_identity_id": patient_id}},
        ),
        ("get", f"/api/v1/clinical/family-histories/{ids['family']}", {}),
        (
            "post",
            f"/api/v1/clinical/family-histories/{ids['family']}/amend",
            {"json": _fh_amend()},
        ),
        ("post", f"/api/v1/clinical/family-histories/{ids['family']}/entered-in-error", {}),
    ]
    for method, path, kwargs in calls:
        response = await getattr(db_client, method)(path, headers=headers, **kwargs)
        await _assert_status(response, 403, path=path)


@requires_db
async def test_platform_admin_is_denied_across_mpi_phi_operations(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=registrar.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    assert created.status_code in {200, 201}
    patient_id = created.json()["id"]
    identifier_id = created.json()["identifiers"][0]["id"]
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    assert anonymous.status_code in {200, 201}
    headers = platform.headers(purpose="IDENTITY_RESOLUTION")
    admin_headers = platform.headers(purpose="ADMINISTRATION")
    evidence = merge_evidence("HARDEN-MPI")
    calls = [
        (
            "post",
            "/api/v1/mpi/identities",
            registrar.headers(),
            {"json": _identity_payload(unique_nik())},
        ),
        (
            "post",
            "/api/v1/mpi/identities/anonymous",
            platform.headers(purpose="EMERGENCY"),
            {"json": {}},
        ),
        (
            "post",
            "/api/v1/mpi/identities/lookup",
            headers,
            {
                "json": {
                    "identifier_system": "id.nik",
                    "identifier_type": "NIK",
                    "identifier_value": unique_nik(),
                }
            },
        ),
        ("get", f"/api/v1/mpi/identities/{patient_id}", admin_headers, {}),
        (
            "post",
            f"/api/v1/mpi/identities/{patient_id}/identifiers",
            headers,
            {
                "json": {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("H"),
                }
            },
        ),
        (
            "post",
            f"/api/v1/mpi/identities/{anonymous.json()['id']}/identify",
            headers,
            {"json": {**_identity_payload(unique_nik()), "reason": "identified"}},
        ),
        (
            "post",
            f"/api/v1/mpi/identifiers/{identifier_id}/verify",
            headers,
            {"json": {"method": "document_inspection"}},
        ),
        (
            "post",
            f"/api/v1/mpi/identifiers/{identifier_id}/reject",
            headers,
            {"json": {"method": "document_inspection"}},
        ),
        (
            "post",
            "/api/v1/mpi/match",
            headers,
            {"json": {"given_name": "Ada", "family_name": "Patient", "birth_date": "1991-02-02"}},
        ),
        (
            "post",
            f"/api/v1/mpi/match-candidates/{uuid4()}/review",
            headers,
            {"json": {"decision": "CONFIRMED_MATCH", "reason": "review"}},
        ),
        (
            "post",
            "/api/v1/mpi/merge",
            headers,
            {
                "json": {
                    "source_identity_id": str(uuid4()),
                    "target_identity_id": str(uuid4()),
                    "reason": "Duplicate registration confirmed by registrar",
                    "evidence": evidence,
                }
            },
        ),
        (
            "post",
            "/api/v1/mpi/unmerge",
            headers,
            {
                "json": {
                    "merge_operation_id": str(uuid4()),
                    "reason": "Undo merge after registrar review",
                    "evidence": evidence,
                }
            },
        ),
    ]
    for method, path, call_headers, kwargs in calls:
        if path == "/api/v1/mpi/identities":
            response = await db_client.post(path, headers=headers, **kwargs)
        else:
            response = await getattr(db_client, method)(path, headers=call_headers, **kwargs)
        await _assert_status(response, 403, path=path)
    still = await db_client.get(
        f"/api/v1/mpi/identities/{patient_id}",
        headers=officer.headers(),
    )
    await _assert_status(still, 200, path="officer mpi read")


@requires_db
async def test_stale_platform_phi_permission_is_still_denied(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    patient_id = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO role_permissions (id, role_id, permission_id)
                SELECT gen_random_uuid(), r.id, p.id
                FROM roles r
                JOIN permissions p
                  ON p.code IN ('clinical.condition.create', 'mpi.identity.read')
                WHERE r.code = 'PLATFORM_ADMIN'
                  AND NOT EXISTS (
                      SELECT 1 FROM role_permissions existing
                      WHERE existing.role_id = r.id AND existing.permission_id = p.id
                  )
                """
            )
        )
    try:
        clinical = await db_client.post(
            "/api/v1/clinical/conditions",
            headers=platform.headers(purpose="TREATMENT"),
            json=_pneumonia(patient_id),
        )
        await _assert_status(clinical, 403, path="stale clinical")
        mpi_read = await db_client.get(
            f"/api/v1/mpi/identities/{patient_id}",
            headers=platform.headers(purpose="ADMINISTRATION"),
        )
        await _assert_status(mpi_read, 403, path="stale mpi")
    finally:
        async with db_engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    DELETE FROM role_permissions
                    WHERE role_id = (SELECT id FROM roles WHERE code = 'PLATFORM_ADMIN')
                      AND permission_id IN (
                          SELECT id FROM permissions
                          WHERE code IN ('clinical.condition.create', 'mpi.identity.read')
                      )
                    """
                )
            )


@requires_db
async def test_platform_admin_cannot_escalate_to_clinical_roles(db_client, db_engine) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    other_platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    org_admin = await seed_actor(db_engine, role_code=RoleCode.ORG_ADMIN)
    target = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=org_admin.organization_id
    )
    headers = platform.headers(purpose="ADMINISTRATION")
    for role in (
        RoleCode.CLINICIAN,
        RoleCode.IDENTITY_OFFICER,
        RoleCode.REGISTRAR,
        RoleCode.AUDITOR,
        "clinician",
        "CLINICIAN ",
    ):
        denied = await db_client.post(
            "/api/v1/iam/memberships",
            headers=headers,
            json={
                "user_id": str(target.user_id),
                "organization_id": str(org_admin.organization_id),
                "role_code": role.strip() if isinstance(role, str) else role,
            },
        )
        assert denied.status_code in {403, 422}, (role, denied.status_code, denied.text)
        if denied.status_code == 403:
            _assert_no_leak(denied)
    self_assign = await db_client.post(
        "/api/v1/iam/memberships",
        headers=headers,
        json={
            "user_id": str(platform.user_id),
            "organization_id": str(org_admin.organization_id),
            "role_code": RoleCode.CLINICIAN,
        },
    )
    await _assert_status(self_assign, 403, path="self clinician")
    other = await db_client.post(
        "/api/v1/iam/memberships",
        headers=headers,
        json={
            "user_id": str(other_platform.user_id),
            "organization_id": str(org_admin.organization_id),
            "role_code": RoleCode.CLINICIAN,
        },
    )
    await _assert_status(other, 403, path="other platform clinician")
    patched = await db_client.patch(
        "/api/v1/iam/memberships",
        headers=headers,
        json={"role_code": RoleCode.CLINICIAN},
    )
    assert patched.status_code in {404, 405}
    org = await db_client.post(
        "/api/v1/organizations",
        headers=headers,
        json={
            "name": f"Bootstrap {uuid4().hex[:8]}",
            "code": f"B{uuid4().hex[:8].upper()}",
            "organization_type": "HOSPITAL",
        },
    )
    assert org.status_code in {200, 201}
    facility = await db_client.post(
        f"/api/v1/organizations/{org_admin.organization_id}/facilities",
        headers=headers,
        json={
            "name": "Ward",
            "code": f"F{uuid4().hex[:6].upper()}",
            "facility_type": "CLINIC_SITE",
        },
    )
    await _assert_status(facility, 403, path="platform facility")
    bootstrap = await db_client.post(
        "/api/v1/iam/memberships",
        headers=headers,
        json={
            "user_id": str(target.user_id),
            "organization_id": str(org_admin.organization_id),
            "role_code": RoleCode.ORG_ADMIN,
        },
    )
    assert bootstrap.status_code in {200, 201, 409}


@requires_db
async def test_direct_sql_cannot_rebind_subject_or_identity(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    first = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Owner"),
    )
    victim = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Victim"),
    )
    _, _, headers, bound = await _bind(db_client, registrar.organization_id, first.json()["id"])
    assert bound.status_code in {200, 201}
    account_id = bound.json()["id"]
    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="subject is immutable"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            UPDATE patient_accounts SET subject = :sub WHERE id = :id
                            """
                        ),
                        {"sub": f"stolen-{uuid4()}", "id": account_id},
                    )
            with pytest.raises(Exception, match="may only rebind to canonical survivor"):
                async with connection.begin():
                    await connection.execute(
                        text(
                            """
                            UPDATE patient_accounts
                            SET patient_identity_id = :victim
                            WHERE id = :id
                            """
                        ),
                        {"victim": victim.json()["id"], "id": account_id},
                    )
            with pytest.raises(Exception, match="cannot be deleted|permission denied"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM patient_accounts WHERE id = :id"),
                        {"id": account_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE patient_accounts"))
            async with connection.begin():
                await connection.execute(
                    text("UPDATE patient_accounts SET status = 'DISABLED' WHERE id = :id"),
                    {"id": account_id},
                )
            with pytest.raises(Exception, match="cannot be reactivated"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE patient_accounts SET status = 'ACTIVE' WHERE id = :id"),
                        {"id": account_id},
                    )
    finally:
        await engine.dispose()
    disabled = await db_client.get("/api/v1/patient/me", headers=headers)
    await _assert_status(disabled, 403, path="disabled me")


@requires_db
async def test_account_control_invariant_and_concurrent_bind(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    patient_id = identity.json()["id"]
    other = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Other"),
    )
    _, token_a, headers_a, first = await _bind(db_client, registrar.organization_id, patient_id)
    assert first.status_code in {200, 201}
    _, _, _, duplicate_identity = await _bind(db_client, registrar.organization_id, patient_id)
    assert duplicate_identity.status_code == 409
    same_subject = await db_client.post(
        "/api/v1/patient/accounts",
        headers=headers_a,
        json={"patient_identity_id": other.json()["id"]},
    )
    assert same_subject.status_code == 409
    third = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Race"),
    )
    race_id = third.json()["id"]

    async def bind_race(subject: str):
        return (await _bind(db_client, registrar.organization_id, race_id, subject=subject))[3]

    left, right = await asyncio.gather(
        bind_race(f"patient-{uuid4()}"),
        bind_race(f"patient-{uuid4()}"),
    )
    codes = sorted([left.status_code, right.status_code])
    assert codes in ([200, 409], [201, 409])


@requires_db
async def test_token_audience_principal_forgery_and_self_access(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    clinician = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=registrar.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    other_org = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    identity_a = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Alpha"),
    )
    identity_b = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Beta"),
    )
    foreign = await db_client.post(
        "/api/v1/mpi/identities",
        headers=other_org.headers(),
        json=_identity_payload(unique_nik(), given="Foreign"),
    )
    subject, token, headers, bound = await _bind(
        db_client, registrar.organization_id, identity_a.json()["id"]
    )
    assert bound.status_code in {200, 201}
    me = await db_client.get("/api/v1/patient/me", headers=headers)
    await _assert_status(me, 200, path="self me")
    access = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": identity_a.json()["id"]},
    )
    await _assert_status(access, 200, path="self record")
    other = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": identity_b.json()["id"]},
    )
    await _assert_status(other, 404, path="patient B")
    guess = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": str(uuid4())},
    )
    await _assert_status(guess, 404, path="uuid guess")
    assert identity_b.json()["id"] not in guess.text
    foreign_access = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": foreign.json()["id"]},
    )
    await _assert_status(foreign_access, 404, path="other org")
    tamper_org = await db_client.get(
        "/api/v1/patient/record-access",
        headers=_patient_headers(token, other_org.organization_id),
        params={"patient_identity_id": identity_a.json()["id"]},
    )
    await _assert_status(tamper_org, 404, path="org header tamper")
    spoof = mint_token(
        sub=subject,
        aud="php-patient",
        extra={
            "patient_identity_id": identity_b.json()["id"],
            "principal_type": "PATIENT",
        },
    )
    spoofed = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(spoof, registrar.organization_id),
    )
    await _assert_status(spoofed, 200, path="spoof claim")
    assert spoofed.json()["canonical_patient_identity_id"] == identity_a.json()["id"]
    unknown = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(
            mint_token(sub=f"missing-{uuid4()}", aud="php-patient"),
            registrar.organization_id,
        ),
    )
    await _assert_status(unknown, 403, path="unknown sub")
    malformed = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(mint_token(sub="", aud="php-patient"), registrar.organization_id),
    )
    assert malformed.status_code in {401, 403}
    staff_as_patient = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(
            mint_token(sub=clinician.subject, aud="php-patient"), registrar.organization_id
        ),
    )
    await _assert_status(staff_as_patient, 403, path="staff subject patient aud")
    platform_as_patient = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(
            mint_token(sub=platform.subject, aud="php-patient"), registrar.organization_id
        ),
    )
    await _assert_status(platform_as_patient, 403, path="platform subject patient aud")
    patient_on_staff = await db_client.get(
        f"/api/v1/clinical/conditions/{uuid4()}",
        headers=headers,
    )
    await _assert_status(patient_on_staff, 401, path="patient on clinical")
    patient_on_platform = await db_client.post(
        "/api/v1/organizations",
        headers=headers,
        json={
            "name": "Nope",
            "code": f"N{uuid4().hex[:6].upper()}",
            "organization_type": "HOSPITAL",
        },
    )
    await _assert_status(patient_on_platform, 401, path="patient on org")
    staff_on_patient = await db_client.get(
        "/api/v1/patient/me",
        headers=clinician.headers(purpose="PATIENT_ACCESS"),
    )
    await _assert_status(staff_on_patient, 401, path="staff on patient")
    platform_token = mint_token(sub=platform.subject, aud="php-platform")
    platform_on_patient = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(platform_token, registrar.organization_id),
    )
    await _assert_status(platform_on_patient, 401, path="platform aud on patient")
    platform_on_clinical = await db_client.post(
        "/api/v1/clinical/conditions",
        headers={
            "Authorization": f"Bearer {platform_token}",
            "X-Organization-Id": str(registrar.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json=_pneumonia(identity_a.json()["id"]),
    )
    await _assert_status(platform_on_clinical, 401, path="platform aud on clinical")
    mixed = mint_token(sub=subject, extra={"aud": ["php-api", "php-patient"]})
    mixed_resp = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(mixed, registrar.organization_id),
    )
    await _assert_status(mixed_resp, 401, path="mixed aud")
    forged_staff = mint_token(
        sub=clinician.subject,
        extra={"principal_type": "PATIENT"},
    )
    forged = await db_client.post(
        "/api/v1/clinical/conditions",
        headers={
            "Authorization": f"Bearer {forged_staff}",
            "X-Organization-Id": str(registrar.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json=_pneumonia(identity_a.json()["id"]),
    )
    assert forged.status_code in {200, 201}
    platform_org_header = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=platform.headers(purpose="TREATMENT"),
        json=_pneumonia(identity_a.json()["id"]),
    )
    await _assert_status(platform_org_header, 403, path="platform not clinician")


@requires_db
async def test_purpose_tenant_facility_and_permissions(db_client, db_engine) -> None:
    hospital = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    clinic = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=hospital.organization_id
    )
    registrar_b = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinic.organization_id
    )
    patient_id = await _active_patient(db_client, registrar_a)
    created = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=hospital.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    assert created.status_code in {200, 201}
    cross = await db_client.get(
        f"/api/v1/clinical/conditions/{created.json()['id']}",
        headers=clinic.headers(purpose="TREATMENT"),
    )
    await _assert_status(cross, 404, path="clinic to hospital")
    reverse = await db_client.get(
        f"/api/v1/mpi/identities/{patient_id}",
        headers=registrar_b.headers(),
    )
    await _assert_status(reverse, 404, path="hospital isolation")
    same_facility = new_id()
    foreign_facility = new_id()
    async with db_engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=same_facility,
                organization_id=hospital.organization_id,
                name="Same org ward",
                code=f"S{uuid4().hex[:6].upper()}",
                facility_type=FacilityType.CLINIC_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=foreign_facility,
                organization_id=clinic.organization_id,
                name="Foreign ward",
                code=f"X{uuid4().hex[:6].upper()}",
                facility_type=FacilityType.CLINIC_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
    local_headers = hospital.headers(purpose="TREATMENT")
    local_headers["X-Facility-Id"] = str(same_facility)
    local_ok = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=local_headers,
        json=_pneumonia(patient_id),
    )
    assert local_ok.status_code in {200, 201}
    foreign_headers = hospital.headers(purpose="TREATMENT")
    foreign_headers["X-Facility-Id"] = str(foreign_facility)
    foreign = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=foreign_headers,
        json=_pneumonia(patient_id),
    )
    await _assert_status(foreign, 404, path="empty list foreign facility")
    clinic_patient = await _active_patient(db_client, registrar_b)
    clinic_only = await db_client.get(
        f"/api/v1/mpi/identities/{clinic_patient}",
        headers=registrar_a.headers(),
    )
    await _assert_status(clinic_only, 404, path="facility header not global")
    _, token, headers, bound = await _bind(db_client, registrar_a.organization_id, patient_id)
    assert bound.status_code in {200, 201}
    missing = await db_client.get(
        "/api/v1/patient/me",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Organization-Id": str(registrar_a.organization_id),
        },
    )
    assert missing.status_code == 422
    unknown = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(token, registrar_a.organization_id, purpose="NOT_A_PURPOSE"),
    )
    assert unknown.status_code == 422
    wrong = await db_client.get(
        "/api/v1/patient/me",
        headers=_patient_headers(token, registrar_a.organization_id, purpose="TREATMENT"),
    )
    await _assert_status(wrong, 403, path="wrong purpose")
    me = await db_client.get("/api/v1/iam/users/me", headers=headers)
    await _assert_status(me, 401, path="patient iam me")


@requires_db
async def test_merge_collision_disables_both_controllers(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=registrar.organization_id
    )
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json={
            "given_name": "Source",
            "family_name": "Collision",
            "birth_date": "1991-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("COL"),
                }
            ],
        },
    )
    target = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Target"),
    )
    source_id = source.json()["id"]
    target_id = target.json()["id"]
    condition = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=(
            await seed_actor(
                db_engine, role_code=RoleCode.CLINICIAN, organization_id=registrar.organization_id
            )
        ).headers(purpose="TREATMENT"),
        json=_pneumonia(source_id),
    )
    assert condition.status_code in {200, 201}
    historical_patient = condition.json()["patient_identity_id"]
    _, _, headers_a, bound_a = await _bind(db_client, registrar.organization_id, source_id)
    _, _, headers_b, bound_b = await _bind(db_client, registrar.organization_id, target_id)
    assert bound_a.status_code in {200, 201}
    assert bound_b.status_code in {200, 201}
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": target_id,
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("COLLIDE-1"),
            "idempotency_key": f"collide-{source_id}",
        },
    )
    assert merge.status_code in {200, 201}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT patient_identity_id FROM conditions WHERE id = :id"),
            {"id": condition.json()["id"]},
        )
        assert str(row.scalar_one()) == historical_patient
    first = await db_client.get("/api/v1/patient/me", headers=headers_a)
    await _assert_status(first, 403, path="collision source me")
    second = await db_client.get("/api/v1/patient/me", headers=headers_b)
    await _assert_status(second, 403, path="collision target me")
    leak = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers_a,
        params={"patient_identity_id": target_id},
    )
    assert leak.status_code in {403, 404}
    _assert_no_leak(leak)
    async with db_engine.connect() as connection:
        statuses = await connection.execute(
            text(
                """
                SELECT status FROM patient_accounts
                WHERE id IN (:a, :b) ORDER BY status
                """
            ),
            {"a": bound_a.json()["id"], "b": bound_b.json()["id"]},
        )
        assert [row[0] for row in statuses] == ["DISABLED", "DISABLED"]


@requires_db
async def test_unique_merge_rebinds_and_keeps_cluster_history(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=registrar.organization_id
    )
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json={
            "given_name": "Only",
            "family_name": "Source",
            "birth_date": "1991-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("UNIQ"),
                }
            ],
        },
    )
    target = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik(), given="Survivor"),
    )
    source_id = source.json()["id"]
    target_id = target.json()["id"]
    _, _, headers, bound = await _bind(db_client, registrar.organization_id, source_id)
    assert bound.status_code in {200, 201}
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": target_id,
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("UNIQ-1"),
            "idempotency_key": f"uniq-{source_id}",
        },
    )
    assert merge.status_code in {200, 201}
    me = await db_client.get("/api/v1/patient/me", headers=headers)
    await _assert_status(me, 200, path="unique merge me")
    assert me.json()["canonical_patient_identity_id"] == target_id
    historical = await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": source_id},
    )
    await _assert_status(historical, 200, path="cluster historical")
    assert source_id in historical.json()["cluster_identity_ids"]


@requires_db
async def test_retired_and_anonymous_remain_ineligible_without_leak(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    clinician = await seed_actor(
        db_engine, role_code=RoleCode.CLINICIAN, organization_id=registrar.organization_id
    )
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    assert anonymous.status_code in {200, 201}
    emergency = await _open_encounter(db_client, clinician, anonymous.json()["id"], "EMER")
    assert emergency.status_code in {200, 201}
    anon_bind = await db_client.post(
        "/api/v1/patient/accounts",
        headers=_patient_headers(
            mint_token(sub=f"patient-{uuid4()}", aud="php-patient"),
            registrar.organization_id,
        ),
        json={"patient_identity_id": anonymous.json()["id"]},
    )
    assert anon_bind.status_code == 409
    _assert_no_leak(anon_bind)
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    patient_id = identity.json()["id"]
    _, _, headers, bound = await _bind(db_client, registrar.organization_id, patient_id)
    assert bound.status_code in {200, 201}
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": patient_id},
        )
    retired_me = await db_client.get("/api/v1/patient/me", headers=headers)
    await _assert_status(retired_me, 403, path="retired me")
    _assert_no_leak(retired_me)


@requires_db
async def test_no_clinical_provenance_for_access_operations(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    patient_id = identity.json()["id"]
    async with db_engine.connect() as connection:
        before = await connection.execute(text("SELECT count(*) FROM clinical_provenances"))
        start = before.scalar_one()
    _, _, headers, bound = await _bind(db_client, registrar.organization_id, patient_id)
    assert bound.status_code in {200, 201}
    await db_client.get("/api/v1/patient/me", headers=headers)
    await db_client.get(
        "/api/v1/patient/record-access",
        headers=headers,
        params={"patient_identity_id": patient_id},
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    await db_client.post(
        "/api/v1/clinical/conditions",
        headers=platform.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    async with db_engine.connect() as connection:
        after = await connection.execute(text("SELECT count(*) FROM clinical_provenances"))
        assert after.scalar_one() == start
        bound_audit = await connection.execute(
            text(
                """
                SELECT action, result FROM audit_events
                WHERE resource_id = :id AND action = 'PATIENT_ACCOUNT_BOUND'
                """
            ),
            {"id": bound.json()["id"]},
        )
        row = bound_audit.first()
        assert row is not None
        assert row[1] == "SUCCESS"


@requires_db
async def test_inherited_denied_audit_rollback_still_present(db_client, db_engine) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    patient_id = (
        await db_client.post(
            "/api/v1/mpi/identities",
            headers=registrar.headers(),
            json=_identity_payload(unique_nik()),
        )
    ).json()["id"]
    denied = await db_client.post(
        "/api/v1/clinical/conditions",
        headers=platform.headers(purpose="TREATMENT"),
        json=_pneumonia(patient_id),
    )
    await _assert_status(denied, 403, path="platform condition")
    async with db_engine.connect() as connection:
        rows = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE action = 'clinical.condition.create' AND result = 'DENIED'
                """
            )
        )
        assert rows.scalar_one() == 0


@requires_db
async def test_concurrent_reactivation_sql_fails(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    identity = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    _, _, _, bound = await _bind(db_client, registrar.organization_id, identity.json()["id"])
    assert bound.status_code in {200, 201}
    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE patient_accounts SET status = 'DISABLED' WHERE id = :id"),
                {"id": bound.json()["id"]},
            )

        async def reactivate():
            async with engine.connect() as connection:
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE patient_accounts SET status = 'ACTIVE' WHERE id = :id"),
                        {"id": bound.json()["id"]},
                    )

        results = await asyncio.gather(reactivate(), reactivate(), return_exceptions=True)
        assert all(isinstance(item, Exception) for item in results)
        async with db_engine.connect() as connection:
            status = await connection.execute(
                text("SELECT status FROM patient_accounts WHERE id = :id"),
                {"id": bound.json()["id"]},
            )
            assert status.scalar_one() == "DISABLED"
    finally:
        await engine.dispose()
