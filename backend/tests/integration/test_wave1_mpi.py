import asyncio
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.mpi.domain.enums import IdentifierType, MatchDecision
from sqlalchemy import text
from tests.integration.conftest import requires_db, seed_actor

pytestmark = pytest.mark.integration


def unique_nik() -> str:
    return f"{uuid4().int % 10**16:016d}"


def unique_mrn(prefix: str = "MRN") -> str:
    return f"{prefix}-{uuid4().hex[:10].upper()}"


def merge_evidence(reference: str = "MPI-1") -> list[dict[str, str]]:
    return [
        {
            "evidence_type": "STAFF_REVIEW",
            "evidence_source": "identity-officer",
            "evidence_reference": reference,
            "reviewer_reason": "Confirmed duplicate registration",
            "reviewed_at": "2026-08-13T17:00:00+00:00",
        }
    ]


def _identity_payload(
    nik: str,
    *,
    given: str = "John",
    family: str = "Doe",
    birth: str = "1990-01-01",
) -> dict[str, object]:
    return {
        "given_name": given,
        "family_name": family,
        "birth_date": birth,
        "identifiers": [
            {
                "identifier_system": "id.nik",
                "identifier_type": IdentifierType.NIK,
                "identifier_value": nik,
            }
        ],
    }


@requires_db
async def test_create_identity_and_anonymous_identity(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    nik = unique_nik()
    identified = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json=_identity_payload(nik),
    )
    assert identified.status_code == 201 or identified.status_code == 200
    body = identified.json()
    assert body["lifecycle_status"] == "ACTIVE"
    assert body["identifiers"][0]["masked_value"].endswith(nik[-4:])
    assert nik not in identified.text

    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=actor.headers(purpose="EMERGENCY"),
        json={},
    )
    assert anonymous.status_code in {200, 201}
    anon = anonymous.json()
    assert anon["lifecycle_status"] == "ANONYMOUS"
    assert anon["identifiers"] == []
    assert anon["id"]
    assert anon["display_label"].startswith("UNKNOWN-")


@requires_db
async def test_duplicate_identifier_rejected(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    nik = unique_nik()
    first = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json=_identity_payload(nik),
    )
    assert first.status_code in {200, 201}
    second = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json=_identity_payload(nik),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


@requires_db
async def test_organization_scoped_mrn_can_repeat_across_orgs(db_client, db_engine) -> None:
    hospital_a = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, org_code=f"HOSPA{uuid4().hex[:8]}"
    )
    hospital_b = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, org_code=f"HOSPB{uuid4().hex[:8]}"
    )
    payload = {
        "given_name": "Ada",
        "family_name": "Lovelace",
        "birth_date": "1815-12-10",
        "identifiers": [
            {
                "identifier_system": "hospital-mrn",
                "identifier_type": IdentifierType.MRN,
                "identifier_value": unique_mrn("SHARED"),
            }
        ],
    }
    first = await db_client.post(
        "/api/v1/mpi/identities", headers=hospital_a.headers(), json=payload
    )
    second = await db_client.post(
        "/api/v1/mpi/identities", headers=hospital_b.headers(), json=payload
    )
    assert first.status_code in {200, 201}
    assert second.status_code in {200, 201}
    assert first.json()["id"] != second.json()["id"]


@requires_db
async def test_verify_identifier_and_deterministic_match(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    trusted_nik = unique_nik()
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(trusted_nik, given="Jonathan", family="Dough"),
    )
    assert created.status_code in {200, 201}
    identifier_id = created.json()["identifiers"][0]["id"]
    verified = await db_client.post(
        f"/api/v1/mpi/identifiers/{identifier_id}/verify",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={"method": "document_inspection"},
    )
    assert verified.status_code in {200, 201}
    assert verified.json()["verification_status"] == "VERIFIED"

    second = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="John", family="Doe"),
    )
    second_id = second.json()["id"]
    second_identifier = second.json()["identifiers"][0]["id"]
    await db_client.post(
        f"/api/v1/mpi/identifiers/{second_identifier}/verify",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={"method": "document_inspection"},
    )
    match = await db_client.post(
        "/api/v1/mpi/match",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "given_name": "John",
            "family_name": "Doe",
            "birth_date": "1990-01-01",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": trusted_nik,
                }
            ],
        },
    )
    assert match.status_code == 200
    decisions = {item["candidate_patient_id"]: item["decision"] for item in match.json()}
    assert created.json()["id"] in decisions
    assert decisions[created.json()["id"]] == MatchDecision.CONFIRMED_MATCH
    assert second_id not in decisions or decisions.get(second_id) != MatchDecision.CONFIRMED_MATCH


