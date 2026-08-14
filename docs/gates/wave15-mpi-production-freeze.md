# MPI Production Freeze Gate — Wave 1.5 Final Remediation

**Verdict:** PASS / PRODUCTION-READY FOUNDATION  
**Date:** 2026-08-14  
**Wave 2:** NOT STARTED

This gate does not claim HIPAA, ISO 27001, or SOC 2 certification. Controls exist; formal assessment has not been performed.

## 1. Executive summary

Wave 1.5 closed the six remaining findings from the prior PASS WITH P2 gate. Purpose-of-use is allow-listed, probe-only matches are persisted without raw identifiers, permission assignment is read from the database, matching resolves MERGED identities to the canonical survivor, merge evidence is mandatory and structured, and Git was initialized without an automatic commit.

P0 = 0, P1 = 0, P2 = 0. Critical security, concurrency, uniqueness, audit, provenance, purpose, RBAC, canonical-match, and evidence tests passed. No clinical tables or Wave 2 APIs were added. Wave 0 ports and `gsai-minio` are unchanged.

## 2. Findings before remediation

| ID | Sev | Finding |
|---|---|---|
| H2 | P2 | `X-Purpose` accepted any non-empty string |
| H3 | P2 | Probe-only match was evaluated but not persisted |
| H4 | P2 | Runtime permissions came from in-code `ROLE_PERMISSIONS` |
| H5 | P2 | Matcher could compare MERGED rows as distinct targets |
| H6 | P2 | Merge evidence could be `{}` |
| H7 | P3 | Workspace had no `.git` directory |

Prior P1 concurrent merge/unmerge race was already fixed and was not regressed.

## 3. Findings after remediation

| ID | Disposition |
|---|---|
| H2 | Fixed — catalog enum + 422 for missing/unknown |
| H3 | Fixed — insert-only `identity_match_probes` |
| H4 | Fixed — `role_permissions` join at principal load |
| H5 | Fixed — canonical walk before match; matcher skips MERGED/RETIRED |
| H6 | Fixed — structured evidence required and persisted |
| H7 | Fixed — `git init` only; no commit; no global Git config change |

## 4. P0 / P1 / P2 / P3 scorecard

| Severity | Open |
|---|---|
| P0 | 0 |
| P1 | 0 |
| P2 | 0 |
| P3 | 0 open findings. Residual process note: repository has no first commit yet (intentional). |

## 5. Files changed

New application/test/docs files include purpose, evidence, and canonical domain modules; Alembic `20260813_0003`; Wave 1.5 unit and integration tests; purpose-of-use, canonical-resolution, source-control, and this gate document.

Modified: MPI service/repository/models/enums/matching, IAM principal loader, API deps/schemas/MPI router, Alembic env, existing Wave 1 tests, and identity/IAM/migration documentation. `docker-compose.yml` was not changed.

## 6. Database migrations added

`20260813_0003` revises `20260813_0002`. Creates insert-only `identity_match_probes` with purpose/status CHECKs, indexes, and an immutability trigger. Upgrade and downgrade are present. Historical migrations `0001` and `0002` were not edited. Downgrade was not executed against the populated local database. Alembic current = `20260813_0003` (head).

## 7. API contract changes

Still under `/api/v1/`. No `/api/v2/`.

Breaking only where required for security:

- `X-Purpose` must be one of the eight catalog values after normalization. Unknown → `422`.
- `POST /api/v1/mpi/merge` and `/unmerge` require `evidence` as a non-empty list of structured items (was a free-form object, including `{}`).

## 8. Purpose-of-use policy

Catalog: `REGISTRATION`, `IDENTITY_RESOLUTION`, `EMERGENCY`, `CARE_COORDINATION`, `ADMINISTRATION`, `PATIENT_ACCESS`, `AUDIT`, `SYSTEM_OPERATION`.

Missing/empty/unknown → `422`. Normalized consistently. Recorded on audit and match probes. Does not grant authorization. PDP remains authoritative. See `docs/mpi/purpose-of-use.md`.

## 9. Authorization model

Permission definitions remain in code (`Permission`, seed `ROLE_PERMISSIONS`). Runtime assignment is `users` → `organization_memberships` → `roles` → `role_permissions` → `permissions`. PDP evaluates permission codes, organization membership, and facility scope. Empty `facility_ids` means organization-wide, not platform-wide. Unknown permission and missing membership deny. No `if role == doctor`.

## 10. Identifier uniqueness model

Unchanged. Database unique indexes remain authoritative. Global vs organization-scoped uniqueness preserved. Application SELECT→INSERT is not sufficient. Concurrent duplicate tests still pass.

## 11. Matching model

`deterministic-v1`. Matching is evidence only. No automatic merge, confirmation, or access grant. Probe-only attempts persist `identity_match_probes` without raw NIK/BPJS/phone/email. Pair matches still upsert `identity_match_candidates`.

