import asyncio
import os
from uuid import uuid4

import pytest
from app.modules.authorization.domain.catalog import RoleCode
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel, UserModel
from app.modules.organization.domain.enums import FacilityStatus, FacilityType
from app.modules.organization.infrastructure.models import FacilityModel
from app.shared.types.ids import new_id
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine
from tests.conftest import mint_token
from tests.integration.conftest import SeededActor, requires_db, seed_actor
from tests.integration.test_wave1_mpi import (
    _identity_payload,
    merge_evidence,
    unique_mrn,
    unique_nik,
)
from tests.integration.test_wave2a_hardening import _active_patient, _open_encounter
from tests.integration.test_wave15_hardening import _headers

pytestmark = [pytest.mark.integration]

LOINC = "http://loinc.org"
APP_DML_URL = os.environ.get(
    "TEST_APP_DML_URL",
    "postgresql+asyncpg://app_dml:app_dml_dev_only@localhost:5433/php_dev",
)


def _consent(
    patient_id: str,
    encounter_id: str | None = None,
    *,
    category: str = "TREATMENT",
    scope: str = "ORGANIZATION",
    decision: str = "PERMIT",
    source: str = "PATIENT",
    note: str | None = "Signed at registration",
    period_start: str | None = None,
    period_end: str | None = None,
    with_code: bool = True,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "patient_identity_id": patient_id,
        "category": category,
        "scope": scope,
        "decision": decision,
        "source": source,
    }
    if with_code:
        payload["code"] = {"system": LOINC, "code": "59284-0", "display": "Consent Document"}
    if note is not None:
        payload["note_text"] = note
    if period_start is not None:
        payload["period_start"] = period_start
    if period_end is not None:
        payload["period_end"] = period_end
    if encounter_id is not None:
        payload["encounter_id"] = encounter_id
    return payload


