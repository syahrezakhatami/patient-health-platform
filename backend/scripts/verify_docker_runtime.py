"""Verify the rebuilt Docker backend on http://localhost:9100.

Run from backend/:

    PYTHONPATH=. .venv/bin/python scripts/verify_docker_runtime.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.modules.authorization.domain.catalog import RoleCode
from app.modules.iam.domain.enums import MembershipStatus, UserStatus
from app.modules.iam.infrastructure.models import OrganizationMembershipModel, RoleModel, UserModel
from app.modules.organization.domain.enums import OrganizationStatus, OrganizationType
from app.modules.organization.infrastructure.models import OrganizationModel
from app.shared.types.ids import new_id

BASE = "http://localhost:9100"
SECRET = "dev-only-not-for-production-change-me-32b"
DB = "postgresql+asyncpg://php_admin:php_admin_dev_only@localhost:5433/php_dev"
failures: list[str] = []


def mint(sub: str) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": sub,
            "iss": "http://localhost:8080/realms/php-dev",
            "aud": "php-api",
            "exp": now + timedelta(minutes=10),
            "iat": now,
        },
        SECRET,
        algorithm="HS256",
    )


def unique_nik() -> str:
    return f"{uuid4().int % 10**16:016d}"


def unique_mrn() -> str:
    return f"RT-{uuid4().hex[:10].upper()}"


def evidence(ref: str) -> list[dict[str, str]]:
    return [
        {
            "evidence_type": "STAFF_REVIEW",
            "evidence_source": "freeze-verify",
            "evidence_reference": ref,
            "reviewer_reason": "Docker runtime verification",
            "reviewed_at": "2026-08-13T17:30:00+00:00",
        }
    ]


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}{': ' + detail if detail else ''}")
    if not ok:
        failures.append(name)


async def seed(engine, role_code: str, organization_id=None):
    subject = f"user-{new_id()}"
    user_id = new_id()
    async with engine.begin() as connection:
        if organization_id is None:
            organization_id = new_id()
            await connection.execute(
                OrganizationModel.__table__.insert().values(
                    id=organization_id,
                    name=f"Freeze {organization_id.hex[:8]}",
                    code=f"FRZ{organization_id.hex[:8]}".upper(),
                    organization_type=OrganizationType.HOSPITAL,
                    status=OrganizationStatus.ACTIVE,
                )
            )
        role = (
            await connection.execute(select(RoleModel.id).where(RoleModel.code == role_code))
        ).scalar_one()
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
                organization_id=None if role_code == RoleCode.PLATFORM_ADMIN else organization_id,
                facility_id=None,
                role_id=role,
                status=MembershipStatus.ACTIVE,
            )
        )
    return organization_id, mint(subject)


async def main() -> int:
    engine = create_async_engine(DB, pool_pre_ping=True)
    async with httpx.AsyncClient(base_url=BASE, timeout=15.0) as client:
        live = await client.get("/api/v1/health/live")
        check("health/live", live.status_code == 200 and live.json()["status"] == "alive")
        ready = await client.get("/api/v1/health/ready")
        body = ready.json()
        check(
            "health/ready",
            ready.status_code == 200
            and body["status"] == "ready"
            and body["checks"] == {"postgres": "ok", "redis": "ok", "object_storage": "ok"},
            json.dumps(body),
        )

        unauth = await client.post("/api/v1/mpi/identities", json={"given_name": "X"})
        check("unauthenticated denied", unauth.status_code == 401, str(unauth.status_code))

        nobody = mint("nobody-unprovisioned")
        unprov = await client.post(
            "/api/v1/mpi/identities",
            headers={
                "Authorization": f"Bearer {nobody}",
                "X-Organization-Id": str(uuid4()),
                "X-Purpose": "REGISTRATION",
            },
            json={
                "given_name": "No",
                "family_name": "User",
                "birth_date": "1990-01-01",
                "identifiers": [
                    {
                        "identifier_system": "id.nik",
                        "identifier_type": "NIK",
                        "identifier_value": unique_nik(),
                    }
                ],
            },
        )
        check("unprovisioned denied", unprov.status_code == 403, str(unprov.status_code))

        org_id, registrar_token = await seed(engine, RoleCode.REGISTRAR)
        _, officer_token = await seed(engine, RoleCode.IDENTITY_OFFICER, organization_id=org_id)
        other_org, other_token = await seed(engine, RoleCode.REGISTRAR)

        missing_purpose = await client.post(
            "/api/v1/mpi/identities",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
            },
            json={
                "given_name": "A",
                "family_name": "B",
                "birth_date": "1991-01-01",
                "identifiers": [
                    {
                        "identifier_system": "id.nik",
                        "identifier_type": "NIK",
                        "identifier_value": unique_nik(),
                    }
                ],
            },
        )
        check("missing purpose 422", missing_purpose.status_code == 422, str(missing_purpose.status_code))

        unknown_purpose = await client.post(
            "/api/v1/mpi/identities",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "unknown-purpose",
            },
            json={
                "given_name": "A",
                "family_name": "B",
                "birth_date": "1991-01-01",
                "identifiers": [
                    {
                        "identifier_system": "id.nik",
                        "identifier_type": "NIK",
                        "identifier_value": unique_nik(),
                    }
                ],
            },
        )
        check("unknown purpose 422", unknown_purpose.status_code == 422, str(unknown_purpose.status_code))

        nik = unique_nik()
        created = await client.post(
            "/api/v1/mpi/identities",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "REGISTRATION",
            },
            json={
                "given_name": "Runtime",
                "family_name": "Verify",
                "birth_date": "1985-05-05",
                "identifiers": [
                    {
                        "identifier_system": "id.nik",
                        "identifier_type": "NIK",
                        "identifier_value": nik,
                    }
                ],
            },
        )
        check("create identity REGISTRATION", created.status_code in {200, 201}, created.text[:200])
        identity = created.json() if created.status_code in {200, 201} else {}
        check("PII masked", bool(identity) and nik not in created.text and "*" in created.text)
        identity_id = identity.get("id")

        lookup = await client.post(
            "/api/v1/mpi/identities/lookup",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "ADMINISTRATION",
            },
            json={
                "identifier_system": "id.nik",
                "identifier_type": "NIK",
                "identifier_value": nik,
            },
        )
        check(
            "lookup same org",
            lookup.status_code == 200 and lookup.json().get("id") == identity_id,
            str(lookup.status_code),
        )

        cross = await client.get(
            f"/api/v1/mpi/identities/{identity_id}",
            headers={
                "Authorization": f"Bearer {other_token}",
                "X-Organization-Id": str(other_org),
                "X-Purpose": "ADMINISTRATION",
            },
        )
        check("cross-org read 404", cross.status_code == 404, str(cross.status_code))

        idor = await client.get(
            f"/api/v1/mpi/identities/{uuid4()}",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "ADMINISTRATION",
            },
        )
        check(
            "IDOR 404 no leak",
            idor.status_code == 404 and "sqlalchemy" not in idor.text.lower(),
            str(idor.status_code),
        )

        anonymous = await client.post(
            "/api/v1/mpi/identities/anonymous",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "EMERGENCY",
            },
            json={},
        )
        check(
            "anonymous EMERGENCY",
            anonymous.status_code in {200, 201}
            and anonymous.json()["lifecycle_status"] == "ANONYMOUS"
            and anonymous.json()["identifiers"] == [],
            str(anonymous.status_code),
        )

        async with engine.connect() as connection:
            before_identities = (
                await connection.execute(text("SELECT count(*) FROM patient_identities"))
            ).scalar_one()
        probe = await client.post(
            "/api/v1/mpi/match",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "IDENTITY_RESOLUTION",
            },
            json={
                "identifiers": [
                    {
                        "identifier_system": "id.nik",
                        "identifier_type": "NIK",
                        "identifier_value": nik,
                    }
                ]
            },
        )
        check("probe-only match", probe.status_code == 200, probe.text[:160])
        async with engine.connect() as connection:
            after_identities = (
                await connection.execute(text("SELECT count(*) FROM patient_identities"))
            ).scalar_one()
            raw_probe = (
                await connection.execute(
                    text(
                        """
                        SELECT count(*) FROM identity_match_probes
                        WHERE organization_id = :org
                          AND (evidence_types::text LIKE :nik OR reasons::text LIKE :nik)
                        """
                    ),
                    {"org": org_id, "nik": f"%{nik}%"},
                )
            ).scalar_one()
            probe_rows = (
                await connection.execute(
                    text(
                        """
                        SELECT count(*) FROM identity_match_probes
                        WHERE organization_id = :org AND purpose = 'IDENTITY_RESOLUTION'
                        """
                    ),
                    {"org": org_id},
                )
            ).scalar_one()
        check("probe did not create identity", after_identities == before_identities)
        check("probe has no raw NIK", raw_probe == 0)
        check("probe persisted", probe_rows >= 1)

        other_identity = await client.post(
            "/api/v1/mpi/identities",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "REGISTRATION",
            },
            json={
                "given_name": "Other",
                "family_name": "Person",
                "birth_date": "1986-06-06",
                "identifiers": [
                    {
                        "identifier_system": "hospital-mrn",
                        "identifier_type": "MRN",
                        "identifier_value": unique_mrn(),
                    }
                ],
            },
        )
        other_identity_id = other_identity.json().get("id")
        denied_merge = await client.post(
            "/api/v1/mpi/merge",
            headers={
                "Authorization": f"Bearer {registrar_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "IDENTITY_RESOLUTION",
            },
            json={
                "source_identity_id": identity_id,
                "target_identity_id": other_identity_id,
                "reason": "not allowed",
                "evidence": evidence("denied"),
            },
        )
        check("unauthorized merge 403", denied_merge.status_code == 403, str(denied_merge.status_code))

        empty_evidence = await client.post(
            "/api/v1/mpi/merge",
            headers={
                "Authorization": f"Bearer {officer_token}",
                "X-Organization-Id": str(org_id),
                "X-Purpose": "IDENTITY_RESOLUTION",
            },
            json={
                "source_identity_id": identity_id,
                "target_identity_id": other_identity_id,
                "reason": "needs evidence",
                "evidence": [],
            },
        )
        check("empty evidence 422", empty_evidence.status_code == 422, str(empty_evidence.status_code))

        openapi = await client.get("/api/v1/openapi.json")
        paths = list(openapi.json().get("paths", {})) if openapi.status_code == 200 else []
        check("no /api/v2", all(not item.startswith("/api/v2") for item in paths) and bool(paths))
        check("no PUT /patients", not any("/patients" in item for item in paths))

    await engine.dispose()
    print(f"\nDocker runtime checks failed: {len(failures)}")
    for item in failures:
        print(f" - {item}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
