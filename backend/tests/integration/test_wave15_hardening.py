from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import Permission, RoleCode
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import (
    OrganizationMembershipModel,
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
)
from app.modules.mpi.domain.enums import IdentifierType
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from sqlalchemy import select, text
from tests.conftest import mint_token
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)


def _mrn_payload(
    mrn: str, *, given: str, family: str, birth: str, system: str = "hospital-mrn"
) -> dict[str, object]:
    return {
        "given_name": given,
        "family_name": family,
        "birth_date": birth,
        "identifiers": [
            {
                "identifier_system": system,
                "identifier_type": IdentifierType.MRN,
                "identifier_value": mrn,
            }
        ],
    }


pytestmark = [pytest.mark.integration, pytest.mark.security]


def _headers(actor: SeededActor, purpose: str, facility_id: str | None = None) -> dict[str, str]:
    headers = actor.headers(purpose=purpose)
    if facility_id is not None:
        headers["X-Facility-Id"] = facility_id
    return headers


@requires_db
async def test_purpose_catalog_is_strict(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    payload = _identity_payload(unique_nik())
    missing = await db_client.post(
        "/api/v1/mpi/identities",
        headers={
            "Authorization": f"Bearer {actor.token}",
            "X-Organization-Id": str(actor.organization_id),
        },
        json=payload,
    )
    assert missing.status_code == 422
    empty = await db_client.post(
        "/api/v1/mpi/identities",
        headers={
            "Authorization": f"Bearer {actor.token}",
            "X-Organization-Id": str(actor.organization_id),
            "X-Purpose": "   ",
        },
        json=payload,
    )
    assert empty.status_code == 422
    unknown = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(purpose="billing"),
        json=payload,
    )
    assert unknown.status_code == 422
    treatment = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(purpose="treatment"),
        json=_identity_payload(unique_nik()),
    )
    assert treatment.status_code in {200, 201}
    lowercase = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(purpose="registration"),
        json=_identity_payload(unique_nik()),
    )
    assert lowercase.status_code in {200, 201}


@requires_db
async def test_valid_purpose_without_permission_is_denied(db_client, db_engine) -> None:
    auditor = await seed_actor(db_engine, role_code=RoleCode.AUDITOR)
    response = await db_client.post(
        "/api/v1/mpi/identities",
        headers=auditor.headers(purpose="REGISTRATION"),
        json=_identity_payload(unique_nik()),
    )
    assert response.status_code == 403


@requires_db
async def test_probe_only_match_is_persisted_without_raw_identifiers(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    nik = unique_nik()
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json=_identity_payload(nik, given="Probe", family="Only", birth="1988-08-08"),
    )
    assert created.status_code in {200, 201}
    identity_id = created.json()["id"]
    async with db_engine.connect() as connection:
        before = await connection.execute(text("SELECT count(*) FROM patient_identities"))
        identity_count = before.scalar_one()
    match = await db_client.post(
        "/api/v1/mpi/match",
        headers=actor.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "identifiers": [
                {
                    "identifier_system": "id.nik",
                    "identifier_type": IdentifierType.NIK,
                    "identifier_value": nik,
                }
            ]
        },
    )
    assert match.status_code == 200
    decisions = {item["candidate_patient_id"]: item["decision"] for item in match.json()}
    assert identity_id in decisions
    async with db_engine.connect() as connection:
        after = await connection.execute(text("SELECT count(*) FROM patient_identities"))
        assert after.scalar_one() == identity_count
        probes = await connection.execute(
            text(
                """
                SELECT purpose, actor_id, organization_id, status, candidate_identity_id,
                       evidence_types::text, reasons::text
                FROM identity_match_probes
                WHERE organization_id = :org
                ORDER BY occurred_at DESC
                LIMIT 5
                """
            ),
            {"org": actor.organization_id},
        )
        rows = list(probes)
        assert rows
        purpose, actor_id, organization_id, status, candidate_id, evidence, reasons = rows[0]
        assert purpose == "IDENTITY_RESOLUTION"
        assert str(actor_id) == str(actor.user_id)
        assert str(organization_id) == str(actor.organization_id)
        assert status in {"PROBE_ONLY", "MATCHED_CANDIDATE"}
        if candidate_id is not None:
            assert str(candidate_id) == identity_id
        blob = f"{evidence} {reasons}"
        assert nik not in blob
        raw = await connection.execute(
            text("SELECT count(*) FROM identity_match_probes WHERE evidence_types::text LIKE :nik"),
            {"nik": f"%{nik}%"},
        )
        assert raw.scalar_one() == 0
        audit = await connection.execute(
            text(
                """
                SELECT count(*)
                FROM audit_events
                WHERE action = 'MATCH_CANDIDATE_CREATED'
                  AND organization_id = :org
                  AND purpose = 'IDENTITY_RESOLUTION'
                """
            ),
            {"org": actor.organization_id},
        )
        assert audit.scalar_one() >= 1
        clinical = await connection.execute(
            text(
                """
                SELECT count(*)
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('diagnoses','medications','laboratory_results')
                """
            )
        )
        assert clinical.scalar_one() == 0


