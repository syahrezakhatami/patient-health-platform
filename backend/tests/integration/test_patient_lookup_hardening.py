import inspect
from pathlib import Path
from uuid import uuid4

import jwt
import pytest
from app.api.v1.mpi import lookup_identity
from app.api.v1.mpi import lookup_patients as lookup_patients_route
from app.api.v1.schemas import PatientLookupRequest
from app.core.errors import AppError, register_exception_handlers
from app.core.logging import _redact_secrets
from app.infra.rate_limit import RateLimitMiddleware
from app.main import create_app
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.authorization.domain.purpose import Purpose, parse_purpose
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.jwt_oidc_validator import JwtOidcTokenValidator
from app.modules.iam.infrastructure.models import (
    OrganizationMembershipModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)
from app.modules.mpi.application import services as mpi_services
from app.modules.mpi.domain.canonical import MAX_SURVIVOR_HOPS, resolve_canonical_id
from app.modules.mpi.domain.enums import IdentifierType, IdentityLifecycle, PatientLookupType
from app.modules.mpi.domain.identifiers import mask_identifier, normalize_identifier
from app.modules.mpi.domain.merge import validate_merge
from app.modules.mpi.infrastructure.repositories import MpiRepository
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select, text
from tests.conftest import make_settings, mint_token
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_patient_lookup import (
    _LOOKUP,
    _assert_no_clinical_payload,
    _bpjs_payload,
    _create_identity,
    _lookup_body,
    _mrn_payload,
    _nik_payload,
    _verify_first_identifier,
    unique_bpjs,
)
from tests.integration.test_wave1_mpi import merge_evidence, unique_mrn, unique_nik

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _mpi_py() -> str:
    return (_REPO_ROOT / "backend/app/api/v1/mpi.py").read_text(encoding="utf-8")


def _services_py() -> str:
    return (_REPO_ROOT / "backend/app/modules/mpi/application/services.py").read_text(
        encoding="utf-8"
    )


def _repo_py() -> str:
    return (_REPO_ROOT / "backend/app/modules/mpi/infrastructure/repositories.py").read_text(
        encoding="utf-8"
    )


async def _counts(db_engine) -> dict[str, int]:
    async with db_engine.connect() as connection:
        row = (
            await connection.execute(
                text(
                    """
                    SELECT
                      (SELECT count(*) FROM patient_identities),
                      (SELECT count(*) FROM patient_identifiers),
                      (SELECT count(*) FROM identity_clusters),
                      (SELECT count(*) FROM identity_cluster_members),
                      (SELECT count(*) FROM identity_match_candidates),
                      (SELECT count(*) FROM identity_merge_operations),
                      (SELECT count(*) FROM identity_provenances),
                      (SELECT count(*) FROM audit_events),
                      (SELECT count(*) FROM clinical_provenances)
                    """
                )
            )
        ).one()
    keys = (
        "patient_identities",
        "patient_identifiers",
        "identity_clusters",
        "identity_cluster_members",
        "identity_match_candidates",
        "identity_merge_operations",
        "identity_provenances",
        "audit_events",
        "clinical_provenances",
    )
    return {key: int(value) for key, value in zip(keys, row, strict=True)}


async def _lookup_audit_rows(db_engine, actor_id):
    async with db_engine.connect() as connection:
        return (
            await connection.execute(
                text(
                    "SELECT action, metadata::text, patient_id::text, purpose "
                    "FROM audit_events WHERE actor_id = :actor AND action IN "
                    "('PATIENT_LOOKUP_ACCESSED', 'CLINICAL_CHART_ACCESSED')"
                ),
                {"actor": actor_id},
            )
        ).all()


