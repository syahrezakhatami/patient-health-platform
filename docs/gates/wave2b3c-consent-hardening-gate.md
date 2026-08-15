# Wave 2B.3c — Consent production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-15
**Frozen Wave 2B.3b:** `wave-2b3b-allergy-frozen` / `21b20b998a7c3ccad41a1273ac4c85101b94144c`
**Consent Alembic:** `20260814_0012`
**Wave 2B.3d Immunization:** NOT STARTED
**Consent freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Consent is a persisted permit/refuse fact. It is **not** a PDP, FHIR Consent resource, or authorization grant.

Companion canvas: [wave2b3c-consent-hardening-gate.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/wave2b3c-consent-hardening-gate.canvas.tsx)

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `21b20b998a7c3ccad41a1273ac4c85101b94144c` |
| Tag | Annotated `wave-2b3b-allergy-frozen` → same commit |
| Working tree | Dirty: Consent implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0012` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012` |
| Migrations `0001`–`0011` | Untouched |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched (`gsai-minio` up ~2 weeks; Compose minio up ~41h) |

## B. Repository

Consent-only scope. Frozen Allergy/Medication/Laboratory/Observation/Condition/Wave 1 PDP modules were not redesigned. Previous-wave tests only dropped `consents` from “absent table” lists and moved deny-by-default stubs from `clinical.consent.create` to `clinical.immunization.create` because Consent is now catalogued. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched.

No `.env`, keys, tokens, `.venv`, caches, logs, or volume data in the working tree.

## C. Migration

`20260814_0012` is additive. It creates `consents`; extends `clinical_provenances.subject_type` with `CONSENT`; seeds `clinical.consent.*` permissions. `0001`–`0011` were not rewritten. No `0013`.

## D. Database integrity

Live `php_dev`:

- UUID PK `consents.id`
- FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances` — all `ON DELETE RESTRICT`
- CHECKs: `category`, `scope`, `decision`, `source`, `status`, `version >= 1`, period order, `revoked_at` consistency, coded pair
- Indexes: patient, encounter, org, facility, status, recorded_at, `(patient, org, status)`, `period_end`
- Trigger `trg_consents_history_immutable` / `prevent_consent_history_mutation()`
- `app_dml`: INSERT / SELECT / UPDATE only; DELETE and TRUNCATE denied
- Orphan `provenance_id` count: 0
- Null `provenance_id` count: 0
- Invalid provenance INSERT fails; referenced provenance cannot be deleted

## E. Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` only when period or note actually changes. `ACTIVE|AMENDED → REVOKED` sets `revoked_at` and increments version. `ACTIVE|AMENDED → ENTERED_IN_ERROR` is terminal and does not increment version (Allergy convention). Both `REVOKED` and `ENTERED_IN_ERROR` are terminal. Rejected: no-op amend, double revoke, double EIE, `AMENDED → ACTIVE`, terminal → anything. `EXPIRED` is not persisted. `is_effective` is computed. No duplicate successful lifecycle audit on no-op or losing races.

## F. Immutability

Frozen after create: `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `category`, `scope`, `decision`, `code` / `code_display`, `source`, recorder, `recorded_at`, `provenance_id`. Amendable until terminal: period, note, status → `AMENDED`, version. Terminal EIE freezes the complete row, including period and note. Verified through API, service transitions, direct SQL UPDATE, `app_dml` UPDATE, and the trigger.

## G. Identity / MPI

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter follows the frozen same-patient check against the canonical identity and returns **409** (not a defect). RETIRED 409. Unknown / cross-org 404. ANONYMOUS 409 including with EMER. Historical `patient_identity_id` is not rewritten after MPI merge.

## H. Encounter binding

Optional. Same patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` encounters 409 without mutating the encounter. Cross-org encounter 404. Wrong patient/encounter pair 409. Consent never mutates encounter status.

## I. Authorization

