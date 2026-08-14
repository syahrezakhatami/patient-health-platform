# Wave 2B.2b — Laboratory production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-14
**Frozen Wave 2B.2a:** `wave-2b2a-observation-frozen` / `32500d1492994154c58c6eb65cade6cf42486d4f`
**Laboratory Alembic:** `20260814_0009`
**Wave 2B.3:** NOT STARTED
**Laboratory freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `32500d1492994154c58c6eb65cade6cf42486d4f` |
| Tag | Annotated `wave-2b2a-observation-frozen` → same commit |
| Working tree | Dirty: Laboratory implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0009` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009` |
| Migrations `0001`–`0008` | Untouched |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched (up ~24h) |

## B. Repository

Laboratory-only scope. Modified files are domain, API, catalog, `0009`, grants, boundary-test table lists, and docs. Hardening additionally touched `app/core/logging.py` (reference-range keys) and added `test_wave2b2b_hardening.py`.

Previous-wave SQL “absent table” lists were updated so `laboratory_*` is allowed while medication/allergy/FHIR remain forbidden. That is required for the suite to stay green; authorization tests were not weakened.

No unrelated application functionality. No `.env`, keys, tokens, `.venv`, caches, or volume data in the tree. `.gitignore` already covers those classes. `.env.example` remains synthetic placeholders.

## C. Migration

`20260814_0009` is additive. It creates `laboratory_orders`, `laboratory_specimens`, `laboratory_results`; extends `clinical_provenances.subject_type`; seeds `clinical.laboratory.*` permissions. `0001`–`0008` were not rewritten. No `0010`.

## D. Database integrity

Live `php_dev`: UUID PKs; FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances`, and parent lab tables all `ON DELETE RESTRICT`. CHECKs for status, specimen type, value type, value shape, interpretation, reference range, non-empty codes, version ≥ 1. History/DELETE triggers on all three tables. `app_dml`: INSERT/SELECT/UPDATE only. Orphan `provenance_id` count: 0/0/0. `provenance_id` is nullable (same Observation/Condition insert-first pattern) with a real FK.

## E. Order lifecycle

Create `REGISTERED`. First specimen → `IN_PROGRESS` (one `LAB_ORDER_IN_PROGRESS`). Cancel only from `REGISTERED`. `IN_PROGRESS` → `ENTERED_IN_ERROR` only. Terminal states immutable. No `COMPLETED`. No-op cancel / cancel after `IN_PROGRESS` / EIE of `CANCELLED` → 409, no duplicate audit. Concurrent cancel vs first specimen: one 200, one 409; final state is either `CANCELLED` with zero specimens or `IN_PROGRESS` with one specimen. Concurrent double cancel: 200 + 409, one `LAB_ORDER_CANCELLED`. Redis is not used.

## F. Specimen lifecycle

Create `COLLECTED`; inherits patient/org/encounter from the order. Open order required. `COLLECTED → REJECTED|ENTERED_IN_ERROR`. No-op reject 409. Concurrent reject vs EIE: one 200, one 409; final `REJECTED` or `ENTERED_IN_ERROR`. Cross-org 404. HTTP DELETE 405. `app_dml` DELETE blocked. Historical `patient_identity_id` SQL-immutable.

## G. Result lifecycle

Create `FINAL`. No draft. Amend `FINAL|AMENDED`; no-op 409; value type immutable (422). `FINAL|AMENDED → ENTERED_IN_ERROR`. Concurrent identical amend and double EIE: 200 + 409, one matching audit. Concurrent amend vs EIE: final `ENTERED_IN_ERROR`. Exactly one value representation via CHECK. Terminology stub only.

## H. Identity / MPI

Canonical FK `patient_identities.id`. No second person table. ACTIVE allowed. MERGED new writes bind survivor. RETIRED 409. Unknown/cross-org 404. Anonymous standalone 409; EMER encounter required. Historical rows not rewritten. MPI modules not modified.

## I. Encounter binding

Optional on the order. Same canonical patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` encounters 409 without mutating the encounter. Cross-org encounter 404. Specimen/result inherit encounter from the order. Laboratory does not change encounter status.

## J. Authorization

