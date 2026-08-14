# Wave 2B.1 — Condition production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-14
**Wave 2A freeze:** `wave-2a-frozen` / `f051e3917e7f388a41e5f2f07f17f469c2d4b4ec`
**Wave 2B.2:** NOT STARTED
**Condition freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`) |
| HEAD | `f051e3917e7f388a41e5f2f07f17f469c2d4b4ec` = `wave-2a-frozen` |
| Wave 2A rewrite | **No.** Tag commit is unchanged. |
| Wave 2B.1 commit | **None.** Working tree dirty / untracked. |
| Alembic | `current == heads == 20260814_0006` (single head) |
| Migrations `0001`–`0005` | Untouched vs `wave-2a-frozen` |
| New migration | `20260814_0006` only |
| Ports | API `9100:8000`, Postgres `5433:5432`, Redis `6380:6379`, EMR MinIO `9101:9000` / `9002:9001` |
| Backend → MinIO | `http://minio:9000` |
| `gsai-minio` | Untouched (`9000`/`9001`, up 2 weeks) |
| API | `/api/v1/clinical/conditions*`. No `/api/v2/`. No DELETE. |

## 2. Files inspected

Clinical Condition path: `application/services.py`, `domain/enums.py`, `domain/lifecycle.py`, `infrastructure/models.py`, `infrastructure/repositories.py`, `api/v1/clinical.py`, `api/v1/schemas.py`, authorization catalog/PDP/purpose/`authorize.py`, logging, exception handlers, Alembic `0006`, `grant_dev_privileges.sql`, live PostgreSQL constraints/grants/triggers, Docker Compose runtime, Wave 1.5 / 2A / 2B.1 tests.

## 3. Files changed (this hardening gate)

- `backend/app/modules/clinical/application/services.py` — no-op status update is 409; no duplicate `CONDITION_STATUS_CHANGED`
- `backend/tests/integration/test_wave2b1_hardening.py` — concurrency, merge, encounter, authz, purpose, IDOR, `app_dml` DELETE
- `docs/gates/wave2b1-condition-hardening-gate.md` — this report

Wave 2B.1 implementation files remain uncommitted on the working tree. `0001`–`0005` were not edited. No new migration was required.

## 4. Migrations / Condition schema

`0006` revises `0005`. Live table `conditions`:

- UUID PK
- `patient_identity_id` FK → `patient_identities` `ON DELETE RESTRICT`
- `encounter_id` FK → `encounters` `ON DELETE RESTRICT` (nullable)
- `organization_id` / `facility_id` FKs `ON DELETE RESTRICT`
- CHECKs: category, clinical status, verification status, encounter-diagnosis requires encounter, period, non-empty code/system
- Indexes on patient, encounter, organization, recorded_at
- Provenance: `provenance_id` column (no FK; same pattern as notes). `clinical_provenances.subject_type` CHECK includes `CONDITION`
- Trigger `trg_conditions_history_immutable` / `prevent_condition_history_mutation`

Condition rows cannot be orphaned by deleting a patient, encounter, org, or facility (`RESTRICT`). Direct DELETE is blocked by the trigger and by `app_dml` lacking DELETE.

## 5. Condition lifecycle

Create defaults: `ACTIVE` + `CONFIRMED`. Cannot create as `ENTERED_IN_ERROR` (422).

Clinical transitions (service + tests): `ACTIVE → RESOLVED` allowed; illegal transitions 409. Verification may change along the documented machine; `ENTERED_IN_ERROR` is **not** a status-endpoint target (422 `use_entered_in_error`).

`ENTERED_IN_ERROR` is a dedicated operation. After it: API 409, service `assert_condition_mutable`, trigger rejects further updates and all deletes.

## 6. Identity binding

`patient_identity_id` is the canonical FK. No NIK/MRN PK.

