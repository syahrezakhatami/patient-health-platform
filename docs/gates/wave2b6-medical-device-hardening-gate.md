# Wave 2B.6 — Medical Device production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-15
**Frozen Wave 2B.5:** `wave-2b5-procedure-frozen` / `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad`
**Medical Device Alembic:** `20260814_0015`
**Medical Device freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Medical Device is a persisted documented patient-device association. It is **not** a FHIR Device resource, inventory object, asset record, warehouse item, maintenance ticket, recall workflow, UDI registry, or CDS object.

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad` |
| Tag | Annotated `wave-2b5-procedure-frozen` → same commit |
| Working tree | Dirty: Medical Device implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0015` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014 → 0015` |
| Migrations `0001`–`0014` | Untouched |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` (Compose) |
| `gsai-minio` / Compose `minio` | Untouched |

## B. Repository

Medical-Device-only scope. Frozen Procedure/Immunization/Consent/Allergy/Medication/Laboratory/Observation/Condition/Wave 1 PDP modules were not redesigned. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched. No production Medical Device code changed in this hardening pass: live schema, lifecycle, identity, encounter, authorization, audit, provenance, and API already matched the approved Immunization/Procedure contract.

No `.env`, keys, tokens, `.venv`, caches, logs, or volume data in the working tree.

## C. Migration

`20260814_0015` is additive. It creates `medical_devices`; extends `clinical_provenances.subject_type` with `MEDICAL_DEVICE`; seeds `clinical.medical_device.*` permissions. `0001`–`0014` were not rewritten. No `0016`.

## D. Database integrity

Live `php_dev`:

- UUID PK `medical_devices.id`
- FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances` — all `ON DELETE RESTRICT`
- `encounter_id`, `facility_id`, and `provenance_id` nullable
- CHECKs: `category` (`DOCUMENTED` \| `REPORTED`), `status` (`ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR`), `association_status` (`IN_USE` \| `NO_LONGER_USED`), coded pair non-empty, `version >= 1`
- Indexes: patient, encounter, org, recorded_at
- Trigger `trg_medical_devices_history_immutable` / `prevent_medical_device_history_mutation()`
- DELETE denied by trigger (`medical_devices cannot be deleted`)
- TRUNCATE denied for `app_dml` (`REVOKE TRUNCATE`)
- No JSON / JSONB columns
- No `fhir_medical_devices` / `fhir_devices`
- `app_dml`: INSERT / SELECT / UPDATE only; DELETE and TRUNCATE denied
- Invalid category / status / association_status / version INSERT fails CHECK
- Orphan `provenance_id` count: 0
- Null `provenance_id` count: 0
- Invalid status / category / association_status count: 0
- `provenance_id` column remains nullable (frozen convention); service always sets it

## E. Lifecycle

Create is always `ACTIVE`. `ACTIVE → AMENDED` and `AMENDED → AMENDED` only when association status, occurrence, or note actually changes. Version increments exactly once per successful amend. `ACTIVE|AMENDED → ENTERED_IN_ERROR` is terminal and does not increment version (Allergy/Immunization/Procedure convention). Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, terminal → anything. `EXPIRED` and `STOPPED` are not persisted as record or association statuses. No generic PUT. No PATCH. No DELETE. No `/revoke`. No `/stop`. No generic `/status` lifecycle endpoint. No duplicate successful lifecycle audit on no-op or losing races.

## F. Immutability

Frozen after create: `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `category`, `code_system` / `code` / `code_display`, recorder, `recorded_at`, `provenance_id`. Amendable until EIE: `association_status`, `occurrence_at`, `note_text`, status → `AMENDED`, version. Terminal EIE freezes the complete row, including association status, occurrence, and note. Verified through API (extra immutable fields on amend are ignored or 422 and do not rewrite identity/code/category), service transitions, direct SQL UPDATE, `app_dml` UPDATE, and the trigger.

## G. Association status

