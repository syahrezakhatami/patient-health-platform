# Wave 2B.7 — Adverse Event production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-16
**Frozen Wave 2B.6:** `wave-2b6-medical-device-frozen` / `fdcd24b19d9797034d89b6928c37dc6c47ffe863`
**Adverse Event Alembic:** `20260814_0016`
**Adverse Event freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Adverse Event is a persisted documented coded adverse-event fact. It is **not** a FHIR AdverseEvent resource, pharmacovigilance platform, incident-management system, Patient History aggregate, Vital Signs table, CarePlan, Diagnosis, or CDS object.

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `fdcd24b19d9797034d89b6928c37dc6c47ffe863` |
| Tag | Annotated `wave-2b6-medical-device-frozen` → same commit |
| Working tree | Dirty: Adverse Event implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0016` (single head) |
| Chain | `0001 → … → 0015 → 0016` |
| Migrations `0001`–`0015` | Untouched |
| Migration `0016` | Untouched this pass |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched |

## B. Repository

Adverse-Event-only scope. Frozen Medical Device / Procedure / Immunization / Consent / Allergy / Medication / Laboratory / Observation / Condition / Wave 1 PDP modules were not redesigned. `Wave1PolicyPDP` is untouched. No production Adverse Event code changed in this hardening pass: live schema, lifecycle, identity, encounter, related-fact invariant, authorization, audit, provenance, and API already matched the approved design contract.

No `.env`, keys, tokens, `.venv`, caches, logs, or volume data in the working tree.

## C. Severity decision

Approved design is **not ambiguous**.

Source: [docs/clinical/wave2b7-adverse-event-domain-approval.md](../clinical/wave2b7-adverse-event-domain-approval.md) sections M and N.

- Section M (immutable after create) lists patient, encounter, org, facility, category, code/display, related FKs, recorder, recorded_at, provenance. **`severity` is not in that list.**
- Section N (amendable until EIE) lists `occurrence_at`, **`severity`**, `note_text`, status → `AMENDED`, version.
- Explicit sentence: “Severity is amendable because seriousness may be corrected after initial documentation (same class of clinical correction as Allergy severity).”
- Closed-decision table row 9: amendable fields = `occurrence_at`, `severity`, `note_text`, status, version.

The implementation-prompt immutability list that included `severity` is therefore **not** the approved contract. Implementation keeps severity amendable. Hardening added a dedicated test: API MILD → MODERATE → SEVERE with version +1 per amend; extra immutable fields on amend do not rewrite identity/code/category/related FKs; direct SQL may change severity until EIE; EIE freezes severity; `AMENDED → ACTIVE` is rejected.

The DB trigger does **not** treat `NEW.severity` as a historical fact. Category and related FKs are frozen by the trigger.

## D. Migration

`20260814_0016` is additive. It creates `adverse_events`; extends `clinical_provenances.subject_type` with `ADVERSE_EVENT`; seeds `clinical.adverse_event.*` permissions. `0001`–`0015` were not rewritten. `0016` was not rewritten this pass.

## E. Database integrity

Live `php_dev`:

- UUID PK `adverse_events.id`
- FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `medications`, `medical_devices`, `procedures`, `clinical_provenances` — all `ON DELETE RESTRICT`
- CHECKs: category `DOCUMENTED` \| `REPORTED`; severity `MILD` \| `MODERATE` \| `SEVERE`; status `ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR`; related-fact at most one; version ≥ 1
- Trigger `trg_adverse_events_history_immutable` / `prevent_adverse_event_history_mutation()`
- DELETE denied by trigger
- TRUNCATE denied for `app_dml`
- `app_dml`: INSERT / SELECT / UPDATE; DELETE and TRUNCATE denied
- No causality / outcome / LIFE_THREATENING / seriousness columns
- No `fhir_adverse_events`
- Orphan / null `provenance_id` count on service-created rows: 0

## F. Related-fact invariant

Zero or exactly one of `medication_id` / `medical_device_id` / `procedure_id`. API and SQL CHECK reject every two-FK combination. Related FKs are immutable after create. Adverse Event create does not change related Medication / Medical Device / Procedure status or version. Target-table DELETE remains independently blocked by frozen-domain DELETE triggers; FK `ON DELETE RESTRICT` is also present.

## G. Lifecycle

Create is always `ACTIVE` v1. `ACTIVE → AMENDED` and `AMENDED → AMENDED` when severity, occurrence, or note actually changes. Version +1 per successful amend. `ACTIVE|AMENDED → ENTERED_IN_ERROR` is terminal and does not increment version. Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, terminal → anything. No PUT / PATCH / DELETE. No `/revoke` / `/stop`.

## H. Immutability

Frozen after create: patient, encounter, org, facility, category, code/display, related FKs, recorder, recorded_at, provenance. Amendable until EIE: severity, occurrence, note, status → `AMENDED`, version. Terminal EIE freezes the complete row, including severity. Verified through API, service, direct SQL, `app_dml`, and the trigger. Encounter status is unchanged after create, amend, and EIE.

## I. Identity / MPI

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter returns **409**. RETIRED 409. Unknown / cross-org 404. Standalone anonymous 409. Anonymous + documentable `EMER` allowed. Anonymous + non-`EMER` 409. Historical `patient_identity_id` is not rewritten after MPI merge. MPI was not redesigned.

## J. Encounter

Optional. Same patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` 409 without mutating the encounter. Cross-org 404. Wrong pair 409.

## K. Authorization