| Lifecycle | New Condition |
|---|---|
| ACTIVE | Allowed |
| MERGED | Binds `surviving_identity_id` |
| RETIRED | 409 |
| Unknown | 404 |
| Cross-org | 404 (same message; no existence leak) |
| ANONYMOUS + `PROBLEM_LIST_ITEM` | 409 |
| ANONYMOUS + `ENCOUNTER_DIAGNOSIS` on `EMER` | Allowed |

Historical Condition rows are **not** rewritten after MPI merge (tested). Concurrent creates against a merged source both bind the survivor.

## 7. Encounter binding

`ENCOUNTER_DIAGNOSIS`: encounter required (API 422, DB CHECK). Unknown encounter 404. Cross-patient 409. Cross-org 404. Cancelled / entered-in-error encounter 409. Encounter is locked `FOR UPDATE` on create.

`PROBLEM_LIST_ITEM`: encounter not required.

## 8. Authorization

Every Condition route requires authentication, `X-Organization-Id`, optional facility, purpose, and a catalog permission:

- `clinical.condition.create`
- `clinical.condition.read`
- `clinical.condition.update`
- `clinical.condition.entered_in_error`

Unauthenticated 401. Registrar + valid purpose 403. Facility allow-list: in-scope 200, out-of-scope 403. Cross-org resource 404.

`clinical.diagnosis.create` is not in the catalog. PDP returns `deny_by_default`.

## 9. Purpose of use

Wave 1.5 catalog plus `TREATMENT`. Missing/invalid purpose 422. Purpose does not grant permission: registrar + `TREATMENT` or `EMERGENCY` still 403. Clinician + `EMERGENCY` with `clinical.condition.read` 200.

## 10. Immutability

Before `ENTERED_IN_ERROR`, clinical/verification status may change per the lifecycle. Identity, encounter, organization, category, code/system/display, and recorder cannot change (trigger + no API fields).

After `ENTERED_IN_ERROR`, the row is frozen at API, service, and database.

The trigger is not overly strict: clinical status remains updatable until voided.

## 11. Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not an authoritative lock (rate-limit / health only).

| Race | Result |
|---|---|
| Concurrent identical `RESOLVED` | `{200, 409}`, one row, one `CONDITION_STATUS_CHANGED` |
| Concurrent double `ENTERED_IN_ERROR` | `{200, 409}`, one void audit |
| Status vs `ENTERED_IN_ERROR` | One 200; other 200 or 409; valid terminal states only; one row |
| Concurrent create, same patient | Both succeed (no uniqueness by design) |
| Concurrent create after merge | Both bind survivor |

No last-writer-wins corruption. No duplicate void history.

## 12. Audit

Success: `CONDITION_CREATED`, `CONDITION_STATUS_CHANGED`, `CONDITION_ENTERED_IN_ERROR`. Metadata is category/status/purpose — not code display, NIK, or note body.

**P2 (inherited Wave 1):** `DENIED` rows share the request session and roll back with `ForbiddenError`. Not redesigned.

## 13. Provenance

Separate insert-only `clinical_provenances` (actor, org, facility, recorded_at, native authorship, clinician information source). `UPDATE`/`DELETE` revoked for `app_dml`. Not collapsed into audit.

## 14. Terminology

Stub only: `system` + `code` + optional `display`. No ICD/SNOMED server, ValueSet, or FHIR terminology API. Code fields are immutable after insert (trigger). Display is log-redacted.

## 15. API

| Method | Path |
|---|---|
| POST | `/api/v1/clinical/conditions` |
| GET | `/api/v1/clinical/conditions?patient_identity_id=` |
| GET | `/api/v1/clinical/conditions/{id}` |
| POST | `/api/v1/clinical/conditions/{id}/status` |
| POST | `/api/v1/clinical/conditions/{id}/entered-in-error` |
| DELETE | **405** |

Validation 422, authz 403, invisible 404, lifecycle 409. Generic handler returns `internal_error` without SQLAlchemy/PostgreSQL detail. Docker OpenAPI is not exposed (`expose_openapi=false`); unauthenticated POST Condition → 401.