@requires_db
async def test_duplicate_name_does_not_auto_merge(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    first = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json={
            "given_name": "John",
            "family_name": "Doe",
            "birth_date": "1990-01-01",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": IdentifierType.MRN,
                    "identifier_value": unique_mrn("A"),
                    "organization_id": str(actor.organization_id),
                }
            ],
        },
    )
    second = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json={
            "given_name": "John",
            "family_name": "Doe",
            "birth_date": "1990-01-01",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": IdentifierType.MRN,
                    "identifier_value": unique_mrn("B"),
                    "organization_id": str(actor.organization_id),
                }
            ],
        },
    )
    assert first.status_code in {200, 201}
    assert second.status_code in {200, 201}
    assert first.json()["id"] != second.json()["id"]
    match = await db_client.post(
        "/api/v1/mpi/match",
        headers=actor.headers(purpose="IDENTITY_RESOLUTION"),
        json={"identity_id": second.json()["id"]},
    )
    assert match.status_code == 200
    assert match.json()[0]["decision"] == MatchDecision.POSSIBLE_MATCH
    assert first.json()["lifecycle_status"] == "ACTIVE"
    assert second.json()["lifecycle_status"] == "ACTIVE"


@requires_db
async def test_merge_unmerge_and_idempotency(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Ann",
            "family_name": "Lee",
            "birth_date": "1984-04-04",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": IdentifierType.MRN,
                    "identifier_value": unique_mrn("MERGE"),
                }
            ],
        },
    )
    target = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Anne", family="Lee", birth="1984-04-04"),
    )
    source_id = source.json()["id"]
    target_id = target.json()["id"]
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": target_id,
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("MPI-1"),
            "idempotency_key": f"merge-{source_id}",
        },
    )
    assert merge.status_code in {200, 201}
    merge_id = merge.json()["id"]
    replay = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source_id,
            "target_identity_id": target_id,
            "reason": "Duplicate registration confirmed by registrar",
            "evidence": merge_evidence("MPI-1"),
            "idempotency_key": f"merge-{source_id}",
        },
    )
    assert replay.json()["id"] == merge_id
    fetched = await db_client.get(
        f"/api/v1/mpi/identities/{source_id}",
        headers=officer.headers(purpose="ADMINISTRATION"),
    )
    assert fetched.json()["lifecycle_status"] == "MERGED"
    assert fetched.json()["surviving_identity_id"] == target_id
    assert fetched.json()["id"] == source_id

    unmerge = await db_client.post(
        "/api/v1/mpi/unmerge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "merge_operation_id": merge_id,
            "reason": "Incorrect linkage",
            "evidence": merge_evidence("MPI-2"),
        },
    )
    assert unmerge.status_code in {200, 201}
    assert unmerge.json()["operation"] == "UNMERGE"
    assert unmerge.json()["related_merge_id"] == merge_id
    restored = await db_client.get(
        f"/api/v1/mpi/identities/{source_id}",
        headers=officer.headers(purpose="ADMINISTRATION"),
    )
    assert restored.json()["lifecycle_status"] == "ACTIVE"
    assert restored.json()["surviving_identity_id"] is None

    async with db_engine.connect() as connection:
        history = await connection.execute(
            text("SELECT operation FROM identity_merge_operations WHERE source_identity_id = :id"),
            {"id": source_id},
        )
        operations = {row[0] for row in history}
        assert operations == {"MERGE", "UNMERGE"}
        audit = await connection.execute(
            text("SELECT action FROM audit_events WHERE patient_id = :id"),
            {"id": source_id},
        )
        actions = {row[0] for row in audit}
        assert "PATIENT_MERGED" in actions or "IDENTITY_STATUS_CHANGED" in actions
        provenance = await connection.execute(
            text("SELECT count(*) FROM identity_provenances WHERE subject_id = :id"),
            {"id": source_id},
        )
        assert provenance.scalar_one() >= 1


@requires_db
async def test_anonymous_identity_can_be_resolved(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=actor.headers(purpose="EMERGENCY"),
        json={},
    )
    identity_id = anonymous.json()["id"]
    resolved = await db_client.post(
        f"/api/v1/mpi/identities/{identity_id}/identify",
        headers=actor.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "given_name": "Siti",
            "family_name": "Aminah",
            "birth_date": "1988-03-03",
            "reason": "Family presented identity documents",
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": unique_nik(),
                }
            ],
        },
    )
    assert resolved.status_code in {200, 201}
    assert resolved.json()["lifecycle_status"] == "ACTIVE"
    assert resolved.json()["id"] == identity_id


