# Wave 2B.5 — Procedure production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-15
**Frozen Wave 2B.4:** `wave-2b4-immunization-frozen` / `20bef7e7a7bc315f6898b508c1de1f237d00abcc`
**Procedure Alembic:** `20260814_0014`
**Procedure freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Procedure is a persisted performed/reported procedure fact. It is **not** a FHIR Procedure resource, order, care plan, scheduling object, CDS object, or workflow engine.

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `20bef7e7a7bc315f6898b508c1de1f237d00abcc` |
| Tag | Annotated `wave-2b4-immunization-frozen` → same commit |
| Working tree | Dirty: Procedure implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0014` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014` |
| Migrations `0001`–`0013` | Untouched |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched (`gsai-minio` up ~2 weeks; Compose minio up ~44h) |

## B. Repository

Procedure-only scope. Frozen Immunization/Consent/Allergy/Medication/Laboratory/Observation/Condition/Wave 1 PDP modules were not redesigned. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched. No production Procedure code changed in this hardening pass: live schema, lifecycle, identity, encounter, authorization, audit, provenance, and API already matched the approved Immunization/Consent contract.

No `.env`, keys, tokens, `.venv`, caches, logs, or volume data in the working tree.

## C. Migration

`20260814_0014` is additive. It creates `procedures`; extends `clinical_provenances.subject_type` with `PROCEDURE`; seeds `clinical.procedure.*` permissions. `0001`–`0013` were not rewritten. No `0015`.

## D. Database integrity

Live `php_dev`:

- UUID PK `procedures.id`
- FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances` — all `ON DELETE RESTRICT`
- CHECKs: `category` (`PERFORMED` \| `REPORTED`), `status` (`ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR`), coded pair non-empty, `version >= 1`
- Indexes: patient, encounter, org, recorded_at
- Trigger `trg_procedures_history_immutable` / `prevent_procedure_history_mutation()`
- `app_dml`: INSERT / SELECT / UPDATE only; DELETE and TRUNCATE denied
- Invalid category / status / version INSERT fails CHECK
- Orphan `provenance_id` count: 0
- Null `provenance_id` count: 0
- `provenance_id` column remains nullable (frozen convention); service always sets it

## E. Lifecycle

Create is always `ACTIVE`. `ACTIVE → AMENDED` and `AMENDED → AMENDED` only when occurrence or note actually changes. Version increments exactly once per successful amend. `ACTIVE|AMENDED → ENTERED_IN_ERROR` is terminal and does not increment version (Allergy/Immunization convention). Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, terminal → anything. `REVOKED` and `EXPIRED` are not persisted. No generic PUT. No PATCH. No DELETE. No `/revoke`. No generic `/status` lifecycle endpoint. No duplicate successful lifecycle audit on no-op or losing races.

## F. Immutability

Frozen after create: `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `category`, `code_system` / `code` / `code_display`, recorder, `recorded_at`, `provenance_id`. Amendable until EIE: `occurrence_at`, `note_text`, status → `AMENDED`, version. Terminal EIE freezes the complete row, including occurrence and note. Procedure has no route/site columns. Verified through API, service transitions, direct SQL UPDATE, `app_dml` UPDATE, and the trigger.

## G. Identity / MPI

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter follows the frozen same-patient check against the canonical identity and returns **409** (not a defect). RETIRED 409. Unknown / cross-org 404. Standalone anonymous 409. Anonymous + documentable `EMER` allowed. Anonymous + non-`EMER` encounter 409. Historical `patient_identity_id` is not rewritten after MPI merge.

## H. Encounter binding

Optional. Same patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` encounters 409 without mutating the encounter. Cross-org encounter 404. Wrong patient/encounter pair 409. Procedure never mutates encounter status.

## I. Authorization

Permissions: `clinical.procedure.create|read|update|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: all (HTTP-tested: PLATFORM_ADMIN create, amend, EIE). ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: none, including Registrar + `TREATMENT`. Unauthenticated 401. Unprovisioned JWT 403. Insufficient permission 403. Facility out-of-scope 403. Cross-org resource 404. Cross-org identity write 404. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default. Purpose does not grant access. Consent does not grant Procedure access. Authorization is permission-based, not role-name checks.

## J. Purpose

`X-Purpose` required, normalized (`treatment` → `TREATMENT`), and validated against the existing catalog. Missing / unknown = 422. Recorded on success audit. A valid purpose does **not** grant authorization.

## K. Audit / logging

Events: `PROCEDURE_CREATED`, `PROCEDURE_AMENDED`, `PROCEDURE_ENTERED_IN_ERROR`. Metadata is category / status / version / purpose — not procedure display, procedure code, note, NIK, BPJS, tokens, passwords, or secrets. Logging redacts `note`, `note_text`, `code_display`, `procedure_display`, `procedure_code`, and `procedure_note`. Inherited Wave 1 DENIED-audit rollback remains P2: a 403 on `clinical.procedure.create` still leaves 0 `DENIED` rows. Not redesigned.

## L. Provenance