async def seed_clinical_without_mpi(engine, organization_id):
    role_id = new_id()
    user_id = new_id()
    subject = f"user-{new_id()}"
    code = f"HNOMPI{role_id.hex[:8]}".upper()
    async with engine.begin() as connection:
        permission_id = (
            await connection.execute(
                select(PermissionModel.id).where(
                    PermissionModel.code == Permission.CLINICAL_CONDITION_READ
                )
            )
        ).scalar_one()
        await connection.execute(
            RoleModel.__table__.insert().values(id=role_id, code=code, name="Clinical without MPI")
        )
        await connection.execute(
            RolePermissionModel.__table__.insert().values(
                id=new_id(), role_id=role_id, permission_id=permission_id
            )
        )
        await connection.execute(
            UserModel.__table__.insert().values(
                id=user_id,
                subject=subject,
                display_name=subject,
                status=UserStatus.ACTIVE,
            )
        )
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=user_id,
                organization_id=organization_id,
                facility_id=None,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    return SeededActor(user_id, subject, organization_id, mint_token(sub=subject))


def test_request_schema_forbids_tenant_injection_fields() -> None:
    fields = set(PatientLookupRequest.model_fields)
    assert fields == {"lookup_type", "lookup_value"}
    assert PatientLookupRequest.model_config.get("extra") == "forbid"
    for extra in (
        {"organization_id": str(uuid4())},
        {"identifier_organization_id": str(uuid4())},
        {"tenant_id": str(uuid4())},
        {"facility_id": str(uuid4())},
        {"purpose": "TREATMENT"},
        {"role": "ORG_ADMIN"},
        {"permission": "mpi.identity.read"},
        {"patient_identity_id": str(uuid4())},
    ):
        with pytest.raises(ValidationError):
            PatientLookupRequest(
                lookup_type=PatientLookupType.MRN,
                lookup_value="MRN-1",
                **extra,
            )


def test_call_graph_uses_header_org_never_body_or_facility_filter() -> None:
    route = inspect.getsource(lookup_patients_route)
    assert "body.lookup_type" in route
    assert "body.lookup_value" in route
    assert "organization_id=organization_id" in route
    assert "body.organization_id" not in route
    repo = inspect.getsource(MpiRepository.find_active_identifiers_for_lookup)
    assert "facility_id" not in repo
    assert "LIKE" not in repo.upper()
    assert "ILIKE" not in repo.upper()
    identifier_lookup = inspect.getsource(mpi_services.MpiService._lookup_patients_by_identifier)
    assert "requires_organization(identifier_type)" in identifier_lookup
    assert "lookup_value" in identifier_lookup
    assert "body." not in identifier_lookup
    org_visible = inspect.getsource(mpi_services.MpiService._is_org_visible)
    assert "has_platform_scope" not in org_visible
    frozen = inspect.getsource(lookup_identity)
    assert "identifier_organization_id=body.identifier_organization_id" in frozen


def test_validation_handler_does_not_serialize_input() -> None:
    source = inspect.getsource(register_exception_handlers)
    assert "del exc" in source
    assert "exc.errors()" not in source
    assert "input" not in source.split("validation_handler")[1].split("http_handler")[0]


def test_rate_limiter_covers_lookup_and_omits_identifier() -> None:
    source = inspect.getsource(RateLimitMiddleware.dispatch)
    assert "/health/live" in source
    assert "patients/lookup" not in source
    assert "Too many requests" in source
    assert "lookup_value" not in source


def test_purpose_catalog_constants_and_normalization() -> None:
    assert Purpose.TREATMENT.value == "TREATMENT"
    assert Purpose.REGISTRATION.value == "REGISTRATION"
    assert Purpose.IDENTITY_RESOLUTION.value == "IDENTITY_RESOLUTION"
    assert Purpose.AUDIT.value == "AUDIT"
    assert parse_purpose("treatment") is Purpose.TREATMENT
    assert parse_purpose(" IDENTITY-RESOLUTION ") is Purpose.IDENTITY_RESOLUTION
    with pytest.raises(AppError):
        parse_purpose("NOT_A_PURPOSE")


def test_mask_identifier_never_returns_short_value_bare() -> None:
    assert mask_identifier("") == ""
    assert mask_identifier("12") == "********12"
    assert "1234567890123456" not in mask_identifier("1234567890123456")
    assert mask_identifier("1234567890123456").endswith("3456")
    assert mask_identifier("ab") != "ab"


