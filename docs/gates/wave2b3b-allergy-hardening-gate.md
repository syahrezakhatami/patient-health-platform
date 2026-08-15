# Wave 2B.3b — Allergy production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-15
**Frozen Wave 2B.3a:** `wave-2b3a-medication-frozen` / `abb6d7a238a139608d645c7e916e3182dd5ecaa9`
**Allergy Alembic:** `20260814_0011`
**Wave 2B.3c Consent:** NOT STARTED
**Allergy freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `abb6d7a238a139608d645c7e916e3182dd5ecaa9` |
| Tag | Annotated `wave-2b3a-medication-frozen` → same commit |
| Working tree | Dirty: Allergy implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0011` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011` |
| Migrations `0001`–`0010` | Untouched |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched (`gsai-minio` up ~2 weeks; Compose minio up ~40h) |

## B. Repository

Allergy-only scope. Implementation files remain domain, API, catalog, `0011`, grants, boundary-test table lists, and docs. Hardening added `test_wave2b3b_hardening.py`, the `reaction` log-redaction key, and this gate document.

Previous-wave SQL “absent table” lists already allow `allergies` while consent/FHIR remain forbidden. Authorization tests were not weakened.

No unrelated application functionality. No `.env`, keys, tokens, `.venv`, caches, or volume data in the tree.

## C. Migration

`20260814_0011` is additive. It creates `allergies`; extends `clinical_provenances.subject_type` with `ALLERGY`; seeds `clinical.allergy.*` permissions. `0001`–`0010` were not rewritten. No `0012`.

## D. Database integrity

Live `php_dev`: UUID PK; FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances` all `ON DELETE RESTRICT`. CHECKs for category, record status, clinical status, verification, criticality, severity, reaction pair, non-empty codes, version ≥ 1. History/DELETE trigger `trg_allergies_history_immutable`. `app_dml`: INSERT/SELECT/UPDATE only; DELETE and TRUNCATE denied. Orphan `provenance_id` count: 0. Null `provenance_id` count: 0. `provenance_id` is nullable (same Observation/Laboratory/Medication insert-first pattern) with a real FK.

## E. Lifecycle

Create is always record `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. No `COMPLETED`. No generic PUT. No-op amend and double EIE: 409, no duplicate success audit. Concurrent identical amend and concurrent EIE: one 200, one 409. Concurrent amend versus EIE: final `ENTERED_IN_ERROR`, one `ALLERGY_ENTERED_IN_ERROR` (amend audit 0 or 1 depending on winner). Redis is not used.

## F. Immutability

API has no generic PUT. Service transitions are explicit. Trigger freezes patient, encounter, org, facility, category, allergen code/display, recorded time, recorder, and provenance. Terminal EIE rows are fully frozen, including previously mutable clinical/verification/reaction/severity fields. Direct `app_dml` UPDATE of identity/allergen is blocked. SQL `AMENDED → ACTIVE` is rejected.

## G. Identity / MPI

Canonical FK `patient_identities.id`. No second person table. ACTIVE allowed. MERGED new writes bind survivor. RETIRED 409. Unknown/cross-org 404. Anonymous standalone 409; EMER encounter required. Historical rows not rewritten. MPI modules not modified.

## H. Encounter binding

Optional for ACTIVE. Same canonical patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` encounters 409 without mutating the encounter. Cross-org encounter 404. Wrong patient pair 409. Allergy does not change encounter status.

## I. Authorization

Permissions: `clinical.allergy.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read (create 403). Registrar: 403 even with `TREATMENT`. Unauthenticated 401. Unprovisioned JWT 403. Cross-org 404. Facility allow-list: in-scope 200, out-of-scope 403. `clinical.diagnosis.create` and `clinical.consent.create` remain deny-by-default. Purpose does not grant access.

## J. Purpose

`X-Purpose` required (422 missing/unknown). Normalized by the existing Wave 1.5 catalog plus `TREATMENT`. Recorded on success audit. Does not bypass PDP. `X-Purpose` is not a persisted Consent record.

## K. Audit

Events: `ALLERGY_CREATED`, `ALLERGY_AMENDED`, `ALLERGY_ENTERED_IN_ERROR`. Metadata is category/status/clinical_status/verification_status/version/purpose — not NIK, BPJS, allergen names, reaction details, severity, criticality, or secrets. Logging redacts `code_display`, `reaction`, reaction coded fields, `severity`, and `criticality`. Inherited Wave 1 DENIED-audit rollback remains P2 and was not redesigned.

## L. Provenance

Insert-only `clinical_provenances`. Subject type `ALLERGY`. Actor, organization, optional facility, `recorded_at`, authorship/source set. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance_id INSERT fails. Provenance DELETE restricted (insert-only trigger plus FK).

## M. DELETE protection

No DELETE routes. DELETE/PUT on `/allergies/{id}` return 405. Trigger raises on DELETE. Live `app_dml` has no DELETE or TRUNCATE privilege on `allergies`.

## N. Concurrency

All mutations `SELECT FOR UPDATE`. Redis is not a clinical lock. Executed live: concurrent amend, concurrent EIE, amend versus EIE.

## O. Security / IDOR

Cross-org 404 without SQLAlchemy or allergen/reaction names in the body. Unknown UUID 404. Unauthorized registrar 403 without `Penicillin` / `Anaphylaxis` leakage.

## P. Docker

`/api/v1/health/live` alive. `/api/v1/health/ready` postgres/redis/object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. MinIO not restarted. `gsai-minio` untouched. Backend image was not rebuilt in this hardening pass.

## Q. Tests

ruff check/format PASS. mypy PASS (105 app files). pytest **168 passed**. Wave 1.5 / 2A / Condition / Observation / Laboratory / Medication remain green. No tests skipped, weakened, or deleted.

## R. Clinical boundary

Allergy present. Consent, FHIR APIs/resources, AI, RAG, CDS absent. No `/api/v2/`, `/fhir/`, `/consents`. Medication remains frozen at `abb6d7a`.

## S. Findings

See scorecard.

## T. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; not redesigned |
| P2 | Historical `patient_identity_id` not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until Consent | Documented; matches Observation |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same Observation/Laboratory/Medication pattern |
| P3 | Duplicate allergy facts for the same allergen are allowed | Allowed in this slice |
| P3 | Docker backend image lags this working-tree change | Tests cover the working tree; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## U. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Allergy is **hardenable**
- Allergy should **remain unfrozen**
- Do not start Consent / FHIR / AI / RAG / CDS
- Do not commit, tag, or push in this pass
