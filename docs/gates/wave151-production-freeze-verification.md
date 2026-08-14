# Wave 1.5.1 — Production Freeze Verification

**Verdict:** PRODUCTION FREEZE — PASS WITH NOTE  
**Date:** 2026-08-14  
**Wave 2:** NOT STARTED

This report verifies reproducibility of the already implemented Wave 1 / Wave 1.5 foundation. It is not a HIPAA, ISO 27001, or SOC 2 certification.

## Final scorecard

| ID | Item | Result |
|---|---|---|
| A | Git status | PASS WITH NOTE |
| B | Docker rebuild | PASS |
| C | Docker compose status | PASS |
| D | Health live | PASS |
| E | Health ready | PASS |
| F | Migration head | PASS |
| G | Database schema | PASS |
| H | Legacy evidence compatibility | PASS WITH NOTE |
| I | RBAC | PASS |
| J | Purpose-of-use | PASS |
| K | Matching | PASS |
| L | Probe | PASS |
| M | Merge concurrency | PASS |
| N | Unmerge concurrency | PASS |
| O | Duplicate identifier concurrency | PASS |
| P | Anonymous identity | PASS |
| Q | Security regression | PASS |
| R | API contract | PASS |
| S | Clinical boundary | PASS |
| T | Ruff | PASS |
| U | Mypy | PASS |
| V | Pytest | PASS |
| W | Port verification | PASS |
| X | Architecture | PASS |

## A. Git status — PASS WITH NOTE

- Repository initialized: yes (`.git` present)
- Branch: `master`
- Commits: none (`git log` empty; `git ls-files` = 0)
- Diff / cached: empty (nothing staged or committed)
- Tracked files: none
- Untracked: `.github/`, `.gitignore`, `README.md`, `backend/`, `docs/`

Wave 1.5 is reproducible from the **working tree** and the rebuilt Docker image. It is **not** reproducible from Git history because no first commit exists. No commit was created in this verification.

## B–C. Docker rebuild and compose — PASS

- `docker compose build --no-cache backend` succeeded
- Image `backend-backend:latest` digest `sha256:c3c642e8…` (new vs pre-rebuild `sha256:ed861a4d…`)
- Container `backend-backend-1` recreated from that image
- `docker compose up -d` touched only this project's stack
- `gsai-minio` container id `bbbe127212d6…` and start time `2026-07-26T17:37:26Z` unchanged

| Service | Status |
|---|---|
| backend-backend-1 | Up (new image) |
| backend-postgres-1 | Up (healthy) |
| backend-redis-1 | Up (healthy) |
| backend-minio-1 | Up (healthy) |

The rebuilt image contains Wave 1.5 modules (`Purpose` catalog, `20260813_0003`, canonical/evidence domain).

## D–E. Health — PASS

`GET http://localhost:9100/api/v1/health/live` → `{"status":"alive"}`

`GET http://localhost:9100/api/v1/health/ready` →

```json
{"status":"ready","checks":{"postgres":"ok","redis":"ok","object_storage":"ok"}}
```

## F. Migration head — PASS

`alembic current` = `20260813_0003`  
`alembic heads` = `20260813_0003`  
Chain: `0001` → `0002` → `0003`. Historical files were not rewritten. Downgrade was not executed.

## G. Schema — PASS

18 public tables. UUID PK on `patient_identities`. Active identifier uniqueness:

- `uq_patient_identifiers_global_active`
- `uq_patient_identifiers_org_active`

Lifecycle CHECKs, merge not-self, merge reason required, cluster active-membership unique index, merge idempotency unique key, insert-only triggers on audit / merge / provenance / probes. No clinical tables.

## H. Legacy evidence — PASS WITH NOTE

| Shape | Rows |
|---|---|
| object (pre-1.5) | 15 |
| array (structured) | 27+ |

Old rows look like `{"ticket":"MPI-1"}`. They were **not** rewritten. The application parses evidence only on **incoming** merge/unmerge requests. Stored history is not re-validated. Idempotent retry and unmerge load operation ids/status, not evidence shape. A future additive data migration is optional; not required for current correctness. No destructive migration was created.

## I–Q. Identity / security — PASS

Pytest: **86 passed** (PostgreSQL `5433`, Redis `6380`), including concurrency, uniqueness, matching, canonical merge resolution, purpose, RBAC, probe, anonymous, and security suites.

Runtime permission assignment is the `role_permissions` join. `ROLE_PERMISSIONS` is definition/seed only and is not imported on the authorization path.

`SELECT FOR UPDATE` remains in `get_identity_for_update`. Redis is not used as a lock.

## R. API contract — PASS

All routes remain under `/api/v1/`. OpenAPI on the live backend has no `/api/v2/` and no `PUT /patients`.

## S. Clinical boundary — PASS

No encounter/diagnosis/observation/medication/treatment/clinical_note/laboratory/consent/FHIR tables. Executable `backend/app` hits are organization taxonomy (`LABORATORY`) and the Wave 0 `clinical_governance` placeholder comment. No Wave 2 code.

## T–V. Quality gates — PASS

- `ruff check app tests` pass
- `ruff format --check app tests` pass
- `mypy` 92 files, no issues
- `pytest` 86 passed

## W. Ports — PASS

| Mapping | Owner |
|---|---|
| `9100:8000` | EMR backend |
| `5433:5432` | EMR PostgreSQL |
| `6380:6379` | EMR Redis |
| `9101:9000` | EMR MinIO API |
| `9002:9001` | EMR MinIO console |
| `9000-9001` | `gsai-minio` (untouched) |

Backend → MinIO remains `http://minio:9000`.

## X. Architecture — PASS

Modular monolith, FastAPI, PostgreSQL, SQLAlchemy async, Redis, MinIO, Alembic, OIDC/JWT, PDP, audit, provenance, MPI, organization, IAM. No microservices, Kafka, Kubernetes, blockchain, vector DB, FHIR server, or AI service.

## Docker runtime (localhost:9100) — PASS after grant fix

First live MPI calls failed with `permission denied for table users` because Alembic runs as `php_admin` and the API uses `app_dml`. Integration tests used `php_admin`, so they hid this.

Fix applied (deployment only, no architecture change):

- Ran `backend/scripts/grant_dev_privileges.sql`
- Documented it as required after migrate
- History tables remain INSERT/SELECT only for `app_dml`

Repeatable check: `PYTHONPATH=. .venv/bin/python scripts/verify_docker_runtime.py`

Live results after grants: unauthenticated 401, unprovisioned 403, missing/unknown purpose 422, REGISTRATION create, ADMINISTRATION lookup, EMERGENCY anonymous, IDENTITY_RESOLUTION probe (no new identity, no raw NIK), unauthorized merge 403, empty evidence 422, IDOR/cross-org 404, PII masked.

## Notes that keep the verdict from a clean PASS

1. No first Git commit — history is not the source of truth yet.
2. 15 legacy object-shaped merge evidence rows remain by design.
3. DML grants are operational, not part of Alembic. `docker compose up` after migrate still requires the grant script on a database that was migrated as `php_admin`.

None of these are open P0/P1 product defects after the grant fix.

## Stop

WAVE 1.5.1 VERIFICATION COMPLETE  
PRODUCTION FREEZE — PASS WITH NOTE  
WAVE 2 NOT STARTED  
STOP.