@requires_db
async def test_concurrent_duplicate_identifier_creates_one_identity(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    nik = unique_nik()
    payload = _identity_payload(nik)

    async def create() -> int:
        response = await db_client.post(
            "/api/v1/mpi/identities", headers=actor.headers(), json=payload
        )
        return response.status_code

    statuses = await asyncio.gather(create(), create())
    assert 409 in statuses
    assert any(code in {200, 201} for code in statuses)
    async with db_engine.connect() as connection:
        count = await connection.execute(
            text(
                """
                SELECT count(*)
                FROM patient_identifiers i
                JOIN patient_identities p ON p.id = i.patient_identity_id
                WHERE i.normalized_value = :nik
                  AND p.lifecycle_status IN ('ACTIVE', 'ANONYMOUS')
                """
            ),
            {"nik": nik},
        )
        assert count.scalar_one() == 1


@requires_db
async def test_audit_and_provenance_created_for_identity(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json=_identity_payload(unique_nik()),
    )
    identity_id = created.json()["id"]
    async with db_engine.connect() as connection:
        audit = await connection.execute(
            text("SELECT action FROM audit_events WHERE patient_id = :id"),
            {"id": identity_id},
        )
        assert "PATIENT_IDENTITY_CREATED" in {row[0] for row in audit}
        provenance = await connection.execute(
            text("SELECT subject_type FROM identity_provenances WHERE subject_id = :id"),
            {"id": identity_id},
        )
        assert "PATIENT_IDENTITY" in {row[0] for row in provenance}


@requires_db
async def test_false_positive_same_name_different_verified_ids(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    first = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="False", family="Positive", birth="1977-07-07"),
    )
    second = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="False", family="Positive", birth="1977-07-07"),
    )
    for response in (first, second):
        identifier_id = response.json()["identifiers"][0]["id"]
        await db_client.post(
            f"/api/v1/mpi/identifiers/{identifier_id}/verify",
            headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
            json={"method": "document_inspection"},
        )
    match = await db_client.post(
        "/api/v1/mpi/match",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={"identity_id": second.json()["id"]},
    )
    decisions = {item["candidate_patient_id"]: item["decision"] for item in match.json()}
    assert decisions[first.json()["id"]] == MatchDecision.NO_MATCH
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": first.json()["id"],
            "target_identity_id": second.json()["id"],
            "reason": "should fail",
            "evidence": merge_evidence("false-positive"),
        },
    )
    assert merge.status_code == 409


@requires_db
async def test_concurrent_merge_same_source_different_targets(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Source",
            "family_name": "Race",
            "birth_date": "1980-01-01",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": IdentifierType.MRN,
                    "identifier_value": unique_mrn("SRC"),
                }
            ],
        },
    )
    target_a = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Target", family="Alpha", birth="1980-01-01"),
    )
    target_b = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Target", family="Beta", birth="1980-01-01"),
    )
    source_id = source.json()["id"]
    target_a_id = target_a.json()["id"]
    target_b_id = target_b.json()["id"]

    async def merge_into(target_id: str) -> object:
        return await db_client.post(
            "/api/v1/mpi/merge",
            headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
            json={
                "source_identity_id": source_id,
                "target_identity_id": target_id,
                "reason": "Concurrent merge race",
                "evidence": merge_evidence("wave15"),
            },
        )

    first, second = await asyncio.gather(merge_into(target_a_id), merge_into(target_b_id))
    statuses = {first.status_code, second.status_code}
    assert 200 in statuses or 201 in statuses
    assert 409 in statuses
    winner = first if first.status_code in {200, 201} else second
    async with db_engine.connect() as connection:
        merges = await connection.execute(
            text(
                """
                SELECT id, target_identity_id
                FROM identity_merge_operations
                WHERE source_identity_id = :id
                  AND operation = 'MERGE'
                  AND status = 'COMPLETED'
                """
            ),
            {"id": source_id},
        )
        rows = list(merges)
        assert len(rows) == 1
        assert str(rows[0][0]) == winner.json()["id"]
        identity = await connection.execute(
            text(
                """
                SELECT lifecycle_status, surviving_identity_id
                FROM patient_identities
                WHERE id = :id
                """
            ),
            {"id": source_id},
        )
        status, surviving = identity.one()
        assert status == "MERGED"
        assert str(surviving) == str(rows[0][1])


@requires_db
async def test_concurrent_unmerge_is_safe(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Unmerge",
            "family_name": "Race",
            "birth_date": "1975-05-05",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": IdentifierType.MRN,
                    "identifier_value": unique_mrn("UNM"),
                }
            ],
        },
    )
    target = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Keep", family="Race", birth="1975-05-05"),
    )
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": target.json()["id"],
            "reason": "Setup for concurrent unmerge",
            "evidence": merge_evidence("wave15-unmerge"),
        },
    )
    merge_id = merge.json()["id"]

    async def unmerge() -> int:
        response = await db_client.post(
            "/api/v1/mpi/unmerge",
            headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
            json={
                "merge_operation_id": merge_id,
                "reason": "Concurrent unmerge race",
                "evidence": merge_evidence("wave15-unmerge"),
            },
        )
        return response.status_code

    statuses = await asyncio.gather(unmerge(), unmerge())
    assert any(code in {200, 201} for code in statuses)
    assert 409 in statuses
    restored = await db_client.get(
        f"/api/v1/mpi/identities/{source.json()['id']}",
        headers=officer.headers(purpose="ADMINISTRATION"),
    )
    assert restored.json()["lifecycle_status"] == "ACTIVE"
    assert restored.json()["surviving_identity_id"] is None
    async with db_engine.connect() as connection:
        count = await connection.execute(
            text(
                """
                SELECT count(*)
                FROM identity_merge_operations
                WHERE related_merge_id = :id
                  AND operation = 'UNMERGE'
                  AND status = 'COMPLETED'
                """
            ),
            {"id": merge_id},
        )
        assert count.scalar_one() == 1
