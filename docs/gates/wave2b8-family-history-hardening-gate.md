# Wave 2B.8 — Family History production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-25
**Frozen Wave 2B.7:** `wave-2b7-adverse-event-frozen` / `8d455b3dede07b9ada00205ff6c49b41b97a0895`
**Family History Alembic:** `20260814_0017`
**Family History freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Family History is a persisted documented family-history fact (one controlled relationship + one coded finding). It is **not** a FHIR FamilyMemberHistory resource, Patient History aggregate, Condition, Diagnosis, CarePlan, Vital Signs table, pedigree, or CDS object.

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `8d455b3dede07b9ada00205ff6c49b41b97a0895` |
| Tag | Annotated `wave-2b7-adverse-event-frozen` → same commit |
| Working tree | Dirty: Family History implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0017` (single head) |
| Chain | `0001 → … → 0016 → 0017` |
| Migrations `0001`–`0016` | Untouched |
| Migration `0017` | Untouched this pass |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched |

## B. Repository

Family-History-only scope. Frozen Adverse Event / Medical Device / Procedure / Immunization / Consent / Allergy / Medication / Laboratory / Observation / Condition / Wave 1 PDP modules were not redesigned. `Wave1PolicyPDP` is untouched. No production Family History code changed in this hardening pass: live schema, lifecycle, identity, encounter, authorization, audit, provenance, and API already matched the approved design contract.

No `.env`, keys, tokens, `.venv`, caches, logs, or volume data in the working tree.

## C. Severity decision

Approved design is **not ambiguous**.

Source: [docs/clinical/wave2b8-family-history-domain-approval.md](../clinical/wave2b8-family-history-domain-approval.md) sections I and J.

- Section I (immutable after create) lists patient, encounter, org, facility, relationship, category, code/display, recorder, recorded_at, provenance.
- Section J (amendable until EIE) lists `occurrence_at`, `note_text`, status → `AMENDED`, version.
- Explicit sentence: relationship is an analogue of Adverse Event `category` / `code`, not of AE `severity`. Family History has no severity.
- Closed-decision table row 9: amendable fields = `occurrence_at`, `note_text`, status, version.

The DB trigger does **not** treat `NEW.occurrence_at` or `NEW.note_text` as historical facts. Relationship, category, and code are frozen by the trigger.

## D. Migration

`20260814_0017` is additive. It creates `family_histories`; extends `clinical_provenances.subject_type` with `FAMILY_HISTORY`; seeds `clinical.family_history.*` permissions. `0001`–`0016` were not rewritten. `0017` was not rewritten this pass.

## E. Database integrity

Live `php_dev`:

- UUID PK `family_histories.id`
- FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances` — all `ON DELETE RESTRICT`
- CHECKs: relationship `PARENT` \| `SIBLING` \| `CHILD` \| `GRANDPARENT` \| `GRANDCHILD` \| `AUNT_UNCLE` \| `COUSIN` \| `OTHER`; category `DOCUMENTED` \| `REPORTED`; status `ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR`; version ≥ 1; non-empty `code_system` / `code`
- Trigger `trg_family_histories_history_immutable` / `prevent_family_history_history_mutation()`
- DELETE denied by trigger
- TRUNCATE denied for `app_dml`
- `app_dml`: INSERT / SELECT / UPDATE; DELETE and TRUNCATE denied
- No JSON / JSONB clinical payload
- No `condition_id`
- No `patient_histories` / `fhir_family_member_histories` / `family_conditions` / `diagnoses` / `care_plans` / `vital_signs`
- Orphan / null `provenance_id` count on service-created rows: 0

## F. Semantic boundary

Family History is not Condition and is not Patient History. Creating a family-history row does not change Condition `clinical_status`. There is no Condition FK. Condition list does not include family-history ids. FHIR `FamilyMemberHistory` is absent.

## G. Lifecycle

Create is always `ACTIVE` v1. `ACTIVE → AMENDED` and `AMENDED → AMENDED` when occurrence or note actually changes. Version +1 per successful amend. `ACTIVE|AMENDED → ENTERED_IN_ERROR` is terminal and does not increment version. Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, terminal → anything. No PUT / PATCH / DELETE. No `/revoke` / `/stop`.

## H. Immutability

Frozen after create: patient, encounter, org, facility, relationship, category, code/display, recorder, recorded_at, provenance. Amendable until EIE: occurrence, note, status → `AMENDED`, version. Terminal EIE freezes the complete row, including occurrence and note. Verified through API, service, direct SQL, `app_dml`, and the trigger. Encounter status is unchanged after create, amend, and EIE.

## I. Identity / MPI

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter returns **409**. RETIRED 409. Unknown / cross-org 404. Standalone anonymous 409. Anonymous + documentable `EMER` allowed. Anonymous + non-`EMER` 409. Historical `patient_identity_id` is not rewritten after MPI merge. MPI was not redesigned.

## J. Encounter

Optional. Same patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` 409 without mutating the encounter. Cross-org 404. Wrong pair 409.

## K. Authorization

Permissions: `clinical.family_history.create|read|update|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: all (HTTP-tested: PLATFORM_ADMIN create, amend, EIE). ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: none, including Registrar + `TREATMENT` after a PERMIT consent. Unauthenticated 401. Unprovisioned JWT 403. Cross-org 404. Purpose does not grant access. Consent does not grant Family History access. Authorization is permission-based. `Wave1PolicyPDP` is unchanged and does not inspect role names or Consent rows.

## L. Purpose

`X-Purpose` required, normalized (`treatment` → `TREATMENT`), catalog-validated. Missing / unknown = 422. Recorded on success audit. Does not grant authorization.