@requires_db
async def test_consent_lifecycle_identity_and_authorization(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    auditor = await seed_actor(
        db_engine, role_code=RoleCode.AUDITOR, organization_id=clinician.organization_id
    )
    org_admin = await seed_actor(
        db_engine, role_code=RoleCode.ORG_ADMIN, organization_id=clinician.organization_id
    )
    platform = await seed_actor(db_engine, role_code=RoleCode.PLATFORM_ADMIN)
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    patient_id = await _active_patient(db_client, registrar)
    encounter_id = (await _open_encounter(db_client, clinician, patient_id)).json()["id"]

    invalid = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json={**_consent(patient_id), "category": "NOT_A_CATEGORY"},
    )
    assert invalid.status_code == 422
    inverted = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(
            patient_id,
            period_start="2026-08-15T00:00:00Z",
            period_end="2026-08-01T00:00:00Z",
        ),
    )
    assert inverted.status_code == 422

    created = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, encounter_id),
    )
    assert created.status_code in {200, 201}
    body = created.json()
    assert body["status"] == "ACTIVE"
    assert body["decision"] == "PERMIT"
    assert body["category"] == "TREATMENT"
    assert body["scope"] == "ORGANIZATION"
    assert body["source"] == "PATIENT"
    assert body["version"] == 1
    assert body["is_effective"] is True
    assert body["revoked_at"] is None
    consent_id = body["id"]

    for category, scope, decision, source in (
        ("DISCLOSURE", "ORGANIZATION", "DENY", "REPRESENTATIVE"),
        ("PRIVACY", "ENCOUNTER", "PERMIT", "CLINICIAN_DOCUMENTED"),
        ("OTHER", "ORGANIZATION", "DENY", "PATIENT"),
    ):
        variant = await db_client.post(
            "/api/v1/clinical/consents",
            headers=clinician.headers(purpose="TREATMENT"),
            json=_consent(
                patient_id,
                encounter_id if scope == "ENCOUNTER" else None,
                category=category,
                scope=scope,
                decision=decision,
                source=source,
                with_code=False,
            ),
        )
        assert variant.status_code in {200, 201}
        assert variant.json()["category"] == category
        assert variant.json()["scope"] == scope
        assert variant.json()["decision"] == decision
        assert variant.json()["source"] == source
        assert variant.json()["code"] is None

    elapsed = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(
            patient_id,
            period_start="2020-01-01T00:00:00Z",
            period_end="2020-12-31T00:00:00Z",
        ),
    )
    assert elapsed.status_code in {200, 201}
    assert elapsed.json()["status"] == "ACTIVE"
    assert elapsed.json()["is_effective"] is False

    denied = await db_client.post(
        "/api/v1/clinical/consents",
        headers=registrar.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    assert denied.status_code == 403
    assert "Consent Document" not in denied.text
    assert "Signed at registration" not in denied.text
    officer_denied = await db_client.post(
        "/api/v1/clinical/consents",
        headers=officer.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    assert officer_denied.status_code == 403

    listed = await db_client.get(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        params={"patient_identity_id": patient_id},
    )
    assert listed.status_code == 200
    assert consent_id in {item["id"] for item in listed.json()}

    auditor_read = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=auditor.headers(purpose="AUDIT"),
    )
    assert auditor_read.status_code == 200
    admin_create = await db_client.post(
        "/api/v1/clinical/consents",
        headers=org_admin.headers(purpose="TREATMENT"),
        json=_consent(patient_id),
    )
    assert admin_create.status_code == 403
    admin_read = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=org_admin.headers(purpose="TREATMENT"),
    )
    assert admin_read.status_code == 200
    platform_read = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=platform.headers(purpose="TREATMENT"),
    )
    assert platform_read.status_code == 200

    amended = await db_client.post(
        f"/api/v1/clinical/consents/{consent_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "period_start": "2026-01-01T00:00:00Z",
            "period_end": "2026-12-31T00:00:00Z",
            "note_text": "Corrected expiry",
        },
    )
    assert amended.status_code == 200
    assert amended.json()["status"] == "AMENDED"
    assert amended.json()["version"] == 2
    assert amended.json()["note_text"] == "Corrected expiry"
    noop = await db_client.post(
        f"/api/v1/clinical/consents/{consent_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={
            "period_start": amended.json()["period_start"],
            "period_end": amended.json()["period_end"],
            "note_text": "Corrected expiry",
        },
    )
    assert noop.status_code == 409

    revoked = await db_client.post(
        f"/api/v1/clinical/consents/{consent_id}/revoke",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert revoked.status_code == 200
    assert revoked.json()["status"] == "REVOKED"
    assert revoked.json()["revoked_at"] is not None
    assert revoked.json()["is_effective"] is False
    assert revoked.json()["version"] == 3
    double_revoke = await db_client.post(
        f"/api/v1/clinical/consents/{consent_id}/revoke",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert double_revoke.status_code == 409
    blocked_amend = await db_client.post(
        f"/api/v1/clinical/consents/{consent_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"note_text": "after revoke"},
    )
    assert blocked_amend.status_code == 409
    blocked_eie_after_revoke = await db_client.post(
        f"/api/v1/clinical/consents/{consent_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_eie_after_revoke.status_code == 409

    void_source = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, note="void me"),
    )
    void_id = void_source.json()["id"]
    voided = await db_client.post(
        f"/api/v1/clinical/consents/{void_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert voided.status_code == 200
    assert voided.json()["status"] == "ENTERED_IN_ERROR"
    assert voided.json()["is_effective"] is False
    blocked_void_amend = await db_client.post(
        f"/api/v1/clinical/consents/{void_id}/amend",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"note_text": "no"},
    )
    assert blocked_void_amend.status_code == 409
    blocked_void_revoke = await db_client.post(
        f"/api/v1/clinical/consents/{void_id}/revoke",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert blocked_void_revoke.status_code == 409
    double_eie = await db_client.post(
        f"/api/v1/clinical/consents/{void_id}/entered-in-error",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert double_eie.status_code == 409

    cross = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=other.headers(purpose="TREATMENT"),
    )
    assert cross.status_code == 404
    assert "sqlalchemy" not in cross.text.lower()
    assert "Consent Document" not in cross.text
    assert "Signed at registration" not in cross.text
    unknown = await db_client.get(
        f"/api/v1/clinical/consents/{uuid4()}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert unknown.status_code == 404
    deleted = await db_client.delete(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert deleted.status_code == 405
    put = await db_client.put(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=clinician.headers(purpose="TREATMENT"),
        json={},
    )
    assert put.status_code == 405
    missing_purpose = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers={
            "Authorization": f"Bearer {clinician.token}",
            "X-Organization-Id": str(clinician.organization_id),
        },
    )
    assert missing_purpose.status_code == 422
    invalid_purpose = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=clinician.headers(purpose="NOT_A_PURPOSE"),
    )
    assert invalid_purpose.status_code == 422
    unauthenticated = await db_client.get(f"/api/v1/clinical/consents/{consent_id}")
    assert unauthenticated.status_code == 401
    unauthenticated_post = await db_client.post(
        "/api/v1/clinical/consents",
        json=_consent(patient_id),
    )
    assert unauthenticated_post.status_code == 401
    unprovisioned = mint_token(sub="nobody-consent")
    denied_jwt = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers={
            "Authorization": f"Bearer {unprovisioned}",
            "X-Organization-Id": str(clinician.organization_id),
            "X-Purpose": "TREATMENT",
        },
    )
    assert denied_jwt.status_code == 403

    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE consents SET patient_identity_id = :pid WHERE id = :id"),
                    {"id": consent_id, "pid": uuid4()},
                )
        with pytest.raises(Exception, match="immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE consents SET decision = 'DENY' WHERE id = :id"),
                    {"id": consent_id},
                )
        with pytest.raises(Exception, match="cannot be deleted"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM consents WHERE id = :id"),
                    {"id": consent_id},
                )
        provenance = await connection.execute(
            text(
                """
                SELECT subject_type FROM clinical_provenances
                WHERE id = (SELECT provenance_id FROM consents WHERE id = :id)
                """
            ),
            {"id": consent_id},
        )
        assert provenance.scalar_one() == "CONSENT"
        fk = await connection.execute(
            text(
                """
                SELECT delete_rule FROM information_schema.referential_constraints
                WHERE constraint_name = 'fk_consents_provenance_id'
                """
            )
        )
        assert fk.scalar_one() == "RESTRICT"
        audit = await connection.execute(
            text("SELECT action, metadata::text FROM audit_events WHERE resource_id = :id"),
            {"id": consent_id},
        )
        rows = list(audit)
        actions = {row[0] for row in rows}
        assert "CONSENT_CREATED" in actions
        assert "CONSENT_AMENDED" in actions
        assert "CONSENT_REVOKED" in actions
        assert all("Consent Document" not in (row[1] or "") for row in rows)
        assert all("Signed at registration" not in (row[1] or "") for row in rows)
        assert all("Corrected expiry" not in (row[1] or "") for row in rows)
        later = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'fhir_consents','fhir_allergy_intolerances',
                    'break_glass_access','patient_portal_accounts'
                  )
                """
            )
        )
        assert later.scalar_one() == 0
        present = await connection.execute(
            text(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN (
                    'consents','allergies','medications','conditions','observations'
                  )
                """
            )
        )
        assert present.scalar_one() == 5