def test_merge_walker_is_frozen_and_does_not_invent_chain_creation() -> None:
    assert MAX_SURVIVOR_HOPS == 8
    merge_src = inspect.getsource(validate_merge)
    assert "The target identity is already merged" in merge_src
    assert "The source identity is already merged" in merge_src
    a, b, c = uuid4(), uuid4(), uuid4()
    assert (
        resolve_canonical_id(
            a,
            status_of={
                a: IdentityLifecycle.MERGED,
                b: IdentityLifecycle.MERGED,
                c: IdentityLifecycle.ACTIVE,
            }.get,
            surviving_of={a: b, b: c}.get,
        )
        == c
    )
    assert (
        resolve_canonical_id(
            a,
            status_of={a: IdentityLifecycle.MERGED, b: IdentityLifecycle.MERGED}.get,
            surviving_of={a: b, b: a}.get,
        )
        is None
    )


def test_logging_redacts_lookup_value() -> None:
    redacted = _redact_secrets(
        None,
        "info",
        {"lookup_value": "1234567890123456", "identifier_value": "MRN-1", "nik": "x", "bpjs": "y"},
    )
    assert redacted["lookup_value"] == "[REDACTED]"
    assert redacted["identifier_value"] == "[REDACTED]"
    assert redacted["nik"] == "[REDACTED]"
    assert redacted["bpjs"] == "[REDACTED]"


@pytest.mark.asyncio
async def test_429_does_not_echo_searched_identifier() -> None:
    settings = make_settings(rate_limit_per_minute=1)
    app = create_app(
        settings,
        token_validator=JwtOidcTokenValidator(settings),
        redis=None,
    )
    nik = unique_nik()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            _LOOKUP,
            headers={"X-Purpose": "TREATMENT", "X-Organization-Id": str(uuid4())},
            json=_lookup_body(PatientLookupType.NIK, nik),
        )
        limited = await client.post(
            _LOOKUP,
            headers={"X-Purpose": "TREATMENT", "X-Organization-Id": str(uuid4())},
            json=_lookup_body(PatientLookupType.NIK, nik),
        )
    assert limited.status_code == 429
    assert nik not in limited.text
    assert limited.json()["error"]["code"] == "rate_limited"
    assert "lookup_value" not in limited.text


@requires_db
async def test_schema_injection_and_422_privacy(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    nik = unique_nik()
    extras = {
        "organization_id": str(uuid4()),
        "identifier_organization_id": str(uuid4()),
        "tenant_id": "acme",
        "facility_id": str(uuid4()),
        "purpose": "TREATMENT",
        "role": "ORG_ADMIN",
        "permission": "mpi.identity.read",
        "patient_identity_id": str(uuid4()),
    }
    for field, value in extras.items():
        response = await db_client.post(
            _LOOKUP,
            headers=actor.headers(purpose="TREATMENT"),
            json={
                "lookup_type": PatientLookupType.NIK,
                "lookup_value": nik,
                field: value,
            },
        )
        assert response.status_code == 422, field
        assert response.json()["error"]["code"] == "validation_error"
        assert nik not in response.text
        assert nik not in str(response.json())


@requires_db
async def test_malformed_jwt_and_staff_audience_matrix(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    body = _lookup_body(PatientLookupType.MRN, unique_mrn("JWT"))
    malformed = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": "Bearer not-a-jwt",
            "X-Organization-Id": str(actor.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json=body,
    )
    assert malformed.status_code == 401
    empty = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": "Bearer ",
            "X-Organization-Id": str(actor.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json=body,
    )
    assert empty.status_code == 401
    garbage = jwt.encode(
        {"sub": actor.subject, "aud": "php-api"},
        "wrong-secret-must-be-at-least-32b!!",
        algorithm="HS256",
    )
    bad_sig = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {garbage}",
            "X-Organization-Id": str(actor.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json=body,
    )
    assert bad_sig.status_code == 401


@requires_db
async def test_permission_purpose_cross_matrix(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    clinical_only = await seed_clinical_without_mpi(db_engine, clinician.organization_id)
    body = _lookup_body(PatientLookupType.MRN, unique_mrn("MX"))
    denied = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {clinical_only.token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": Purpose.TREATMENT.value,
        },
        json=body,
    )
    assert denied.status_code == 403

    for purpose in (
        Purpose.TREATMENT.value,
        Purpose.REGISTRATION.value,
        Purpose.IDENTITY_RESOLUTION.value,
        Purpose.AUDIT.value,
    ):
        allowed = await db_client.post(
            _LOOKUP,
            headers=clinician.headers(purpose=purpose),
            json=body,
        )
        assert allowed.status_code == 200, purpose

    invalid = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "NOT_A_PURPOSE",
        },
        json=body,
    )
    assert invalid.status_code == 422
    patient_access = await db_client.post(
        _LOOKUP,
        headers=clinician.headers(purpose=Purpose.PATIENT_ACCESS.value),
        json=body,
    )
    assert patient_access.status_code == 403
    whitespace = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": " treatment ",
        },
        json=body,
    )
    assert whitespace.status_code == 200
    missing = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
        json=body,
    )
    assert missing.status_code == 422
    audits = await _lookup_audit_rows(db_engine, clinician.user_id)
    blob = " ".join((row[1] or "") + " " + (row[3] or "") for row in audits)
    assert "NOT_A_PURPOSE" not in blob
    assert body["lookup_value"] not in blob