Permissions: `clinical.adverse_event.create|read|update|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: all (HTTP-tested: PLATFORM_ADMIN create, amend, EIE). ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: none, including Registrar + `TREATMENT` after a PERMIT consent. Unauthenticated 401. Unprovisioned JWT 403. Cross-org 404. Purpose does not grant access. Consent does not grant Adverse Event access. Authorization is permission-based. `Wave1PolicyPDP` is unchanged and does not inspect role names or Consent rows.

## L. Purpose

`X-Purpose` required, normalized (`treatment` → `TREATMENT`), catalog-validated. Missing / unknown = 422. Recorded on success audit. Does not grant authorization.

## M. Audit / logging

Events: `ADVERSE_EVENT_CREATED`, `ADVERSE_EVENT_AMENDED`, `ADVERSE_EVENT_ENTERED_IN_ERROR`. Metadata is category / severity / status / version / purpose — not note, display, code, NIK, BPJS, tokens, or secrets. Inherited Wave 1 DENIED-audit rollback remains P2: a 403 on `clinical.adverse_event.create` still leaves 0 `DENIED` rows. Not redesigned.

## N. Provenance

Insert-only `clinical_provenances`. Subject type `ADVERSE_EVENT`. `provenance_id` FK `ON DELETE RESTRICT`. Service always sets it. No orphan rows.

## O. Concurrency — executed live

All mutations use PostgreSQL `SELECT FOR UPDATE` (`ClinicalRepository.get_adverse_event_for_update`). Redis is not a clinical lock. Related-fact lookup is read-only and does not use Redis. Live races:

| Race | Live result |
|---|---|
| Amend vs amend | one 200, one 409, one `ADVERSE_EVENT_AMENDED` |
| EIE vs EIE | one 200, one 409, one `ADVERSE_EVENT_ENTERED_IN_ERROR`; version unchanged |
| Amend vs EIE | one 200, one 409; final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1 |

## P. API boundary

`POST /api/v1/clinical/adverse-events`, `GET /api/v1/clinical/adverse-events?patient_identity_id=`, `GET /api/v1/clinical/adverse-events/{id}`, `POST .../amend`, `POST .../entered-in-error`. PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No `/fhir/AdverseEvent/`. No FHIR.

## Q. Security / leakage

401 / 403 / 404 / 409 / 422 behave as specified. Cross-org GET is 404 without note, display, code, or SQL errors. Registrar denial is 403 without payload leakage.

## R. Runtime

`/api/v1/health/live` = 200. `/api/v1/health/ready` = 200 with postgres / redis / object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` untouched. Backend image was not rebuilt. Live `:9100` POST `/api/v1/clinical/adverse-events` returns 404 (image lag). Integration tests execute the working-tree ASGI app against live Postgres.

## S. Quality gates

`ruff check app tests` PASS. `ruff format --check app tests` PASS. `mypy app` PASS (105 app files). pytest **237 passed**. Adverse Event hardening file: **10 passed**. Frozen Condition / Observation / Laboratory / Medication / Allergy / Consent / Immunization / Procedure / Medical Device integration files: **34 passed**. Alembic `current == heads == 20260814_0016`. Production `rate_limit_per_minute` remains **120**. Test-only ceiling remains **10000**.

## T. Secret scan

No `.env`, credentials, private keys, GitHub tokens, production secrets, `.venv`, runtime volumes, logs, or cache artifacts in the working tree.

## U. Frozen-domain regression

Medical Device hardening later-table absence list still forbids `fhir_devices`, `fhir_medical_devices`, `care_plans`, `vital_signs`, `diagnoses`, `patient_histories`. The earlier removal of `adverse_events` from that list is an absence-probe update only; Medical Device FKs, lifecycle, and semantics are unchanged. Frozen-domain tests passed.

## V. Findings

No P0/P1. Inherited P2/P3 were not redesigned. No production code change. No approved Adverse Event contract was changed.

## W. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; reconfirmed on Adverse Event 403; not redesigned |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until a later PDP wave | Documented; Consent is not a PDP for Adverse Event |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same frozen clinical pattern |
| P3 | Duplicate adverse-event facts are allowed | Allowed in this slice |
| P3 | Causality / outcome / `LIFE_THREATENING` deferred | Approved design |
| P3 | Test `rate_limit_per_minute` remains 10000 | Test-only; production remains 120 |
| P3 | Docker backend image lags this working-tree change | Tests cover the working tree; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## X. Hardening changes this pass

No production Adverse Event code change. Focused tests: concurrent amend vs amend, concurrent EIE vs EIE, concurrent amend vs EIE, dedicated amendable-severity contract (API + SQL + EIE freeze), related-fact SQL XOR and FK RESTRICT, no related-resource mutation, post-create immutable SQL including related FKs, terminal freeze including severity, PATCH/PUT/DELETE 405 plus absent `/revoke` `/stop`, registrar / IDENTITY_OFFICER 403 without leakage, inherited DENIED-audit count, consent does not grant access, PLATFORM_ADMIN create/amend/EIE, MERGED + encounter binding, RETIRED 409, purpose normalization, `SELECT FOR UPDATE` source assertion, production rate limit 120, `Wave1PolicyPDP` has no role-name or Consent checks.

## Y. Exact files changed this hardening pass

- `backend/tests/integration/test_wave2b7_hardening.py` (added)
- `docs/gates/wave2b7-adverse-event-hardening-gate.md` (this file)

## Z. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Adverse Event is **hardenable** and **hardening is complete**
- Adverse Event should **remain unfrozen**
- Do not start Patient History / Vital Signs table / CarePlan / Diagnosis / FHIR / AI / RAG / CDS / pharmacovigilance / incident management
- Do not commit, tag, or push in this pass