@requires_db
async def test_anonymous_merged_and_encounter_consent_binding(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    officer = await seed_actor(
        db_engine, role_code=RoleCode.IDENTITY_OFFICER, organization_id=clinician.organization_id
    )
    other = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    other_registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=other.organization_id
    )
    anonymous = await db_client.post(
        "/api/v1/mpi/identities/anonymous",
        headers=registrar.headers(purpose="EMERGENCY"),
        json={},
    )
    anonymous_id = anonymous.json()["id"]
    blocked = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(anonymous_id),
    )
    assert blocked.status_code == 409
    emer = await _open_encounter(db_client, clinician, anonymous_id, "EMER")
    still_blocked = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="EMERGENCY"),
        json=_consent(anonymous_id, emer.json()["id"]),
    )
    assert still_blocked.status_code == 409

    patient_id = await _active_patient(db_client, registrar)
    other_patient = await _active_patient(db_client, registrar)
    foreign_patient = await _active_patient(db_client, other_registrar)
    mismatch = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(
            patient_id, (await _open_encounter(db_client, clinician, other_patient)).json()["id"]
        ),
    )
    assert mismatch.status_code == 409
    foreign = await _open_encounter(db_client, other, foreign_patient)
    cross_org = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, foreign.json()["id"]),
    )
    assert cross_org.status_code == 404
    unknown_enc = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, str(uuid4())),
    )
    assert unknown_enc.status_code == 404

    cancelled = await _open_encounter(db_client, clinician, patient_id)
    cancel = await db_client.post(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "CANCELLED"},
    )
    assert cancel.status_code == 200
    blocked_cancelled = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, cancelled.json()["id"]),
    )
    assert blocked_cancelled.status_code == 409
    still_cancelled = await db_client.get(
        f"/api/v1/clinical/encounters/{cancelled.json()['id']}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert still_cancelled.json()["status"] == "CANCELLED"

    erroneous = await _open_encounter(db_client, clinician, patient_id)
    mark_error = await db_client.post(
        f"/api/v1/clinical/encounters/{erroneous.json()['id']}/status",
        headers=clinician.headers(purpose="TREATMENT"),
        json={"status": "ENTERED_IN_ERROR"},
    )
    assert mark_error.status_code == 200
    blocked_eie_enc = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, erroneous.json()["id"]),
    )
    assert blocked_eie_enc.status_code == 409

    source = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json={
            "given_name": "Cns",
            "family_name": "Source",
            "birth_date": "1982-02-02",
            "identifiers": [
                {
                    "identifier_system": "hospital-mrn",
                    "identifier_type": "MRN",
                    "identifier_value": unique_mrn("W2B3C"),
                }
            ],
        },
    )
    survivor = await db_client.post(
        "/api/v1/mpi/identities",
        headers=officer.headers(),
        json=_identity_payload(unique_nik(), given="Cns", family="Survivor", birth="1982-02-02"),
    )
    historical = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(source.json()["id"]),
    )
    assert historical.status_code in {200, 201}
    historical_id = historical.json()["id"]
    merged = await db_client.post(
        "/api/v1/mpi/merge",
        headers=officer.headers(purpose="IDENTITY_RESOLUTION"),
        json={
            "source_identity_id": source.json()["id"],
            "target_identity_id": survivor.json()["id"],
            "reason": "Wave 2B.3c historical consent",
            "evidence": merge_evidence("wave2b3c-hist"),
        },
    )
    assert merged.status_code in {200, 201}
    fetched = await db_client.get(
        f"/api/v1/clinical/consents/{historical_id}",
        headers=clinician.headers(purpose="TREATMENT"),
    )
    assert fetched.json()["patient_identity_id"] == source.json()["id"]
    created = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(source.json()["id"]),
    )
    assert created.json()["patient_identity_id"] == survivor.json()["id"]
    retired = await _active_patient(db_client, registrar)
    async with db_engine.begin() as connection:
        await connection.execute(
            text("UPDATE patient_identities SET lifecycle_status = 'RETIRED' WHERE id = :id"),
            {"id": retired},
        )
    rejected = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(retired),
    )
    assert rejected.status_code == 409
    missing = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(str(uuid4())),
    )
    assert missing.status_code == 404


