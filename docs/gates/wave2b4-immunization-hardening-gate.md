# Wave 2B.4 — Immunization production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-15
**Frozen Wave 2B.3c:** `wave-2b3c-consent-frozen` / `0258a20e5e49f2978fb16091603b5942c745ecda`
**Immunization Alembic:** `20260814_0013`
**Immunization freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Immunization is a persisted administered/reported vaccination fact. It is **not** a FHIR Immunization resource, schedule, forecast, inventory, registry, or CDS engine.

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `0258a20e5e49f2978fb16091603b5942c745ecda` |
| Tag | Annotated `wave-2b3c-consent-frozen` → same commit |
| Working tree | Dirty: Immunization implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0013` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013` |
| Migrations `0001`–`0012` | Untouched |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched (`gsai-minio` up ~2 weeks; Compose minio up ~44h) |

## B. Repository

Immunization-only scope. Frozen Consent/Allergy/Medication/Laboratory/Observation/Condition/Wave 1 PDP modules were not redesigned. Previous-wave tests only registered Immunization in metadata and moved deny-by-default stubs from `clinical.immunization.create` to `clinical.procedure.create` because Immunization is now catalogued. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched.

No `.env`, keys, tokens, `.venv`, caches, logs, or volume data in the working tree.

## C. Migration

`20260814_0013` is additive. It creates `immunizations`; extends `clinical_provenances.subject_type` with `IMMUNIZATION`; seeds `clinical.immunization.*` permissions. `0001`–`0012` were not rewritten. No `0014`.

## D. Database integrity

Live `php_dev`:

- UUID PK `immunizations.id`
- FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances` — all `ON DELETE RESTRICT`
- CHECKs: `category` (`ADMINISTERED` \| `REPORTED`), `status` (`ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR`), `route`, `site`, coded pair non-empty, `version >= 1`
- Indexes: patient, encounter, org, recorded_at
- Trigger `trg_immunizations_history_immutable` / `prevent_immunization_history_mutation()`
- `app_dml`: INSERT / SELECT / UPDATE only; DELETE and TRUNCATE denied
- Orphan `provenance_id` count: 0
- Null `provenance_id` count: 0
- Invalid provenance INSERT fails; referenced provenance cannot be deleted
- `provenance_id` column remains nullable (frozen convention); service always sets it

## E. Lifecycle

Create is always `ACTIVE`. `ACTIVE → AMENDED` and `AMENDED → AMENDED` only when occurrence, route, site, or note actually changes. Version increments exactly once per successful amend. `ACTIVE|AMENDED → ENTERED_IN_ERROR` is terminal and does not increment version (Allergy convention). Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, terminal → anything. `REVOKED` and `EXPIRED` are not persisted. No generic PUT. No DELETE. No duplicate successful lifecycle audit on no-op or losing races.

## F. Immutability

Frozen after create: `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `category`, vaccine `code_system` / `code` / `code_display`, recorder, `recorded_at`, `provenance_id`. Amendable until EIE: `occurrence_at`, `route`, `site`, `note_text`, status → `AMENDED`, version. Terminal EIE freezes the complete row, including occurrence, route, site, and note. Verified through API, service transitions, direct SQL UPDATE, `app_dml` UPDATE, and the trigger.

## G. Identity / MPI

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter follows the frozen same-patient check against the canonical identity and returns **409** (not a defect). RETIRED 409. Unknown / cross-org 404. Standalone anonymous 409. Anonymous + documentable `EMER` allowed. Anonymous + non-`EMER` encounter 409. Historical `patient_identity_id` is not rewritten after MPI merge.

## H. Encounter binding

Optional. Same patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` encounters 409 without mutating the encounter. Cross-org encounter 404. Wrong patient/encounter pair 409. Immunization never mutates encounter status.

## I. Authorization

Permissions: `clinical.immunization.create|read|update|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: all. ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: none, including Registrar + `TREATMENT`. Unauthenticated 401. Unprovisioned JWT 403. Insufficient permission 403. Facility out-of-scope 403. Cross-org resource 404. Cross-org identity write 404. `clinical.diagnosis.create` and `clinical.procedure.create` remain deny-by-default. Purpose does not grant access. Consent does not grant Immunization access.

## J. Purpose

`X-Purpose` required, normalized (`treatment` → `TREATMENT`), and validated against the existing catalog. Missing / unknown = 422. Recorded on success audit. A valid purpose does **not** grant authorization.

## K. Audit / logging

Events: `IMMUNIZATION_CREATED`, `IMMUNIZATION_AMENDED`, `IMMUNIZATION_ENTERED_IN_ERROR`. Metadata is category / status / version / purpose — not vaccine display, vaccine code, note, NIK, BPJS, tokens, passwords, or secrets. Logging redacts `note`, `note_text`, `code_display`, `vaccine_display`, `vaccine_code`, and `immunization_note`. `route` and `site` are not written to audit metadata; they are not in the generic redaction key set because those names collide with unrelated fields. Inherited Wave 1 DENIED-audit rollback remains P2: a 403 on `clinical.immunization.create` still leaves 0 `DENIED` rows. Not redesigned.

## L. Provenance

