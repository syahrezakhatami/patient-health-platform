from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.clinical.infrastructure.models import ClinicalProvenanceModel
from app.modules.mpi.domain.enums import IdentifierType, PatientLookupType
from sqlalchemy import func, select, text
from tests.conftest import TEST_SECRET, mint_token
from tests.integration.conftest import requires_db, seed_actor
from tests.integration.test_wave1_mpi import merge_evidence, unique_mrn, unique_nik

pytestmark = pytest.mark.integration

_LOOKUP = "/api/v1/mpi/patients/lookup"
_FROZEN_LOOKUP = "/api/v1/mpi/identities/lookup"


def unique_bpjs() -> str:
    return f"{uuid4().int % 10**13:013d}"


def _lookup_body(lookup_type: str, lookup_value: str) -> dict[str, str]:
    return {"lookup_type": lookup_type, "lookup_value": lookup_value}


def _mrn_payload(
    mrn: str,
    *,
    system: str = "hospital-mrn",
    given: str = "Ada",
    family: str = "Lovelace",
    birth: str = "1815-12-10",
    sex: str = "FEMALE",
) -> dict[str, object]:
    return {
        "given_name": given,
        "family_name": family,
        "birth_date": birth,
        "administrative_sex": sex,
        "identifiers": [
            {
                "identifier_system": system,
                "identifier_type": IdentifierType.MRN,
                "identifier_value": mrn,
            }
        ],
    }


def _nik_payload(nik: str, *, given: str = "Budi", family: str = "Santoso") -> dict[str, object]:
    return {
        "given_name": given,
        "family_name": family,
        "birth_date": "1990-01-15",
        "administrative_sex": "MALE",
        "identifiers": [
            {
                "identifier_system": "id.nik",
                "identifier_type": IdentifierType.NIK,
                "identifier_value": nik,
            }
        ],
    }


def _bpjs_payload(bpjs: str) -> dict[str, object]:
    return {
        "given_name": "Siti",
        "family_name": "Aminah",
        "birth_date": "1988-03-03",
        "administrative_sex": "FEMALE",
        "identifiers": [
            {
                "identifier_system": "id.bpjs",
                "identifier_type": IdentifierType.BPJS,
                "identifier_value": bpjs,
            }
        ],
    }


async def _create_identity(db_client, actor, payload: dict[str, object]) -> dict:
    response = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json=payload,
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()


async def _verify_first_identifier(db_client, actor, created: dict) -> None:
    identifier_id = created["identifiers"][0]["id"]
    verified = await db_client.post(
        f"/api/v1/mpi/identifiers/{identifier_id}/verify",
        headers=actor.headers(purpose="IDENTITY_RESOLUTION"),
        json={"method": "document_inspection"},
    )
    assert verified.status_code in {200, 201}


async def _provenance_count(db_engine) -> int:
    async with db_engine.connect() as connection:
        return int(
            (
                await connection.execute(select(func.count()).select_from(ClinicalProvenanceModel))
            ).scalar_one()
        )


def _assert_no_clinical_payload(body: dict) -> None:
    blob = str(body).lower()
    for forbidden in (
        "condition",
        "observation",
        "medication",
        "allerg",
        "encounter",
        "timeline",
        "chart",
        "procedure",
        "laboratory",
    ):
        assert forbidden not in blob


@requires_db
async def test_staff_audience_accepted_and_others_rejected(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    org = str(actor.organization_id)
    body = _lookup_body(PatientLookupType.MRN, unique_mrn("AUD"))
    accepted = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="TREATMENT"),
        json=body,
    )
    assert accepted.status_code == 200

    tokens = {
        "patient": mint_token(sub=actor.subject, aud="php-patient"),
        "platform": mint_token(sub=actor.subject, aud="php-platform"),
        "wrong": mint_token(sub=actor.subject, aud="other-api"),
        "mixed": mint_token(sub=actor.subject, extra={"aud": ["php-api", "php-patient"]}),
        "missing": jwt.encode(
            {
                "sub": actor.subject,
                "iss": "http://localhost:8080/realms/php-dev",
                "exp": datetime.now(UTC) + timedelta(minutes=5),
                "iat": datetime.now(UTC),
            },
            TEST_SECRET,
            algorithm="HS256",
        ),
    }
    for token in tokens.values():
        denied = await db_client.post(
            _LOOKUP,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Organization-Id": org,
                "X-Purpose": "TREATMENT",
            },
            json=body,
        )
        assert denied.status_code == 401