@requires_db
async def test_database_permission_assignment_is_authoritative(db_client, db_engine) -> None:
    registrar = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=registrar.headers(),
        json=_identity_payload(unique_nik()),
    )
    identity_id = created.json()["id"]
    role_code = f"CUSTOM_{uuid4().hex[:8].upper()}"
    user_id = new_id()
    subject = f"user-{user_id}"
    membership_id = new_id()
    role_id = new_id()
    async with db_engine.begin() as connection:
        permission_id = (
            await connection.execute(
                select(PermissionModel.id).where(
                    PermissionModel.code == Permission.MPI_IDENTITY_READ
                )
            )
        ).scalar_one()
        await connection.execute(
            RoleModel.__table__.insert().values(
                id=role_id,
                code=role_code,
                name="Custom read role",
            )
        )
        assignment_id = new_id()
        await connection.execute(
            RolePermissionModel.__table__.insert().values(
                id=assignment_id,
                role_id=role_id,
                permission_id=permission_id,
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
                id=membership_id,
                user_id=user_id,
                organization_id=registrar.organization_id,
                facility_id=None,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    actor = SeededActor(user_id, subject, registrar.organization_id, mint_token(sub=subject))
    allowed = await db_client.get(
        f"/api/v1/mpi/identities/{identity_id}",
        headers=actor.headers(purpose="ADMINISTRATION"),
    )
    assert allowed.status_code == 200
    async with db_engine.begin() as connection:
        await connection.execute(
            RolePermissionModel.__table__.delete().where(RolePermissionModel.id == assignment_id)
        )
    denied = await db_client.get(
        f"/api/v1/mpi/identities/{identity_id}",
        headers=actor.headers(purpose="ADMINISTRATION"),
    )
    assert denied.status_code == 403
    async with db_engine.begin() as connection:
        await connection.execute(
            RolePermissionModel.__table__.insert().values(
                id=new_id(),
                role_id=role_id,
                permission_id=permission_id,
            )
        )
        await connection.execute(
            OrganizationMembershipModel.__table__.update()
            .where(OrganizationMembershipModel.id == membership_id)
            .values(status=MembershipStatus.REVOKED)
        )
    revoked = await db_client.get(
        f"/api/v1/mpi/identities/{identity_id}",
        headers=actor.headers(purpose="ADMINISTRATION"),
    )
    assert revoked.status_code == 403


@requires_db
async def test_facility_scope_and_empty_binding(db_client, db_engine) -> None:
    actor = await seed_actor(db_engine, role_code=RoleCode.REGISTRAR)
    created = await db_client.post(
        "/api/v1/mpi/identities",
        headers=actor.headers(),
        json=_identity_payload(unique_nik()),
    )
    identity_id = created.json()["id"]
    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, organization_id, code in (
            (in_scope, actor.organization_id, "IN"),
            (out_of_scope, actor.organization_id, "OUT"),
        ):
            await connection.execute(
                FacilityModel.__table__.insert().values(
                    id=facility_id,
                    organization_id=organization_id,
                    name=code,
                    code=code,
                    facility_type=FacilityType.HOSPITAL_SITE,
                    status=FacilityStatus.ACTIVE,
                )
            )
    org_wide = await db_client.get(
        f"/api/v1/mpi/identities/{identity_id}",
        headers=_headers(actor, "ADMINISTRATION", str(in_scope)),
    )
    assert org_wide.status_code == 200
    bound_user = new_id()
    subject = f"user-{bound_user}"
    async with db_engine.begin() as connection:
        role_id = (
            await connection.execute(
                select(RoleModel.id).where(RoleModel.code == RoleCode.REGISTRAR)
            )
        ).scalar_one()
        await connection.execute(
            UserModel.__table__.insert().values(
                id=bound_user,
                subject=subject,
                display_name=subject,
                status=UserStatus.ACTIVE,
            )
        )
        await connection.execute(
            OrganizationMembershipModel.__table__.insert().values(
                id=new_id(),
                user_id=bound_user,
                organization_id=actor.organization_id,
                facility_id=in_scope,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    bound = SeededActor(bound_user, subject, actor.organization_id, mint_token(sub=subject))
    allowed = await db_client.get(
        f"/api/v1/mpi/identities/{identity_id}",
        headers=_headers(bound, "ADMINISTRATION", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/mpi/identities/{identity_id}",
        headers=_headers(bound, "ADMINISTRATION", str(out_of_scope)),
    )
    assert denied.status_code == 403


@requires_db
async def test_canonical_match_resolves_merged_and_skips_retired(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_mrn_payload(
            unique_mrn("CANON"),
            given="Canon",
            family="Chain",
            birth="1979-09-09",
        ),
    )
    mid = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_mrn_payload(
            unique_mrn("MID"),
            given="Canon",
            family="Mid",
            birth="1979-09-09",
            system="hospital-b-mrn",
        ),
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Canon", family="Survivor", birth="1979-09-09"),
    )
    retired = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Canon", family="Chain", birth="1979-09-09"),
    )
    first = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": mid.json()["id"],
            "reason": "First hop",
            "evidence": merge_evidence("chain-1"),
        },
    )
    assert first.status_code in {200, 201}
    second = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": mid.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Second hop",
            "evidence": merge_evidence("chain-2"),
        },
    )
    assert second.status_code in {200, 201}
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired.json()["id"]},
        )
    match = await db_client.post(
        "/api/v1/mpi/match",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={"identity_id": source.json()["id"]},
    )
    assert match.status_code == 200
    candidates = {item["candidate_patient_id"] for item in match.json()}
    assert source.json()["id"] not in candidates
    assert mid.json()["id"] not in candidates
    assert retired.json()["id"] not in candidates
    retired_probe = await db_client.post(
        "/api/v1/mpi/match",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={"identity_id": retired.json()["id"]},
    )
    assert retired_probe.status_code == 409
    async with db_engine.begin() as connection:
        await connection.execute(
            text(
                """
                UPDATE patient_identities
                SET surviving_identity_id = NULL
                WHERE id = :id
                """
            ),
            {"id": source.json()["id"]},
        )
    broken = await db_client.post(
        "/api/v1/mpi/match",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={"identity_id": source.json()["id"]},
    )
    assert broken.status_code == 409