@requires_db
async def test_consent_concurrency_facility_and_app_dml(db_client, db_engine) -> None:
    clinician = await seed_actor(db_engine, role_code=RoleCode.CLINICIAN)
    registrar = await seed_actor(
        db_engine, role_code=RoleCode.REGISTRAR, organization_id=clinician.organization_id
    )
    patient_id = await _active_patient(db_client, registrar)
    created = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, note="concurrent amend"),
    )
    consent_id = created.json()["id"]

    async def amend() -> object:
        return await db_client.post(
            f"/api/v1/clinical/consents/{consent_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"note_text": "amended once"},
        )

    first, second = await asyncio.gather(amend(), amend())
    assert sorted([first.status_code, second.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CONSENT_AMENDED'
                """
            ),
            {"id": consent_id},
        )
        assert events.scalar_one() == 1

    revoke_row = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, note="concurrent revoke"),
    )
    revoke_id = revoke_row.json()["id"]

    async def revoke() -> object:
        return await db_client.post(
            f"/api/v1/clinical/consents/{revoke_id}/revoke",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    left, right = await asyncio.gather(revoke(), revoke())
    assert sorted([left.status_code, right.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        revoke_events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CONSENT_REVOKED'
                """
            ),
            {"id": revoke_id},
        )
        assert revoke_events.scalar_one() == 1

    eie_row = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, note="concurrent eie"),
    )
    eie_id = eie_row.json()["id"]

    async def void() -> object:
        return await db_client.post(
            f"/api/v1/clinical/consents/{eie_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    void_left, void_right = await asyncio.gather(void(), void())
    assert sorted([void_left.status_code, void_right.status_code]) == [200, 409]
    async with db_engine.connect() as connection:
        eie_events = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CONSENT_ENTERED_IN_ERROR'
                """
            ),
            {"id": eie_id},
        )
        assert eie_events.scalar_one() == 1

    race = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, note="amend vs revoke"),
    )
    race_id = race.json()["id"]

    async def amend_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/consents/{race_id}/amend",
            headers=clinician.headers(purpose="TREATMENT"),
            json={"note_text": "raced amend"},
        )

    async def revoke_race() -> object:
        return await db_client.post(
            f"/api/v1/clinical/consents/{race_id}/revoke",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    raced_left, raced_right = await asyncio.gather(amend_race(), revoke_race())
    codes = {raced_left.status_code, raced_right.status_code}
    assert 200 in codes
    assert codes <= {200, 409}
    async with db_engine.connect() as connection:
        row = await connection.execute(
            text("SELECT status FROM consents WHERE id = :id"),
            {"id": race_id},
        )
        assert row.scalar_one() == "REVOKED"
        revoked_count = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CONSENT_REVOKED'
                """
            ),
            {"id": race_id},
        )
        amended_count = await connection.execute(
            text(
                """
                SELECT count(*) FROM audit_events
                WHERE resource_id = :id AND action = 'CONSENT_AMENDED'
                """
            ),
            {"id": race_id},
        )
        assert revoked_count.scalar_one() == 1
        assert amended_count.scalar_one() in {0, 1}

    terminal = await db_client.post(
        "/api/v1/clinical/consents",
        headers=clinician.headers(purpose="TREATMENT"),
        json=_consent(patient_id, note="revoke vs eie"),
    )
    terminal_id = terminal.json()["id"]

    async def revoke_terminal() -> object:
        return await db_client.post(
            f"/api/v1/clinical/consents/{terminal_id}/revoke",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    async def eie_terminal() -> object:
        return await db_client.post(
            f"/api/v1/clinical/consents/{terminal_id}/entered-in-error",
            headers=clinician.headers(purpose="TREATMENT"),
        )

    term_left, term_right = await asyncio.gather(revoke_terminal(), eie_terminal())
    term_codes = {term_left.status_code, term_right.status_code}
    assert 200 in term_codes
    assert term_codes <= {200, 409}
    async with db_engine.connect() as connection:
        status = await connection.execute(
            text("SELECT status FROM consents WHERE id = :id"),
            {"id": terminal_id},
        )
        final = status.scalar_one()
        assert final in {"REVOKED", "ENTERED_IN_ERROR"}
        revoked_n = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM audit_events
                    WHERE resource_id = :id AND action = 'CONSENT_REVOKED'
                    """
                ),
                {"id": terminal_id},
            )
        ).scalar_one()
        eie_n = (
            await connection.execute(
                text(
                    """
                    SELECT count(*) FROM audit_events
                    WHERE resource_id = :id AND action = 'CONSENT_ENTERED_IN_ERROR'
                    """
                ),
                {"id": terminal_id},
            )
        ).scalar_one()
        assert revoked_n + eie_n == 1

    in_scope = new_id()
    out_of_scope = new_id()
    async with db_engine.begin() as connection:
        for facility_id, code in ((in_scope, "CIN"), (out_of_scope, "COUT")):
            await connection.execute(
                FacilityModel.__table__.insert().values(
                    id=facility_id,
                    organization_id=clinician.organization_id,
                    name=code,
                    code=code,
                    facility_type=FacilityType.HOSPITAL_SITE,
                    status=FacilityStatus.ACTIVE,
                )
            )
        role_id = (
            await connection.execute(
                select(RoleModel.id).where(RoleModel.code == RoleCode.CLINICIAN)
            )
        ).scalar_one()
        bound_user = new_id()
        subject = f"user-{bound_user}"
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
                organization_id=clinician.organization_id,
                facility_id=in_scope,
                role_id=role_id,
                status=MembershipStatus.ACTIVE,
            )
        )
    bound = SeededActor(bound_user, subject, clinician.organization_id, mint_token(sub=subject))
    allowed = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=_headers(bound, "TREATMENT", str(in_scope)),
    )
    assert allowed.status_code == 200
    denied = await db_client.get(
        f"/api/v1/clinical/consents/{consent_id}",
        headers=_headers(bound, "TREATMENT", str(out_of_scope)),
    )
    assert denied.status_code == 403
    assert "Consent Document" not in denied.text
    assert "Signed at registration" not in denied.text

    async with db_engine.connect() as connection:
        provenance = await connection.execute(
            text("SELECT provenance_id FROM consents WHERE id = :id"),
            {"id": consent_id},
        )
        provenance_id = provenance.scalar_one()
    async with db_engine.connect() as connection:
        with pytest.raises(Exception, match="foreign key|fk_consents_provenance"):
            async with connection.begin():
                await connection.execute(
                    text(
                        """
                        INSERT INTO consents (
                            id, patient_identity_id, organization_id, category,
                            scope, decision, source, status, recorded_at, version,
                            provenance_id
                        )
                        SELECT gen_random_uuid(), patient_identity_id, organization_id,
                               category, scope, decision, source, 'ACTIVE', now(), 1, :bad
                        FROM consents WHERE id = :id
                        """
                    ),
                    {"id": consent_id, "bad": uuid4()},
                )
        with pytest.raises(Exception, match="insert-only|foreign key|fk_consents_provenance"):
            async with connection.begin():
                await connection.execute(
                    text("DELETE FROM clinical_provenances WHERE id = :id"),
                    {"id": provenance_id},
                )
        with pytest.raises(Exception, match="invalid consent status transition|immutable"):
            async with connection.begin():
                await connection.execute(
                    text("UPDATE consents SET status = 'ACTIVE' WHERE id = :id"),
                    {"id": consent_id},
                )

    engine = create_async_engine(APP_DML_URL, pool_pre_ping=True)
    try:
        async with engine.connect() as connection:
            with pytest.raises(Exception, match="permission denied|cannot be deleted"):
                async with connection.begin():
                    await connection.execute(
                        text("DELETE FROM consents WHERE id = :id"),
                        {"id": consent_id},
                    )
            with pytest.raises(Exception, match="immutable"):
                async with connection.begin():
                    await connection.execute(
                        text("UPDATE consents SET code_display = 'Bypass' WHERE id = :id"),
                        {"id": consent_id},
                    )
            with pytest.raises(Exception, match="permission denied"):
                async with connection.begin():
                    await connection.execute(text("TRUNCATE consents"))
    finally:
        await engine.dispose()