@requires_db
async def test_lookup_requires_permission_and_purpose(db_client, db_engine) -> None:
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    body = _lookup_body(PatientLookupType.MRN, unique_mrn("PERM"))
    forbidden = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {platform.token}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json=body,
    )
    assert forbidden.status_code == 403

    missing = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
        json=body,
    )
    assert missing.status_code == 422
    assert missing.json()["error"]["code"] == "purpose_required"

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
    assert invalid.json()["error"]["code"] == "invalid_purpose"

    patient_access = await db_client.post(
        _LOOKUP,
        headers=clinician.headers(purpose="PATIENT_ACCESS"),
        json=body,
    )
    assert patient_access.status_code == 403


@requires_db
async def test_organization_membership_required_and_no_body_org_override(
    db_client, db_engine
) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    outsider = await db_client.post(
        _LOOKUP,
        headers={
            "Authorization": f"Bearer {hospital_b.token}",
            "X-Organization-Id": str(hospital_a.organization_id),
            "X-Purpose": "TREATMENT",
        },
        json=_lookup_body(PatientLookupType.MRN, unique_mrn("OUT")),
    )
    assert outsider.status_code == 403

    override = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="TREATMENT"),
        json={
            "lookup_type": PatientLookupType.MRN,
            "lookup_value": unique_mrn("OVR"),
            "organization_id": str(hospital_b.organization_id),
        },
    )
    assert override.status_code == 422
    identifier_org = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="TREATMENT"),
        json={
            "lookup_type": PatientLookupType.MRN,
            "lookup_value": unique_mrn("OVR2"),
            "identifier_organization_id": str(hospital_b.organization_id),
        },
    )
    assert identifier_org.status_code == 422


@requires_db
async def test_exact_mrn_nik_bpjs_uuid_and_normalization(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine,
        role_code=RoleCode.IDENTITY_OFFICER,
        organization_id=registrar.organization_id,
    )
    mrn = unique_mrn("EXACT")
    nik = unique_nik()
    bpjs = unique_bpjs()
    created_mrn = await _create_identity(db_client, registrar, _mrn_payload(f"  {mrn}  "))
    created_nik = await _create_identity(db_client, registrar, _nik_payload(nik))
    await _verify_first_identifier(db_client, officer, created_nik)
    created_bpjs = await _create_identity(db_client, registrar, _bpjs_payload(bpjs))
    await _verify_first_identifier(db_client, officer, created_bpjs)

    mrn_hit = await db_client.post(
        _LOOKUP,
        headers=registrar.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, f" {mrn} "),
    )
    assert mrn_hit.status_code == 200
    mrn_body = mrn_hit.json()
    assert mrn_body["outcome"] == "one"
    assert mrn_body["results"][0]["patient_identity_id"] == created_mrn["id"]
    assert mrn_body["results"][0]["display_name"] == "Ada Lovelace"
    assert mrn_body["results"][0]["birth_date"] == "1815-12-10"
    assert mrn_body["results"][0]["administrative_sex"] == "FEMALE"
    assert mrn_body["results"][0]["organization_mrn"] == mrn
    assert mrn_body["results"][0]["selectable"] is True
    assert "identifiers" not in mrn_body["results"][0]
    _assert_no_clinical_payload(mrn_body)

    nik_hit = await db_client.post(
        _LOOKUP,
        headers=registrar.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, f"{nik[:4]}-{nik[4:]}"),
    )
    assert nik_hit.status_code == 200
    nik_body = nik_hit.json()
    assert nik_body["outcome"] == "one"
    assert nik_body["results"][0]["patient_identity_id"] == created_nik["id"]
    assert nik not in nik_hit.text
    assert nik_body["results"][0]["masked_identifier"].endswith(nik[-4:])
    assert set(nik_body["results"][0]["masked_identifier"]) <= set("*" + nik[-4:])

    bpjs_hit = await db_client.post(
        _LOOKUP,
        headers=registrar.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.BPJS, bpjs),
    )
    assert bpjs_hit.status_code == 200
    assert bpjs_hit.json()["results"][0]["patient_identity_id"] == created_bpjs["id"]
    assert bpjs not in bpjs_hit.text

    uuid_hit = await db_client.post(
        _LOOKUP,
        headers=registrar.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, created_mrn["id"]),
    )
    assert uuid_hit.status_code == 200
    assert uuid_hit.json()["results"][0]["patient_identity_id"] == created_mrn["id"]


@requires_db
async def test_zero_result_and_unknown_type(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    missing = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="TREATMENT"),
        json=_lookup_body(PatientLookupType.MRN, unique_mrn("NONE")),
    )
    assert missing.status_code == 200
    assert missing.json() == {"outcome": "none", "truncated": False, "results": []}
    unknown = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="TREATMENT"),
        json=_lookup_body("PASSPORT", "A1234567"),
    )
    assert unknown.status_code == 422
    prefix = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="TREATMENT"),
        json=_lookup_body(PatientLookupType.MRN, "MRN%"),
    )
    assert prefix.status_code == 200
    assert prefix.json()["outcome"] == "none"