Permissions: `clinical.consent.create|read|update|revoke|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: all. ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: none, including Registrar + `TREATMENT`. Unauthenticated 401. Unprovisioned JWT 403. Insufficient permission 403. Facility out-of-scope 403. Cross-org resource 404. `clinical.diagnosis.create` and `clinical.immunization.create` remain deny-by-default (not in catalog). Purpose does not grant access.

## J. Purpose

`X-Purpose` required, normalized, and validated against the existing catalog. Missing / unknown = 422. Recorded on success audit. A valid purpose does **not** grant authorization. `X-Purpose` is not the Consent decision.

## K. Audit / logging

Events: `CONSENT_CREATED`, `CONSENT_AMENDED`, `CONSENT_REVOKED`, `CONSENT_ENTERED_IN_ERROR`. Metadata is category / scope / decision / status / version / purpose — not note text, code display, NIK, BPJS, tokens, passwords, or secrets. Logging redacts `note`, `note_text`, `consent_note`, and `code_display`. Inherited Wave 1 DENIED-audit rollback remains P2: a 403 on `clinical.consent.create` still leaves 0 `DENIED` rows. Not redesigned.

## L. Provenance

Insert-only `clinical_provenances`. Subject type `CONSENT`. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance rejected. Referenced provenance cannot be deleted. No orphan rows.

## M. Concurrency — executed live

All mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a clinical lock. Live races:

| Race | Live result |
|---|---|
| Amend vs amend | one 200, one 409, one `CONSENT_AMENDED` |
| Revoke vs revoke | one 200, one 409, one `CONSENT_REVOKED` |
| EIE vs EIE | one 200, one 409, one `CONSENT_ENTERED_IN_ERROR` |
| Amend vs revoke | one 200, one 409; final `REVOKED` |
| Amend vs EIE | one 200, one 409; final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1 |
| Revoke vs EIE | one terminal winner; competing mutation 409 |

## N. API boundary

`POST /api/v1/clinical/consents`, `GET /api/v1/clinical/consents?patient_identity_id=`, `GET /api/v1/clinical/consents/{id}`, `POST .../amend`, `POST .../revoke`, `POST .../entered-in-error`. PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No FHIR Consent. No Consent-as-PDP behavior.

## O. Security / leakage

401 / 403 / 404 / 409 / 422 behave as specified. Cross-org GET is 404 without consent scope, decision, note, code display, or patient data. Registrar / IDENTITY_OFFICER denial is 403 without payload leakage. Unknown UUID 404 without SQLAlchemy / database details. Invalid provenance does not leak internal DB details.

## P. Runtime

`/api/v1/health/live` = 200. `/api/v1/health/ready` = 200 with postgres / redis / object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` untouched. Backend image was not rebuilt in this hardening pass.

## Q. Quality gates

ruff check / ruff format --check PASS. mypy PASS (105 app files). pytest **180 passed**. Wave 1.5 / 2A / Condition / Observation / Laboratory / Medication / Allergy remain green. No tests skipped, weakened, or deleted.

## R. Secret scan

No `.env`, credentials, private keys, GitHub tokens, production secrets, `.venv`, runtime volumes, logs, or cache artifacts in the working tree.

## S. Clinical boundary

Native `consents` present. FHIR Consent, Immunization, Procedure, CarePlan, AI, RAG, CDS, break-glass, and patient-portal tables remain absent. Consent is not wired into other clinical getters. Allergy remains frozen at `21b20b9`.

## T. Findings

See scorecard. No P0/P1. Inherited P2/P3 were not redesigned.

## U. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; reconfirmed on Consent 403; not redesigned |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until a later PDP wave | Documented; Consent is not a PDP |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same Observation / Laboratory / Medication / Allergy pattern |
| P3 | Duplicate ACTIVE consent facts are allowed | Allowed in this slice |
| P3 | Docker backend image lags this working-tree change | Tests cover the working tree; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## V. Hardening changes this pass

Minimum production change: add `note` and `consent_note` to log redaction. Focused tests: concurrent amend vs EIE, terminal EIE row freeze (API + SQL), PATCH 405, registrar / IDENTITY_OFFICER read 403 without leakage, inherited DENIED-audit count, MERGED + encounter binding.

## W. Exact files changed

Working tree (implementation + hardening, uncommitted):

- `backend/alembic/env.py`
- `backend/alembic/versions/20260814_0012_wave2b3c_consents.py`
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
- `backend/tests/integration/test_wave15_hardening.py`
- `backend/tests/integration/test_wave2a_clinical.py`
- `backend/tests/integration/test_wave2b1_condition.py`
- `backend/tests/integration/test_wave2b2a_observation.py`
- `backend/tests/integration/test_wave2b2b_laboratory.py`
- `backend/tests/integration/test_wave2b3a_medication.py`
- `backend/tests/integration/test_wave2b3b_allergy.py`
- `backend/tests/integration/test_wave2b3c_consent.py`
- `backend/tests/integration/test_wave2b3c_hardening.py`
- `backend/tests/unit/test_wave1_boundaries.py`
- `backend/tests/unit/test_wave2b2b_laboratory_domain.py`
- `backend/tests/unit/test_wave2b3a_medication_domain.py`
- `backend/tests/unit/test_wave2b3b_allergy_domain.py`
- `backend/tests/unit/test_wave2b3c_consent_domain.py`
- `docs/architecture/modular-monolith.md`
- `docs/clinical/wave2b3c-consent.md`
- `docs/development/migrations.md`
- `docs/gates/wave2b3c-consent-implementation-gate.md`
- `docs/gates/wave2b3c-consent-hardening-gate.md`

## X. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Consent is **hardenable**
- Consent should **remain unfrozen**
- Do not start Immunization / Procedure / CarePlan / FHIR / AI / RAG / CDS / Consent-as-PDP
- Do not commit, tag, or push in this pass