## 16. Database security

Live grants on `conditions`: `app_dml` INSERT/SELECT/UPDATE only. `php_admin` retains DELETE for migrations. `readonly` SELECT. Reproduced from `scripts/grant_dev_privileges.sql` (`REVOKE DELETE, TRUNCATE ON TABLE conditions FROM app_dml`). Confirmed with `app_dml` connection, not only `php_admin`.

## 17. Docker runtime

Backend rebuilt `--no-deps` from this tree. Health live `alive`; ready `postgres/redis/object_storage ok`. EMR MinIO unchanged. `gsai-minio` not restarted. Ports unchanged.

## 18. Security / regression tests

| Check | Result |
|---|---|
| ruff check / format --check | PASS |
| mypy | PASS |
| pytest | **116 passed** (Wave 1.5, Wave 2A, Wave 2B.1, this gate) |

Hardening coverage includes random UUID 404, cross-org 404, facility 403, SQL identity/category/code mutation blocked, `app_dml` DELETE denied, merge non-rewrite, concurrent races.

## 19. Clinical boundary

Scan of `backend/app`: no Observation, Laboratory, Medication, Allergy, Consent, FHIR, AI, RAG, or CDS implementation. `OrganizationType.LABORATORY` remains org taxonomy. `clinical_governance` remains a Wave 0 placeholder. Forbidden tables absent from SQLAlchemy metadata and live PostgreSQL.

Condition is the only Wave 2B domain.

## 20. Findings

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| H1 | P1 | No-op / concurrent identical status updates returned 200 and duplicated `CONDITION_STATUS_CHANGED` | **Fixed** in service (409 `condition_status_unchanged`) |
| H2 | P2 | `DENIED` audit rows roll back with `ForbiddenError` | Remaining (Wave 1 session; not redesigned) |
| H3 | P2 | Historical `patient_identity_id` is not rewritten after MPI merge; survivor list does not include source-bound rows | Remaining (explicit non-rewrite; tested) |
| H4 | P2 | `conditions.provenance_id` has no FK (same pattern as notes) | Remaining |
| H5 | P2 | Before EIE, SQL may still change onset/abatement/`recorded_at`/`facility_id` | Remaining (trigger not overly strict; identity/code frozen) |
| H6 | P3 | Dev grants live in `grant_dev_privileges.sql`, not Alembic | Remaining (Wave 1/2A pattern) |

No P0. No open P1.

## 21. Remediation

Service-only: skip no-op status writes and skip their audit. Added regression tests for identical concurrent status, status vs EIE, concurrent create, merge non-rewrite, concurrent post-merge create, encounter boundaries, purpose/authz/IDOR/DELETE, `app_dml` DELETE. No `0007`. `0001`–`0005` untouched.

## 22. Remaining risks

Denial-audit durability requires a Wave 1 session/audit change. Merge does not backfill Condition identity. Neither is Wave 2B.2. Duplicate problem-list codes are allowed (no uniqueness constraint).

## 23. Final scorecard

| Area | Result |
|---|---|
| Repository / freeze integrity | PASS (`wave-2a-frozen` intact; no 2B.1 commit) |
| Identity binding | PASS |
| Encounter binding | PASS |
| Org/facility PDP | PASS |
| Purpose ≠ authorization | PASS |
| Immutability (API + DB) | PASS |
| Concurrency | PASS (after H1) |
| Audit / provenance | PASS WITH P2 (H2, H4) |
| Terminology stub bounded | PASS |
| IDOR / PII / DELETE | PASS |
| Docker / ports / MinIO | PASS |
| Clinical boundary | PASS |
| Quality gates | 116 passed |
| **Verdict** | **PASS WITH P2** |

WAVE 2B.1 HARDENING COMPLETE — WAVE 2B.2 NOT STARTED — CONDITION NOT FROZEN