@requires_db
async def test_mrn_and_national_id_are_org_isolated(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    shared_mrn = unique_mrn("SHARED")
    nik = unique_nik()
    created_a = await _create_identity(
        db_client, hospital_a, _mrn_payload(shared_mrn, given="Aida")
    )
    created_b = await _create_identity(
        db_client, hospital_b, _mrn_payload(shared_mrn, given="Bella")
    )
    await _create_identity(
        db_client, hospital_b, _nik_payload(nik, given="Foreign", family="Patient")
    )

    a_mrn = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, shared_mrn),
    )
    assert a_mrn.status_code == 200
    assert a_mrn.json()["results"][0]["patient_identity_id"] == created_a["id"]
    assert a_mrn.json()["results"][0]["display_name"] == "Aida Lovelace"
    assert created_b["id"] not in a_mrn.text
    assert "another" not in a_mrn.text.lower()
    assert "hospital b" not in a_mrn.text.lower()

    a_nik = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, nik),
    )
    assert a_nik.status_code == 200
    assert a_nik.json()["outcome"] == "none"
    assert a_nik.json()["results"] == []
    assert nik not in a_nik.text
    assert "another" not in a_nik.text.lower()


@requires_db
async def test_merged_returns_canonical_survivor_not_source(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    source_mrn = unique_mrn("SRC")
    source = await _create_identity(db_client, officer, _mrn_payload(source_mrn, given="Ann"))
    target = await _create_identity(db_client, officer, _nik_payload(unique_nik(), given="Anne"))
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source["id"],
            "target_identity_id": target["id"],
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("LOOKUP-MERGE"),
            "idempotency_key": f"lookup-merge-{source['id']}",
        },
    )
    assert merge.status_code in {200, 201}
    found = await db_client.post(
        _LOOKUP,
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json=_lookup_body(PatientLookupType.MRN, source_mrn),
    )
    assert found.status_code == 200
    body = found.json()
    assert body["outcome"] == "one"
    assert body["results"][0]["patient_identity_id"] == target["id"]
    assert body["results"][0]["requested_patient_identity_id"] == source["id"]
    assert body["results"][0]["resolved_from_merged"] is True
    assert body["results"][0]["selectable"] is True

    frozen = await db_client.post(
        _FROZEN_LOOKUP,
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "identifier_system": "hospital-mrn",
            "identifier_type": IdentifierType.MRN,
            "identifier_value": source_mrn,
        },
    )
    assert frozen.status_code in {200, 201}
    assert frozen.json()["id"] == source["id"]
    assert frozen.json()["lifecycle_status"] == "MERGED"


@requires_db
async def test_canonical_cross_org_pointer_does_not_disclose_foreign_survivor(
    db_client, db_engine
) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    nik = unique_nik()
    foreign = await _create_identity(
        db_client, hospital_b, _nik_payload(nik, given="Foreign", family="Source")
    )
    local = await _create_identity(
        db_client, hospital_a, _mrn_payload(unique_mrn("LOCAL"), given="Local", family="Survivor")
    )
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                "UPDATE patient_identities "
                "SET lifecycle_status = 'MERGED', surviving_identity_id = :survivor "
                "WHERE id = :source"
            ),
            {"survivor": local["id"], "source": foreign["id"]},
        )

    leaked = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, nik),
    )
    assert leaked.status_code == 200
    assert leaked.json()["outcome"] == "none"
    assert leaked.json()["results"] == []
    assert local["id"] not in leaked.text
    assert "Foreign" not in leaked.text
    assert nik not in leaked.text


@requires_db
async def test_retired_identifier_empty_and_retired_uuid_conflict(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    mrn = unique_mrn("RET")
    created = await _create_identity(db_client, actor, _mrn_payload(mrn))
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": created["id"]},
        )
    by_mrn = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, mrn),
    )
    assert by_mrn.status_code == 200
    assert by_mrn.json()["outcome"] == "none"
    by_uuid = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, created["id"]),
    )
    assert by_uuid.status_code == 409
    assert by_uuid.json()["error"]["code"] == "identity_not_usable"