@requires_db
async def test_facility_header_does_not_filter_identity(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    mrn = unique_mrn("FAC")
    created = await _create_identity(db_client, actor, _mrn_payload(mrn))
    facility_a = new_id()
    facility_b = new_id()
    async with db_engine.begin() as connection:
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=facility_a,
                organization_id=actor.organization_id,
                name="Ward A1",
                code=f"A1{facility_a.hex[:6].upper()}",
                facility_type=FacilityType.CLINIC_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
        await connection.execute(
            FacilityModel.__table__.insert().values(
                id=facility_b,
                organization_id=actor.organization_id,
                name="Ward A2",
                code=f"A2{facility_b.hex[:6].upper()}",
                facility_type=FacilityType.CLINIC_SITE,
                status=FacilityStatus.ACTIVE,
            )
        )
    bodies = []
    for facility in (str(facility_a), str(facility_b), None):
        headers = actor.headers(purpose="REGISTRATION")
        if facility:
            headers["X-Facility-Id"] = facility
        found = await db_client.post(
            _LOOKUP,
            headers=headers,
            json=_lookup_body(PatientLookupType.MRN, mrn),
        )
        assert found.status_code == 200
        bodies.append(found.json())
    assert bodies[0]["outcome"] == bodies[1]["outcome"] == bodies[2]["outcome"] == "one"
    assert {item["results"][0]["patient_identity_id"] for item in bodies} == {created["id"]}


@requires_db
async def test_exact_match_rejects_prefix_suffix_substring_and_wildcards(
    db_client, db_engine
) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=actor.organization_id
    )
    mrn = unique_mrn("EXACTH")
    nik = unique_nik()
    bpjs = unique_bpjs()
    await _create_identity(db_client, actor, _mrn_payload(mrn))
    created_nik = await _create_identity(db_client, actor, _nik_payload(nik))
    await _verify_first_identifier(db_client, officer, created_nik)
    created_bpjs = await _create_identity(db_client, actor, _bpjs_payload(bpjs))
    await _verify_first_identifier(db_client, officer, created_bpjs)

    async def lookup(lookup_type: str, value: str) -> dict:
        response = await db_client.post(
            _LOOKUP,
            headers=actor.headers(purpose="REGISTRATION"),
            json=_lookup_body(lookup_type, value),
        )
        return {"status": response.status_code, "body": response.json(), "text": response.text}

    full_mrn = await lookup(PatientLookupType.MRN, mrn)
    assert full_mrn["status"] == 200 and full_mrn["body"]["outcome"] == "one"
    for value in (mrn[:8], mrn[2:], mrn[1:8], f"{mrn}%", f"%{mrn}", f"{mrn}_x", ".*", f"{mrn}.*"):
        missed = await lookup(PatientLookupType.MRN, value)
        assert missed["status"] == 200
        assert missed["body"]["outcome"] == "none"
        assert missed["body"]["results"] == []

    full_nik = await lookup(PatientLookupType.NIK, nik)
    assert full_nik["status"] == 200 and full_nik["body"]["outcome"] == "one"
    assert nik not in full_nik["text"]
    prefix_nik = await lookup(PatientLookupType.NIK, nik[:8])
    assert prefix_nik["status"] == 422
    assert nik[:8] not in prefix_nik["text"]
    flipped = f"{nik[:15]}0" if nik[-1] != "0" else f"{nik[:15]}1"
    other_nik = await lookup(PatientLookupType.NIK, flipped)
    assert other_nik["status"] == 200
    assert other_nik["body"]["outcome"] == "none"

    full_bpjs = await lookup(PatientLookupType.BPJS, bpjs)
    assert full_bpjs["status"] == 200 and full_bpjs["body"]["outcome"] == "one"
    assert bpjs not in full_bpjs["text"]
    short_bpjs = await lookup(PatientLookupType.BPJS, bpjs[:6])
    assert short_bpjs["status"] == 422
    assert bpjs[:6] not in short_bpjs["text"]