## M. Audit / logging

Events: `FAMILY_HISTORY_CREATED`, `FAMILY_HISTORY_AMENDED`, `FAMILY_HISTORY_ENTERED_IN_ERROR`. Metadata is relationship / category / status / version / purpose — not note, display, code, NIK, BPJS, tokens, or secrets. Inherited Wave 1 DENIED-audit rollback remains P2: a 403 on `clinical.family_history.create` still leaves 0 `DENIED` rows. Not redesigned.

## N. Provenance

Insert-only `clinical_provenances`. Subject type `FAMILY_HISTORY`. `provenance_id` FK `ON DELETE RESTRICT`. Service always sets it. No orphan rows.

## O. Concurrency — executed live

All mutations use PostgreSQL `SELECT FOR UPDATE` (`ClinicalRepository.get_family_history_for_update`). Redis is not a clinical lock. Live races:

| Race | Live result |
|---|---|
| Amend vs amend | one 200, one 409, one `FAMILY_HISTORY_AMENDED`; version increments exactly once |
| EIE vs EIE | one 200, one 409, one `FAMILY_HISTORY_ENTERED_IN_ERROR`; version unchanged |
| Amend vs EIE | one 200, one 409; final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1 |

## P. API boundary

`POST /api/v1/clinical/family-histories`, `GET /api/v1/clinical/family-histories?patient_identity_id=`, `GET /api/v1/clinical/family-histories/{id}`, `POST .../amend`, `POST .../entered-in-error`. PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No `/fhir/FamilyMemberHistory/`. No FHIR.

## Q. Security / leakage

401 / 403 / 404 / 409 / 422 behave as specified. Cross-org GET is 404 without note, display, code, or SQL errors. Registrar denial is 403 without payload leakage.

## R. Runtime

`/api/v1/health/live` = 200. `/api/v1/health/ready` = 200 with postgres / redis / object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` untouched. Backend image was not rebuilt. Live `:9100` POST `/api/v1/clinical/family-histories` returns 404 (image lag). Integration tests execute the working-tree ASGI app against live Postgres.

## S. Quality gates

`ruff check app tests` PASS. `ruff format --check app tests` PASS. `mypy app` PASS (105 app files). pytest **256 passed**. Family History hardening file: **9 passed**. Frozen Condition / Observation / Laboratory / Medication / Allergy / Consent / Immunization / Procedure / Medical Device / Adverse Event integration + hardening files: **89 passed**. Alembic `current == heads == 20260814_0017`. Production `rate_limit_per_minute` remains **120**. Test-only ceiling remains **10000**.

## T. Secret scan

No `.env`, credentials, private keys, GitHub tokens, production secrets, `.venv`, runtime volumes, logs, or cache artifacts in the working tree.

## U. Frozen-domain regression

Adverse Event and Medical Device later-table absence lists still forbid `fhir_adverse_events`, `fhir_devices`, `fhir_medical_devices`, `care_plans`, `vital_signs`, `diagnoses`, `patient_histories`. `patient_histories` remains a Patient History absence probe, not a Family History forbidden-table rule. Frozen-domain tests passed. Frozen-domain semantics were not changed.

## V. Findings

No P0/P1. Inherited P2/P3 were not redesigned. No production code change. No approved Family History contract was changed. No new Family History defect was found.

## W. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Class | Action |
|---|---|---|---|
| P0 | None | — | — |
| P1 | None | — | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1 | Reconfirmed on Family History 403; not redesigned |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge | Inherited / by design | Documented |
| P2 | Same-org UUID read is org-scoped until a later PDP wave | Inherited | Documented; Consent is not a PDP for Family History |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note | Unchanged |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same frozen clinical pattern | Unchanged |
| P3 | Duplicate family-history facts are allowed | Allowed in this slice | Unchanged |
| P3 | Relative identity / deceased / age-at-onset deferred | Approved design | Unchanged |
| P3 | Test `rate_limit_per_minute` remains 10000 | Test-only; production remains 120 | Unchanged |
| P3 | Docker backend image lags this working-tree change | Image lag | Tests cover the working tree; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## X. Hardening changes this pass

No production Family History code change. Focused tests: concurrent amend vs amend (including version +1 once), concurrent EIE vs EIE, concurrent amend vs EIE, dedicated amendable occurrence/note contract (API + SQL + EIE freeze), extra immutable fields on amend do not rewrite relationship/category/code, post-create immutable SQL including relationship and category, terminal freeze including occurrence/note, PATCH/PUT/DELETE 405 plus absent `/revoke` `/stop`, registrar / IDENTITY_OFFICER 403 without leakage, inherited DENIED-audit count, consent does not grant access, PLATFORM_ADMIN create/amend/EIE, MERGED + encounter binding, RETIRED 409, anonymous standalone vs EMER, purpose normalization, `SELECT FOR UPDATE` source assertion, production rate limit 120, `Wave1PolicyPDP` has no role-name or Consent checks, Condition/Patient History/FHIR semantic boundary.

## Y. Exact files changed this hardening pass

- `backend/tests/integration/test_wave2b8_hardening.py` (added)
- `docs/gates/wave2b8-family-history-hardening-gate.md` (this file)
- `docs/clinical/wave2b8-family-history.md` (status header only: hardening complete, not frozen)

## Z. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Family History is **hardenable** and **hardening is complete**
- Family History should **remain unfrozen**
- Do not start Patient History / Vital Signs table / CarePlan / Diagnosis / FHIR / AI / RAG / CDS / pedigree
- Do not commit, tag, or push in this pass
