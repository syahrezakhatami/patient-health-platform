# Wave 1.5 — Final Freeze / Baseline

**Status:** FROZEN  
**Date:** 2026-08-14  
**Implementation gate:** PASS (P0 = 0, P1 = 0, P2 = 0)  
**Deployment verification:** PASS WITH NOTE  
**Wave 2A:** STARTED (clinical foundation only; Wave 2 is not complete)

This is the official identity-foundation baseline. Later work must treat the items below as frozen unless a dedicated exception is approved.

This baseline is not a HIPAA, ISO 27001, or SOC 2 certification.

## What is frozen

| Layer | Baseline |
|---|---|
| Architecture | Modular monolith, Architecture v2.1 |
| Backend | FastAPI, Pydantic, SQLAlchemy 2 asyncio, asyncpg, Alembic |
| Data stores | PostgreSQL, Redis, MinIO |
| Authz | OIDC/JWT, Wave1PolicyPDP, deny by default |
| Identity | MPI only. Person is conceptual. Canonical key is `patient_identities.id` (UUID) |
| Schema head | Identity freeze: `20260813_0003`. Wave 2A adds `20260814_0004` on top. Do not edit `0001`–`0003`. |
| API | `/api/v1/` only |

## Ports (do not change)

| Service | Host mapping | Internal |
|---|---|---|
| EMR backend | `9100:8000` | container 8000 |
| PostgreSQL | `5433:5432` | container 5432 |
| Redis | `6380:6379` | container 6379 |
| EMR MinIO API | `9101:9000` | `http://minio:9000` |
| EMR MinIO console | `9002:9001` | container 9001 |
| `gsai-minio` | host `9000-9001` | **other stack — do not touch** |

## Identity invariants

- NIK, MRN, BPJS, phone, email, and name are attributes, never primary keys.
- Lifecycle: `ANONYMOUS → ACTIVE|MERGED|RETIRED`; `ACTIVE → MERGED|RETIRED`; `MERGED → ACTIVE` (unmerge only); `RETIRED` terminal.
- Matching is evidence. It is not merge, authorization, consent, or clinical access.
- No automatic merge. No silent merge of anonymous identities.
- Concurrent merge A→B and A→C: exactly one success. PostgreSQL `SELECT FOR UPDATE` is authoritative. Redis is not a lock.
- Database unique indexes are authoritative for identifier uniqueness.
- Audit and provenance stay separate and insert-only.
- Sensitive identifiers are masked. No `GET /patients?name=`. Unknown/unauthorized reads return 404.

## Wave 1.5 controls included in this baseline

- Purpose catalog: `REGISTRATION`, `IDENTITY_RESOLUTION`, `EMERGENCY`, `CARE_COORDINATION`, `ADMINISTRATION`, `PATIENT_ACCESS`, `AUDIT`, `SYSTEM_OPERATION`. Unknown → 422. Purpose does not grant authorization.
- Runtime permission assignment from `role_permissions`. Catalog defines permissions; database assigns them.
- Probe-only match persisted on `identity_match_probes` without raw NIK/BPJS/phone/email. Probe does not create an identity.
- `MERGED` identities resolve to the canonical survivor before matching. `RETIRED` is not matchable.
- Merge/unmerge evidence is a mandatory structured list.

## Explicitly out of baseline (do not start)

Encounter, diagnosis, observation, laboratory, medication, treatment, clinical notes, allergy, immunization, procedure, consent UI, FHIR clinical resources, patient portal, AI/RAG/vector DB, PACS/DICOM, Kafka, blockchain, microservices, Kubernetes.

## Known baseline notes

1. Git is initialized on `master` with **no first commit**. The working tree is the current source. History is not yet the source of truth.
2. Some historical `identity_merge_operations.evidence` rows remain object-shaped. New writes are structured arrays. Do not rewrite history without an approved data migration.
3. After `alembic upgrade head` as `php_admin`, apply `backend/scripts/grant_dev_privileges.sql` so the Docker API role `app_dml` can run. Alembic does not grant DML.

## Verification references

- Implementation gate: `docs/gates/wave15-mpi-production-freeze.md`
- Deployment verification: `docs/gates/wave151-production-freeze-verification.md`
- Live Docker check: `backend/scripts/verify_docker_runtime.py`

## Stop

WAVE 1.5 FINAL FREEZE / BASELINE ESTABLISHED  
WAVE 2 NOT STARTED  
STOP.