@requires_db
async def test_normalization_matches_frozen_helper(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    mrn = f"00123-{uuid4().hex[:8].upper()}"
    await _create_identity(db_client, actor, _mrn_payload(f"  {mrn}  "))
    expected = normalize_identifier(
        "hospital-mrn", IdentifierType.MRN, f"  {mrn}  "
    ).normalized_value
    found = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, f" {mrn} "),
    )
    assert found.status_code == 200
    assert found.json()["results"][0]["organization_mrn"] == expected
    assert found.json()["results"][0]["organization_mrn"].startswith("00123")


@requires_db
async def test_same_mrn_00123_is_org_isolated(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    shared = f"00123-{uuid4().hex[:8].upper()}"
    created_a = await _create_identity(
        db_client, hospital_a, _mrn_payload(shared, given="PatientA")
    )
    created_b = await _create_identity(
        db_client, hospital_b, _mrn_payload(shared, given="PatientB")
    )
    a_hit = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, shared),
    )
    b_hit = await db_client.post(
        _LOOKUP,
        headers=hospital_b.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, shared),
    )
    assert a_hit.json()["results"][0]["patient_identity_id"] == created_a["id"]
    assert b_hit.json()["results"][0]["patient_identity_id"] == created_b["id"]
    assert created_b["id"] not in a_hit.text
    assert created_a["id"] not in b_hit.text
    assert "PatientB" not in a_hit.text
    assert "PatientA" not in b_hit.text


@requires_db
async def test_nik_and_bpjs_cross_org_concealment(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer_b = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=hospital_b.organization_id
    )
    nik = unique_nik()
    bpjs = unique_bpjs()
    created_nik = await _create_identity(
        db_client, hospital_b, _nik_payload(nik, given="ForeignNik", family="Hidden")
    )
    await _verify_first_identifier(db_client, officer_b, created_nik)
    created_bpjs = await _create_identity(db_client, hospital_b, _bpjs_payload(bpjs))
    await _verify_first_identifier(db_client, officer_b, created_bpjs)

    a_nik = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, nik),
    )
    a_bpjs = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.BPJS, bpjs),
    )
    unknown = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, unique_nik()),
    )
    assert a_nik.status_code == unknown.status_code == 200
    assert a_nik.json() == unknown.json() == {"outcome": "none", "truncated": False, "results": []}
    assert a_bpjs.json() == {"outcome": "none", "truncated": False, "results": []}
    for response in (a_nik, a_bpjs):
        assert nik not in response.text
        assert bpjs not in response.text
        assert "ForeignNik" not in response.text
        assert created_nik["id"] not in response.text
        assert created_bpjs["id"] not in response.text
        assert "another" not in response.text.lower()
        assert str(hospital_b.organization_id) not in response.text

    b_nik = await db_client.post(
        _LOOKUP,
        headers=hospital_b.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, nik),
    )
    assert b_nik.json()["outcome"] == "one"
    assert b_nik.json()["results"][0]["patient_identity_id"] == created_nik["id"]
    assert nik not in b_nik.text