Insert-only `clinical_provenances`. Subject type `IMMUNIZATION`. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance rejected. Referenced provenance cannot be deleted. No orphan rows. No null `provenance_id` in service-created rows.

## M. Concurrency — executed live

All mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a clinical lock (`db_app` integration fixture sets `redis=None`). Live races:

| Race | Live result |
|---|---|
| Amend vs amend | one 200, one 409, one `IMMUNIZATION_AMENDED` |
| EIE vs EIE | one 200, one 409, one `IMMUNIZATION_ENTERED_IN_ERROR` |
| Amend vs EIE | one 200, one 409; final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1; version 1 or 2 |

## N. API boundary

`POST /api/v1/clinical/immunizations`, `GET /api/v1/clinical/immunizations?patient_identity_id=`, `GET /api/v1/clinical/immunizations/{id}`, `POST .../amend`, `POST .../entered-in-error`. PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No FHIR Immunization. No scheduling, forecasting, inventory, or registry routes.

## O. Security / leakage

401 / 403 / 404 / 409 / 422 behave as specified. Cross-org GET is 404 without vaccine code, display, note, or patient data. Registrar / IDENTITY_OFFICER denial is 403 without payload leakage. Unknown UUID 404 without SQLAlchemy / database details. Invalid provenance does not leak internal DB details.

## P. Runtime

`/api/v1/health/live` = 200. `/api/v1/health/ready` = 200 with postgres / redis / object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` untouched. Backend image was not rebuilt in this hardening pass. Integration tests execute the working-tree ASGI app against live Postgres.

## Q. Quality gates

ruff check / ruff format --check PASS. mypy PASS (105 app files). pytest **191 passed**. Wave 1.5 / 2A / Condition / Observation / Laboratory / Medication / Allergy / Consent remain green. No tests skipped, weakened, or deleted.

## R. Secret scan

No `.env`, credentials, private keys, GitHub tokens, production secrets, `.venv`, runtime volumes, logs, or cache artifacts in the working tree. `.gitignore` unchanged.

## S. Clinical boundary

Native `immunizations` present. FHIR Immunization, Procedure, CarePlan, AI, RAG, CDS, break-glass, and patient-portal tables remain absent. Immunization is not wired into other clinical getters. Consent remains frozen at `0258a20`.

## T. Findings

See scorecard. No P0/P1. Inherited P2/P3 were not redesigned.

## U. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; reconfirmed on Immunization 403; not redesigned |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until a later PDP wave | Documented; Consent is not a PDP for Immunization |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same Observation / Laboratory / Medication / Allergy / Consent pattern |
| P3 | Duplicate immunization facts are allowed | Allowed in this slice |
| P3 | `route` / `site` are not generic log-redaction keys | Not written to audit metadata; names collide with unrelated fields |
| P3 | Docker backend image lags this working-tree change | Tests cover the working tree; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## V. Hardening changes this pass

Minimum production change: add `vaccine_code` to log redaction. Focused tests: concurrent amend vs EIE, terminal EIE row freeze (API + SQL including occurrence/route/site/note), PATCH/PUT/DELETE 405, registrar / IDENTITY_OFFICER read 403 without leakage, inherited DENIED-audit count, MERGED + encounter binding, cross-org identity 404, purpose normalization, platform-admin create, anonymous non-EMER 409, ACTIVE → EIE without version bump.

## W. Exact files changed

Working tree (implementation + hardening, uncommitted):

- `backend/alembic/env.py`
- `backend/alembic/versions/20260814_0013_wave2b4_immunizations.py`
- `backend/app/api/v1/clinical.py`
- `backend/app/api/v1/schemas.py`
- `backend/app/core/logging.py`
- `backend/app/modules/authorization/domain/catalog.py`
- `backend/app/modules/clinical/__init__.py`
- `backend/app/modules/clinical/application/services.py`
- `backend/app/modules/clinical/domain/enums.py`
- `backend/app/modules/clinical/domain/lifecycle.py`
- `backend/app/modules/clinical/infrastructure/models.py`
- `backend/app/modules/clinical/infrastructure/repositories.py`
- `backend/scripts/grant_dev_privileges.sql`
- `backend/tests/integration/test_wave2b4_immunization.py`
- `backend/tests/integration/test_wave2b4_hardening.py`
- `backend/tests/unit/test_wave1_boundaries.py`
- `backend/tests/unit/test_wave2b2b_laboratory_domain.py`
- `backend/tests/unit/test_wave2b3a_medication_domain.py`
- `backend/tests/unit/test_wave2b3b_allergy_domain.py`
- `backend/tests/unit/test_wave2b4_immunization_domain.py`
- `docs/architecture/modular-monolith.md`
- `docs/clinical/wave2b4-immunization.md`
- `docs/development/migrations.md`
- `docs/gates/wave2b4-immunization-implementation-gate.md`
- `docs/gates/wave2b4-immunization-hardening-gate.md`

## X. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Immunization is **hardenable**
- Immunization should **remain unfrozen**
- Do not start Procedure / CarePlan / FHIR / AI / RAG / CDS / Consent-as-PDP
- Do not commit, tag, or push in this pass