## 12. Canonical identity resolution

`MERGED` → walk `surviving_identity_id` (max 8 hops) to the active/anonymous survivor. Cycle, broken link, missing row, or `RETIRED` fails safely (`409`). Matcher does not mutate lifecycle. See `docs/mpi/canonical-resolution.md`.

## 13. Anonymous identity behavior

Unchanged. Opaque UUID, no required NIK/MRN/phone/email, temporary display label is not a matching key, no silent merge.

## 14. Merge model

Explicit, authorized, insert-only. Structured evidence mandatory. Source row retained as `MERGED`. Self-merge, retired, already-merged target, cycle, and identifier collision still rejected.

## 15. Unmerge model

New `UNMERGE` row pointing at the original merge. Original merge remains immutable. Source returns to `ACTIVE`. Concurrent unmerge: one success, one deterministic `409`.

## 16. Concurrency guarantees

PostgreSQL `SELECT FOR UPDATE` on identity rows (UUID lock order) remains the authority. Redis is not used as a correctness lock. Concurrent A→B / A→C: exactly one successful merge.

## 17. Audit guarantees

Sensitive MPI mutations remain audited, including `MATCH_CANDIDATE_CREATED`. Purpose is recorded. Raw NIK/BPJS/passport/phone/email are not written into audit metadata. Audit is insert-only and separate from application logs.

## 18. Provenance guarantees

`identity_provenances` remains a separate insert-only table. Probe persistence writes `MATCH_CANDIDATE` provenance. Historical provenance is not deleted.

## 19. PII protection

Sensitive identifiers remain masked in responses. No `GET /patients?name=`. Unauthorized/unknown reads remain `404`. Probe and evidence paths reject raw sensitive identifier storage.

## 20. Security test results

Auth, authorization, purpose, identifier, matching, merge, and unmerge matrix cases in `test_wave1_security.py` and `test_wave15_hardening.py` passed as part of the full suite.

## 21. Unit test results

Purpose, evidence, canonical resolution, matcher skip of MERGED/RETIRED, and existing Wave 1 domain tests passed.

## 22. Integration test results

**86 passed** against PostgreSQL `localhost:5433` and Redis `localhost:6380`.

## 23. Ruff result

`ruff check app tests` — all checks passed.  
`ruff format --check app tests` — 108 files already formatted.

## 24. Mypy result

Success: no issues found in 92 source files.

## 25. Docker verification

This project's Compose services are up: `backend-backend-1`, `backend-postgres-1`, `backend-redis-1`, `backend-minio-1`. `GET /api/v1/health/live` on host `9100` returns alive. `gsai-minio` was not modified.

The running backend container image was not rebuilt in this remediation. Behavioral proof is the in-process pytest ASGI suite against the same database.

## 26. Port verification

| Service | Mapping | Status |
|---|---|---|
| EMR backend | `9100:8000` | unchanged |
| PostgreSQL | `5433:5432` | unchanged |
| Redis | `6380:6379` | unchanged |
| EMR MinIO API | `9101:9000` | unchanged |
| EMR MinIO console | `9002:9001` | unchanged |
| Backend → MinIO | `http://minio:9000` | unchanged |
| `gsai-minio` | host `9000-9001` | untouched |

## 27. Clinical boundary scan

No encounter/diagnosis/medication/observation/FHIR tables exist. Hits classified as:

- `OrganizationType.LABORATORY` / `FacilityType.LABORATORY_SITE` — organization taxonomy, not a lab module
- `clinical_governance` — Wave 0 placeholder types only; no tables or APIs
- Documentation prohibitions and comments — acceptable
- Object storage / correlation / logging field names — infrastructure, not clinical EMR

Wave 2 code was not created.

## 28. Remaining risks

- No first Git commit yet (operator action). History is not reviewable until committed.
- Running Docker backend image may lag this source tree until rebuilt.
- Formal compliance/certification has not been assessed.
- Historical `identity_merge_operations.evidence` JSONB may still contain pre-hardening object-shaped rows; new writes are structured arrays.
- Seed `ROLE_PERMISSIONS` can still drift from `role_permissions` if future permission definitions are added without a data migration.

None of these are open P0/P1/P2 product defects in the identity foundation.

## 29. Explicit Wave 2 readiness

The identity foundation is ready for a later Wave 2 clinical design. Wave 2 is **not started**. Do not create encounters, diagnoses, laboratory, medication, treatment, FHIR clinical resources, consent UI, or clinical APIs in this freeze.

**WAVE 1.5 FINAL REMEDIATION COMPLETE**  
**MPI PRODUCTION FREEZE GATE: PASS**  
**WAVE 2 NOT STARTED**  
**STOP.**