Permissions: `clinical.laboratory.{order,specimen,result}.{create,read,update,entered_in_error}`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read (create 403). Registrar: 403 even with `TREATMENT`. Unauthenticated 401. Unprovisioned JWT 403. Cross-org 404. Facility allow-list: in-scope 200, out-of-scope 403. `clinical.laboratory.create`, `clinical.medication.create`, `clinical.diagnosis.create` remain deny-by-default. Purpose does not grant access. Observation/Condition permissions are separate catalog entries, not implied by Laboratory.

## K. Purpose

`X-Purpose` required (422 missing/unknown). Normalized by the existing Wave 1.5 catalog plus `TREATMENT`. Recorded on success audit. Does not bypass PDP.

## L. Audit

Events: `LAB_ORDER_CREATED`, `LAB_ORDER_IN_PROGRESS`, `LAB_ORDER_CANCELLED`, `LAB_ORDER_ENTERED_IN_ERROR`, `LAB_SPECIMEN_COLLECTED`, `LAB_SPECIMEN_REJECTED`, `LAB_SPECIMEN_ENTERED_IN_ERROR`, `LAB_RESULT_CREATED`, `LAB_RESULT_AMENDED`, `LAB_RESULT_ENTERED_IN_ERROR`. Metadata is status/type/purpose/version — not NIK, BPJS, measured values, or secrets. Logging now redacts value keys and `reference_range_low` / `reference_range_high`. Inherited Wave 1 DENIED-audit rollback remains P2 and was not redesigned.

## M. Provenance

Insert-only `clinical_provenances`. Subject types `LABORATORY_ORDER`, `LABORATORY_SPECIMEN`, `LABORATORY_RESULT`. Actor, organization, optional facility, `recorded_at`, authorship/source set. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance_id INSERT fails. Provenance DELETE restricted.

## N. Immutability

API has no generic PUT. Service transitions are explicit. Triggers freeze patient, encounter, org, facility, codes, ordered/collected/recorded time, recorder, provenance, result value type. Terminal rows are fully frozen. Mutable until terminal: order/specimen/result status, result values/range/interpretation/`effective_at`, versions.

## O. DELETE protection

No DELETE routes. DELETE/PUT on existing resource paths return 405. Triggers raise on DELETE. Live `app_dml` has no DELETE privilege on the three tables.

## P. Concurrency

All mutations `SELECT FOR UPDATE`. Redis is not a clinical lock. Covered: order cancel vs first specimen, double cancel, double order EIE, specimen reject vs EIE, result amend, result EIE, amend vs EIE.

## Q. Security / IDOR

Cross-org 404 without SQLAlchemy or result codes in the body. Unknown UUID 404. Malformed UUID 422. Wrong patient/encounter 409. Unauthorized registrar 403 without `mmol/L` / LOINC leakage.

## R. Docker

`/api/v1/health/live` alive. `/api/v1/health/ready` postgres/redis/object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. MinIO not restarted. Backend image was not rebuilt in this hardening pass (logging redaction is covered by unit tests on the working tree).

## S. Tests

ruff check/format PASS. mypy PASS (105 app files). pytest **144 passed**. Wave 1.5 / 2A / Condition / Observation remain green. No tests skipped, weakened, or deleted.

## T. Clinical boundary

Laboratory present. Medication, allergy, consent, FHIR APIs/resources, AI, RAG, CDS absent. No `/api/v2/`, `/fhir/`, `/medications`, `/allergies`, `/consents`. `OrganizationType.LABORATORY` remains org taxonomy only.

## U. Findings

See scorecard.

## V. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; not redesigned |
| P2 | Historical `patient_identity_id` not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until Consent | Documented; matches Observation |
| P2 | Result amend/EIE does not re-check parent order/specimen terminal state | Documented; independent resource lifecycles |
| P2 | Reference-range log keys were incomplete | Closed: allowlist extended |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same Observation pattern |
| P3 | Duplicate orders/specimens/results allowed | Allowed in this slice |
| P3 | Docker backend image lags this working-tree logging change | Unit-tested; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## W. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Laboratory is **hardenable**
- Laboratory should **remain unfrozen**
- Do not start Wave 2B.3 / Medication / Allergy / Consent / FHIR / AI / RAG / CDS
- Do not commit, tag, or push in this pass