@requires_db
async def test_anonymous_uuid_lookup_returns_safe_summary(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=actor.headers(purpose="EMERGENCY"),
        json={},
    )
    assert anonymous.status_code in {200, 201}
    found = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, anonymous.json()["id"]),
    )
    assert found.status_code == 200
    body = found.json()["results"][0]
    assert body["lifecycle_status"] == "ANONYMOUS"
    assert body["identity_kind"] in {"ANONYMOUS", "TEMPORARY"}
    assert body["display_label"].startswith("UNKNOWN-")
    assert body["selectable"] is True
    assert body["organization_mrn"] is None


@requires_db
async def test_unverified_national_id_is_review_required(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    nik = unique_nik()
    created = await _create_identity(db_client, actor, _nik_payload(nik))
    found = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, nik),
    )
    assert found.status_code == 200
    body = found.json()
    assert body["outcome"] == "review_required"
    assert body["results"][0]["patient_identity_id"] == created["id"]
    assert body["results"][0]["selectable"] is False
    assert body["results"][0]["review_required"] is True
    assert nik not in found.text


@requires_db
async def test_ambiguous_mrn_across_systems_is_bounded(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    shared = unique_mrn("AMB")
    created_ids = []
    for index in range(2):
        created = await _create_identity(
            db_client,
            actor,
            _mrn_payload(shared, system=f"hospital-mrn-{index}", given=f"Pat{index}"),
        )
        created_ids.append(created["id"])
    found = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, shared),
    )
    assert found.status_code == 200
    body = found.json()
    assert body["outcome"] == "ambiguous"
    assert body["truncated"] is False
    assert len(body["results"]) == 2
    assert {item["patient_identity_id"] for item in body["results"]} == set(created_ids)


@requires_db
async def test_foreign_uuid_concealed_and_response_is_minimized(db_client, db_engine) -> None:
    hospital_a = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    hospital_b = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    foreign = await _create_identity(db_client, hospital_b, _mrn_payload(unique_mrn("FUUID")))
    found = await db_client.post(
        _LOOKUP,
        headers=hospital_a.headers(purpose="TREATMENT"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, foreign["id"]),
    )
    assert found.status_code == 200
    assert found.json()["outcome"] == "none"
    assert found.json()["results"] == []
    assert "another" not in found.text.lower()


@requires_db
async def test_lookup_audits_without_raw_identifier_or_chart_or_provenance(
    db_client, db_engine
) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    officer = await seed_actor(
        db_engine,
        role_code=RoleCode.IDENTITY_OFFICER,
        organization_id=actor.organization_id,
    )
    before = await _provenance_count(db_engine)
    mrn = unique_mrn("AUD1")
    nik = unique_nik()
    await _create_identity(db_client, actor, _mrn_payload(mrn))
    await _create_identity(db_client, actor, _nik_payload(nik))
    source = await _create_identity(
        db_client, officer, _mrn_payload(unique_mrn("AUDSRC"), given="Src")
    )
    target = await _create_identity(
        db_client, officer, _nik_payload(unique_nik(), given="Tgt", family="Canonical")
    )
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source["id"],
            "target_identity_id": target["id"],
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("LOOKUP-AUD"),
            "idempotency_key": f"lookup-aud-{source['id']}",
        },
    )
    assert merge.status_code in {200, 201}

    none_hit = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, unique_mrn("MISS")),
    )
    one_hit = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.MRN, mrn),
    )
    review = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.NIK, nik),
    )
    canonical = await db_client.post(
        _LOOKUP,
        headers=actor.headers(purpose="REGISTRATION"),
        json=_lookup_body(PatientLookupType.PATIENT_IDENTITY_ID, source["id"]),
    )
    assert none_hit.status_code == 200
    assert one_hit.status_code == 200
    assert review.status_code == 200
    assert canonical.status_code == 200
    assert canonical.json()["results"][0]["patient_identity_id"] == target["id"]

    async with db_engine.connect() as connection:
        rows = (
            await connection.execute(
                text(
                    "SELECT action, metadata::text, patient_id::text "
                    "FROM audit_events WHERE actor_id = :actor AND action IN "
                    "('PATIENT_LOOKUP_ACCESSED', 'CLINICAL_CHART_ACCESSED')"
                ),
                {"actor": actor.user_id},
            )
        ).all()
    actions = [row[0] for row in rows]
    assert "CLINICAL_CHART_ACCESSED" not in actions
    assert actions.count("PATIENT_LOOKUP_ACCESSED") >= 4
    blob = " ".join(row[1] or "" for row in rows)
    assert mrn not in blob
    assert nik not in blob
    assert "lookup_type" in blob
    after = await _provenance_count(db_engine)
    assert after == before

    assert none_hit.request.url.path == _LOOKUP
    assert mrn not in str(one_hit.request.url)
    assert nik not in str(review.request.url)