Insert-only `clinical_provenances`. Subject type `PROCEDURE`. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance rejected. Referenced provenance cannot be deleted. No orphan rows. No null `provenance_id` in service-created rows.

## M. Concurrency — executed live

All mutations use PostgreSQL `SELECT FOR UPDATE` (`ClinicalRepository.get_procedure_for_update`). Redis is not a clinical lock (`db_app` integration fixture sets `redis=None`; amend/EIE service methods do not reference Redis). Live races:

| Race | Live result |
|---|---|
| Amend vs amend | one 200, one 409, one `PROCEDURE_AMENDED` |
| EIE vs EIE | one 200, one 409, one `PROCEDURE_ENTERED_IN_ERROR`; version unchanged |
| Amend vs EIE | one 200, one 409; final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1; version 1 or 2 |

## N. API boundary

`POST /api/v1/clinical/procedures`, `GET /api/v1/clinical/procedures?patient_identity_id=`, `GET /api/v1/clinical/procedures/{id}`, `POST .../amend`, `POST .../entered-in-error`. PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No `/fhir/`. No FHIR Procedure. No CarePlan, scheduling, inventory, or registry routes.

## O. Security / leakage

401 / 403 / 404 / 409 / 422 behave as specified. Cross-org GET is 404 without procedure code, display, note, or patient data. Registrar / IDENTITY_OFFICER denial is 403 without payload leakage. Unknown UUID 404 without SQLAlchemy / database details. Invalid provenance does not leak internal DB details.

## P. Runtime

`/api/v1/health/live` = 200. `/api/v1/health/ready` = 200 with postgres / redis / object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` untouched. Backend image was not rebuilt in this hardening pass. Integration tests execute the working-tree ASGI app against live Postgres.

## Q. Quality gates

`ruff check app tests` PASS. `ruff format --check app tests` PASS. `mypy app` PASS (105 app files). pytest **204 passed**. Procedure hardening file: **6 passed**. Frozen Condition / Observation / Laboratory / Medication / Allergy / Consent / Immunization plus prior hardening: **83 passed**. No tests skipped, weakened, or deleted. Repo-wide `ruff format --check` without paths still fails on frozen Alembic `0001`–`0013`; those files were not rewritten.

## R. Secret scan

No `.env`, credentials, private keys, GitHub tokens, production secrets, `.venv`, runtime volumes, logs, or cache artifacts in the working tree. `.gitignore` unchanged.

## S. Clinical boundary

Native `procedures` present. FHIR Procedure, CarePlan, AI, RAG, CDS, break-glass, and patient-portal tables remain absent. Procedure is not wired into other clinical getters. Immunization remains frozen at `20bef7e`.

## T. Findings

See scorecard. No P0/P1. Inherited P2/P3 were not redesigned. No new architectural decision was required.

## U. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; reconfirmed on Procedure 403; not redesigned |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until a later PDP wave | Documented; Consent is not a PDP for Procedure |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same Observation / Laboratory / Medication / Allergy / Consent / Immunization pattern |
| P3 | Duplicate procedure facts are allowed | Allowed in this slice |
| P3 | Performer / body site / reason / outcome deferred | Approved design |
| P3 | Test `rate_limit_per_minute` raised 1000 → 10000 | Test-only; production remains 120; suite volume exceeded the inherited test ceiling |
| P3 | Docker backend image lags this working-tree change | Tests cover the working tree; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## V. Hardening changes this pass

No production Procedure code change. Focused tests: concurrent amend vs amend, concurrent EIE vs EIE, concurrent amend vs EIE, terminal EIE row freeze (API + SQL including occurrence/note/status/version and all frozen identity fields), PATCH/PUT/DELETE 405, registrar / IDENTITY_OFFICER read 403 without leakage, inherited DENIED-audit count, MERGED + encounter binding, RETIRED 409, cross-org identity 404, purpose normalization, PLATFORM_ADMIN create/amend/EIE, REPORTED category, `occurrence_at` amendment, anonymous non-EMER 409, cancelled/EIE encounter 409 without mutating the encounter, CHECK constraints, `SELECT FOR UPDATE` source assertion.

Test fixture only: `rate_limit_per_minute` 1000 → 10000 in unit and integration settings so the larger ASGI suite does not collide with the inherited Redis-backed limiter. Production rate limit remains 120.

## W. Exact files changed this hardening pass

- `backend/tests/integration/test_wave2b5_hardening.py` (added)
- `backend/tests/integration/test_wave2b5_procedure.py` (shared payload helpers)
- `backend/tests/conftest.py` (test rate-limit ceiling)
- `backend/tests/integration/conftest.py` (test rate-limit ceiling)
- `docs/gates/wave2b5-procedure-hardening-gate.md` (this file)

## X. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Procedure is **hardenable** and **hardening is complete**
- Procedure should **remain unfrozen**
- Do not start CarePlan / FHIR / AI / RAG / CDS / Consent-as-PDP / scheduling / inventory / registry
- Do not commit, tag, or push in this pass