@requires_db
async def test_canonical_cross_org_adversarial_matrix(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer_a = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=hospital_a.organization_id
    )

    foreign_nik = unique_nik()
    foreign_source = await _create_identity(
        db_client, hospital_b, _nik_payload(foreign_nik, given="Foreign", family="Source")
    )
    local_survivor = await _create_identity(
        db_client, hospital_a, _mrn_payload(unique_mrn("LSUR"), given="Local", family="Survivor")
    )
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE patient_identities "
                "SET lifecycle_status = 'MERGED', surviving_identity_id = :survivor "
                "WHERE id = :source"
            ),
            {"survivor": local_survivor["id"], "source": foreign_source["id"]},
        )
    hop_a = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, foreign_nik),
    )
    assert hop_a.json()["outcome"] == "none"
    assert local_survivor["id"] not in hop_a.text

    local_mrn = unique_mrn("LSRC")
    local_source = await _create_identity(
        db_client, hospital_a, _mrn_payload(local_mrn, given="Local", family="Source")
    )
    foreign_survivor = await _create_identity(
        db_client, hospital_b, _mrn_payload(unique_mrn("FSUR"), given="Foreign", family="Survivor")
    )
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE patient_identities "
                "SET lifecycle_status = 'MERGED', surviving_identity_id = :survivor "
                "WHERE id = :source"
            ),
            {"survivor": foreign_survivor["id"], "source": local_source["id"]},
        )
    hop_b = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, local_mrn),
    )
    assert hop_b.json()["outcome"] == "none"
    assert foreign_survivor["id"] not in hop_b.text
    assert "Foreign Survivor" not in hop_b.text

    foreign_pair_nik = unique_nik()
    foreign_x = await _create_identity(
        db_client, hospital_b, _nik_payload(foreign_pair_nik, given="Fx")
    )
    foreign_y = await _create_identity(
        db_client, hospital_b, _mrn_payload(unique_mrn("FY"), given="Fy")
    )
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE patient_identities "
                "SET lifecycle_status = 'MERGED', surviving_identity_id = :survivor "
                "WHERE id = :source"
            ),
            {"survivor": foreign_y["id"], "source": foreign_x["id"]},
        )
    hop_c = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, foreign_pair_nik),
    )
    assert hop_c.json()["outcome"] == "none"

    source = await _create_identity(
        db_client, officer_a, _mrn_payload(unique_mrn("DSRC"), given="Ann")
    )
    target = await _create_identity(db_client, officer_a, _nik_payload(unique_nik(), given="Anne"))
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer_a.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source["id"],
            "target_identity_id": target["id"],
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("HARDEN-D"),
            "idempotency_key": f"harden-d-{source['id']}",
        },
    )
    assert merge.status_code in {200, 201}
    hop_d = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, source["id"]),
    )
    assert hop_d.json()["outcome"] == "one"
    assert hop_d.json()["results"][0]["patient_identity_id"] == target["id"]
    assert hop_d.json()["results"][0]["resolved_from_merged"] is True
    assert hop_d.json()["results"][0]["lifecycle_status"] != "MERGED"