`IN_USE` and `NO_LONGER_USED` are clinical association states only. They are not inventory, asset, warehouse, maintenance, recall, or retirement statuses. Amendment `IN_USE → NO_LONGER_USED` (and the reverse) follows `ACTIVE → AMENDED` with version +1. `EXPIRED` / `STOPPED` / `RETIRED` association values fail CHECK / 422. No Procedure FK.

## H. Identity / MPI

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter follows the frozen same-patient check against the canonical identity and returns **409** (not a defect). RETIRED 409. Unknown / cross-org 404. Standalone anonymous 409. Anonymous + documentable `EMER` allowed. Anonymous + non-`EMER` encounter 409. Historical `patient_identity_id` is not rewritten after MPI merge.

## I. Encounter binding

Optional. Same patient, same org, documentable. `CANCELLED` / `ENTERED_IN_ERROR` encounters 409 without mutating the encounter. Cross-org encounter 404. Wrong patient/encounter pair 409. Medical Device never mutates encounter status. Encounter status is unchanged after create, amend, and EIE.

## J. Authorization

Permissions: `clinical.medical_device.create|read|update|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: all (HTTP-tested: PLATFORM_ADMIN create, amend, EIE). ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: none, including Registrar + `TREATMENT`. Unauthenticated 401. Unprovisioned JWT 403. Insufficient permission 403. Cross-org resource 404. Cross-org identity write 404. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default. Purpose does not grant access. Consent does not grant Medical Device access. Authorization is permission-based, not role-name checks. `Wave1PolicyPDP` is unchanged.

## K. Purpose

`X-Purpose` required, normalized (`treatment` → `TREATMENT`), and validated against the existing catalog. Missing / unknown = 422. Recorded on success audit. A valid purpose does **not** grant authorization.

## L. Audit / logging

Events: `MEDICAL_DEVICE_CREATED`, `MEDICAL_DEVICE_AMENDED`, `MEDICAL_DEVICE_ENTERED_IN_ERROR`. Metadata is category / status / association_status / version / purpose — not device display, device code, note, NIK, BPJS, tokens, passwords, or secrets. Logging redacts `note`, `note_text`, `code_display`, `device_display`, `device_code`, and `medical_device_note`. Inherited Wave 1 DENIED-audit rollback remains P2: a 403 on `clinical.medical_device.create` still leaves 0 `DENIED` rows. Not redesigned.

## M. Provenance

Insert-only `clinical_provenances`. Subject type `MEDICAL_DEVICE`. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance rejected. Referenced provenance cannot be deleted. No orphan rows. No null `provenance_id` in service-created rows.

## N. Concurrency — executed live

All mutations use PostgreSQL `SELECT FOR UPDATE` (`ClinicalRepository.get_medical_device_for_update`). Redis is not a clinical lock (`db_app` integration fixture sets `redis=None`; amend/EIE service methods do not reference Redis). Live races:

| Race | Live result |
|---|---|
| Amend vs amend | one 200, one 409, one `MEDICAL_DEVICE_AMENDED` |
| EIE vs EIE | one 200, one 409, one `MEDICAL_DEVICE_ENTERED_IN_ERROR`; version unchanged |
| Amend vs EIE | one 200, one 409; final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1; version 1 or 2 |

## O. API boundary

`POST /api/v1/clinical/medical-devices`, `GET /api/v1/clinical/medical-devices?patient_identity_id=`, `GET /api/v1/clinical/medical-devices/{id}`, `POST .../amend`, `POST .../entered-in-error`. PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No `/fhir/`. No FHIR Device. No inventory, asset, maintenance, recall, CarePlan, Patient History, Adverse Event, Vital Signs, or Diagnosis routes.

## P. Security / leakage

401 / 403 / 404 / 409 / 422 behave as specified. Cross-org GET and mutation are 404 without device code, display, note, patient data, organization data, or SQL errors. Registrar / IDENTITY_OFFICER denial is 403 without payload leakage. Unknown UUID 404 without SQLAlchemy / database details.

## Q. Runtime

`/api/v1/health/live` = 200. `/api/v1/health/ready` = 200 with postgres / redis / object_storage ok. Ports unchanged. Compose `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` untouched. Backend image was not rebuilt in this hardening pass. Docker OpenAPI on `:9100` does not list `/api/v1/clinical/medical-devices` (image lag). Integration tests execute the working-tree ASGI app against live Postgres.

## R. Quality gates

`ruff check app tests` PASS. `ruff format --check app tests` PASS. `mypy app` PASS (105 app files). pytest **217 passed**. Medical Device hardening file: **6 passed**. Frozen Condition / Observation / Laboratory / Medication / Allergy / Consent / Immunization / Procedure plus prior hardening: **65 passed**. No tests skipped, weakened, or deleted. Repo-wide `ruff format --check` without paths still fails on frozen Alembic `0001`–`0014`; those files were not rewritten.

## S. Secret scan

No `.env`, credentials, private keys, GitHub tokens, production secrets, `.venv`, runtime volumes, logs, or cache artifacts in the working tree. `.gitignore` unchanged.

## T. Clinical boundary

Native `medical_devices` present. Columns for UDI, serial number, manufacturer, lot number, inventory/asset/warehouse status, Procedure FK, performer, body site, reason, and outcome are absent. FHIR Device, CarePlan, Patient History, Adverse Event, Vital Signs, and Diagnosis tables remain absent. Medical Device is not wired into other clinical getters. Frozen Procedure remains at `0a61ee6`.

## U. Findings

See scorecard. No P0/P1. Inherited P2/P3 were not redesigned. No new architectural decision was required. No approved Medical Device contract was changed.

## V. P0 / P1 / P2 / P3 scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; reconfirmed on Medical Device 403; not redesigned |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until a later PDP wave | Documented; Consent is not a PDP for Medical Device |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | `provenance_id` nullable (FK present; service always sets it) | Same Observation / Laboratory / Medication / Allergy / Consent / Immunization / Procedure pattern |
| P3 | Duplicate device-association facts are allowed | Allowed in this slice |
| P3 | UDI / serial / manufacturer / lot deferred | Approved design |
| P3 | Procedure FK / performer / body site / reason / outcome deferred | Approved design |
| P3 | Test `rate_limit_per_minute` remains 10000 | Test-only, inherited from Procedure hardening; production remains 120; not changed this pass |
| P3 | Docker backend image lags this working-tree change | Tests cover the working tree; image not rebuilt this pass |

**Verdict: PASS WITH P2**

## W. Hardening changes this pass

No production Medical Device code change. Focused tests: concurrent amend vs amend, concurrent EIE vs EIE, concurrent amend vs EIE, terminal EIE row freeze (API + SQL including association/occurrence/note/status/version and all frozen identity fields), post-create immutable SQL, PATCH/PUT/DELETE 405, registrar / IDENTITY_OFFICER read 403 without leakage, inherited DENIED-audit count, MERGED + encounter binding, RETIRED 409, cross-org identity 404, purpose normalization, PLATFORM_ADMIN create/amend/EIE, REPORTED category, `association_status` amendment, anonymous non-EMER 409, cancelled/EIE encounter 409 without mutating the encounter, CHECK constraints including `IMPLANTED` / `EXPIRED` / `RETIRED` / version 0, `SELECT FOR UPDATE` source assertion, FK `ON DELETE RESTRICT`, semantic-boundary absent columns/tables.

Test fixture: production rate limit remains 120. The inherited test ceiling of 10000 was not changed this pass.

## X. Exact files changed this hardening pass

- `backend/tests/integration/test_wave2b6_hardening.py` (added)
- `docs/gates/wave2b6-medical-device-hardening-gate.md` (this file)

## Y. Recommendation

- P0 exists: **no**
- P1 exists: **no**
- Medical Device is **hardenable** and **hardening is complete**
- Medical Device should **remain unfrozen**
- Do not start Patient History / Adverse Event / Vital Signs / CarePlan / Diagnosis / FHIR / AI / RAG / CDS / Consent-as-PDP / inventory / scheduling / registry
- Do not commit, tag, or push in this pass