@requires_db
async def test_structured_merge_evidence_is_required_and_persisted(db_client, db_engine) -> None:
    officer = await seed_actor(db_engine, role_code=RoleCode.IDENTITY_OFFICER)
    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_mrn_payload(unique_mrn("EV"), given="Ev", family="Source", birth="1981-01-01"),
    )
    target = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Ev", family="Target", birth="1981-01-01"),
    )
    empty = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": target.json()["id"],
            "reason": "needs evidence",
            "evidence": [],
        },
    )
    assert empty.status_code == 422
    missing_reason = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": target.json()["id"],
            "reason": "needs evidence",
            "evidence": [
                {
                    "evidence_type": "STAFF_REVIEW",
                    "evidence_source": "officer",
                    "evidence_reference": "x",
                    "reviewer_reason": "",
                    "reviewed_at": "2026-08-13T17:00:00+00:00",
                }
            ],
        },
    )
    assert missing_reason.status_code == 422
    invalid_type = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": target.json()["id"],
            "reason": "needs evidence",
            "evidence": [
                {
                    "evidence_type": "GUESS",
                    "evidence_source": "officer",
                    "evidence_reference": "x",
                    "reviewer_reason": "looks similar",
                    "reviewed_at": "2026-08-13T17:00:00+00:00",
                }
            ],
        },
    )
    assert invalid_type.status_code == 422
    merge = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": target.json()["id"],
            "reason": "Confirmed duplicate",
            "evidence": merge_evidence("persist-1"),
            "idempotency_key": f"ev-{source.json()['id']}",
        },
    )
    assert merge.status_code in {200, 201}
    merge_id = merge.json()["id"]
    replay = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": target.json()["id"],
            "reason": "Confirmed duplicate",
            "evidence": merge_evidence("persist-1"),
            "idempotency_key": f"ev-{source.json()['id']}",
        },
    )
    assert replay.json()["id"] == merge_id
    async with db_engine.connect() as connection:
        stored = await connection.execute(
            text(
                """
                SELECT evidence::text, operation
                FROM identity_merge_operations
                WHERE id = :id
                """
            ),
            {"id": merge_id},
        )
        evidence_text, operation = stored.one()
        assert operation == "MERGE"
        assert "STAFF_REVIEW" in evidence_text
        assert "persist-1" in evidence_text
        audit = await connection.execute(
            text(
                """
                SELECT metadata::text
                FROM audit_events
                WHERE action = 'PATIENT_MERGED'
                  AND resource_id = :id
                """
            ),
            {"id": merge_id},
        )
        metadata = audit.scalar_one()
        assert "STAFF_REVIEW" in metadata
        assert "IDENTITY_RESOLUTION" in metadata or "purpose" in metadata
    unmerge = await db_client.post(
        "/api/v1/mpi/unmerge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "merge_operation_id": merge_id,
            "reason": "Incorrect linkage",
            "evidence": merge_evidence("unmerge-1"),
        },
    )
    assert unmerge.status_code in {200, 201}
    assert unmerge.json()["related_merge_id"] == merge_id
    async with db_engine.connect() as connection:
        original = await connection.execute(
            text("SELECT operation, evidence::text FROM identity_merge_operations WHERE id = :id"),
            {"id": merge_id},
        )
        operation, evidence_text = original.one()
        assert operation == "MERGE"
        assert "persist-1" in evidence_text