@requires_db
async def test_frozen_sequential_merge_chain_and_cycle_defense(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    source_mrn = unique_mrn("CHAIN")
    source = await _create_identity(db_client, officer, _mrn_payload(source_mrn, given="HopA"))
    mid = await _create_identity(
        db_client,
        officer,
        _mrn_payload(unique_mrn("MID"), given="HopB", system="hospital-mrn-mid"),
    )
    survivor = await _create_identity(db_client, officer, _nik_payload(unique_nik(), given="HopC"))
    first = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source["id"],
            "target_identity_id": mid["id"],
            "reason": "First hop",
            "evidence": merge_evidence("chain-h1"),
            "idempotency_key": f"chain-h1-{source['id']}",
        },
    )
    assert first.status_code in {200, 201}
    second = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": mid["id"],
            "target_identity_id": survivor["id"],
            "reason": "Second hop",
            "evidence": merge_evidence("chain-h2"),
            "idempotency_key": f"chain-h2-{mid['id']}",
        },
    )
    assert second.status_code in {200, 201}
    found = await db_client.post(
        _LOOKUP,
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json=_lookup_body(PatientLookupType.MRN, source_mrn),
    )
    assert found.json()["results"][0]["patient_identity_id"] == survivor["id"]
    assert found.json()["results"][0]["requested_patient_identity_id"] == source["id"]

    left = await _create_identity(db_client, officer, _mrn_payload(unique_mrn("LOOP1")))
    right = await _create_identity(db_client, officer, _mrn_payload(unique_mrn("LOOP2")))
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE patient_identities SET lifecycle_status = 'MERGED', "
                "surviving_identity_id = :right WHERE id = :left"
            ),
            {"right": right["id"], "left": left["id"]},
        )
        await connection.execute(
            text(
                "UPDATE patient_identities SET lifecycle_status = 'MERGED', "
                "surviving_identity_id = :left WHERE id = :right"
            ),
            {"left": left["id"], "right": right["id"]},
        )
    looped = await db_client.post(
        _LOOKUP,
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, left["id"]),
    )
    assert looped.status_code == 409
    assert looped.json()["error"]["code"] == "identity_not_usable"
    assert left["id"] not in looped.text
    assert "surviving_identity_id" not in looped.text


@requires_db
async def test_unknown_and_foreign_uuid_are_equivalent(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    foreign = await _create_identity(db_client, hospital_b, _mrn_payload(unique_mrn("FU")))
    unknown = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="TREATMENT"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, str(uuid4())),
    )
    foreign_lookup = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="TREATMENT"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, foreign["id"]),
    )
    assert (
        unknown.json()
        == foreign_lookup.json()
        == {
            "outcome": "none",
            "truncated": False,
            "results": [],
        }
    )
    assert str(hospital_b.organization_id) not in foreign_lookup.text


@requires_db
async def test_retired_payload_has_no_identifier_dump(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    mrn = unique_mrn("RETX")
    created = await _create_identity(db_client, actor, _mrn_payload(mrn, given="Retired"))
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": created["id"]},
        )
    by_uuid = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, created["id"]),
    )
    assert by_uuid.status_code == 409
    payload = by_uuid.json()
    assert set(payload["error"]) == {"code", "message", "correlation_id"}
    assert mrn not in by_uuid.text
    assert "Retired" not in by_uuid.text
    assert "identifiers" not in by_uuid.text


@requires_db
async def test_unverified_mix_and_ambiguity_bounds(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=actor.organization_id
    )
    verified_nik = unique_nik()
    unverified_nik = unique_nik()
    created_verified = await _create_identity(db_client, actor, _nik_payload(verified_nik))
    await _verify_first_identifier(db_client, officer, created_verified)
    created_unverified = await _create_identity(db_client, actor, _nik_payload(unverified_nik))
    verified_hit = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, verified_nik),
    )
    unverified_hit = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, unverified_nik),
    )
    assert verified_hit.json()["outcome"] == "one"
    assert verified_hit.json()["results"][0]["selectable"] is True
    assert unverified_hit.json()["outcome"] == "review_required"
    assert unverified_hit.json()["results"][0]["selectable"] is False
    assert unverified_hit.json()["results"][0]["patient_identity_id"] == created_unverified["id"]

    shared = unique_mrn("AMB6")
    created_ids = []
    for index in range(6):
        created = await _create_identity(
            db_client,
            actor,
            _mrn_payload(shared, system=f"hospital-mrn-{index}", given=f"Pat{index:02d}"),
        )
        created_ids.append(created["id"])
    found = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, shared),
    )
    body = found.json()
    assert body["outcome"] == "ambiguous"
    assert body["truncated"] is True
    assert len(body["results"]) == 5
    returned = [item["patient_identity_id"] for item in body["results"]]
    assert returned == sorted(returned)
    assert set(returned).issubset(set(created_ids))
    assert all(item["selectable"] is True for item in body["results"])

    none = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, unique_mrn("ZERO")),
    )
    assert none.json() == {"outcome": "none", "truncated": False, "results": []}


@requires_db
async def test_response_minimization_and_anonymous_safety(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=actor.organization_id
    )
    nik = unique_nik()
    created = await _create_identity(db_client, actor, _nik_payload(nik))
    await _verify_first_identifier(db_client, officer, created)
    found = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, nik),
    )
    hit = found.json()["results"][0]
    allowed = {
        "patient_identity_id",
        "requested_patient_identity_id",
        "lifecycle_status",
        "identity_kind",
        "display_name",
        "display_label",
        "birth_date",
        "administrative_sex",
        "organization_mrn",
        "masked_identifier",
        "identifier_verification",
        "resolved_from_merged",
        "review_required",
        "selectable",
    }
    assert set(hit) <= allowed
    forbidden = (
        "identifiers",
        "phone",
        "email",
        "address",
        "match_score",
        "cluster",
        "merge_operation",
        "provenance",
        "organization_id",
    )
    blob = str(found.json()).lower()
    for item in forbidden:
        assert item not in blob
    assert nik not in found.text
    _assert_no_clinical_payload(found.json())

    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=actor.headers(purpose="EMERGENCY"),
        json={},
    )
    anon_hit = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, anonymous.json()["id"]),
    )
    body = anon_hit.json()["results"][0]
    assert body["identity_kind"] in {"ANONYMOUS", "TEMPORARY"}
    assert body["masked_identifier"] is None
    assert "1234567890123456" not in anon_hit.text
    assert body["organization_mrn"] is None


@requires_db
async def test_lookup_is_read_only_except_audit(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    mrn = unique_mrn("RO")
    await _create_identity(db_client, actor, _mrn_payload(mrn))
    before = await _counts(db_engine)
    found = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, mrn),
    )
    missing = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, unique_mrn("MISS")),
    )
    assert found.status_code == 200
    assert missing.status_code == 200
    after = await _counts(db_engine)
    for table in (
        "patient_identities",
        "patient_identifiers",
        "identity_clusters",
        "identity_cluster_members",
        "identity_match_candidates",
        "identity_merge_operations",
        "identity_provenances",
        "clinical_provenances",
    ):
        assert after[table] == before[table], table
    assert after["audit_events"] >= before["audit_events"] + 2
    assert after["clinical_provenances"] == before["clinical_provenances"]
    audits = await _lookup_audit_rows(db_engine, actor.user_id)
    assert "CLINICAL_CHART_ACCESSED" not in [row[0] for row in audits]
    none_rows = [
        row for row in audits if row[0] == "PATIENT_LOOKUP_ACCESSED" and "none" in (row[1] or "")
    ]
    assert none_rows
    assert all(row[2] in {None, ""} for row in none_rows)
    blob = " ".join(row[1] or "" for row in audits)
    assert mrn not in blob


@requires_db
async def test_lookup_indexes_exist_for_exact_match(db_engine) -> None:
    async with db_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE tablename = 'patient_identifiers'"
                )
            )
        ).all()
    names = {row[0] for row in rows}
    defs = " ".join(row[1] for row in rows).lower()
    assert "uq_patient_identifiers_global_active" in names
    assert "uq_patient_identifiers_org_active" in names
    assert "ix_patient_identifiers_organization_id" in names
    assert "ix_patient_identifiers_system_normalized" in names
    assert "identifier_system" in defs and "normalized_value" in defs
    repo = _repo_py()
    assert "normalized_value == normalized_value" in repo or "normalized_value" in repo
    assert ".limit(limit)" in repo
    services = _services_py()
    assert "find_active_identifiers_for_lookup" in services
    assert "LIKE" not in services
    mpi = _mpi_py()
    assert 'prefix="/mpi"' in mpi
    assert "/identities/lookup" in mpi
    assert "/patients/lookup" in mpi
