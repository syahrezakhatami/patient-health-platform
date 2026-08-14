# Wave 2B.3a — Medication final freeze

**Date:** 2026-08-14
**Verdict:** PASS WITH P2
**WAVE 2B.3a MEDICATION:** FROZEN
**WAVE 2B.3b ALLERGY:** NOT STARTED
**WAVE 2B.3c CONSENT:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Executive summary

Native Medication was verified on the frozen Wave 2B.2b Laboratory baseline. Alembic head is `20260814_0010`. Quality gates: ruff, mypy, **156 pytest passed**. Live health/ready pass. Medication DELETE is `405`. `app_dml` DELETE is denied.

P0 = 0. P1 = 0. Residual P2/P3 are inherited or documented and were not redesigned.

## 2. Repository baseline

| Item | Value |
|---|---|
| Branch | `main` (tracks `origin/main`) |
| Previous freeze | `7ddd87ca33833d9298a9cd80c91fa847484fa027` / `wave-2b2b-laboratory-frozen` |
| Tag | `wave-2b3a-medication-frozen` (this freeze commit) |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0010` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010` |
| Migrations `0001`–`0009` | Unchanged |

## 3. Medication scope

Native prescribed or reported medication fact. Not FHIR MedicationRequest / MedicationAdministration / MedicationDispense / MedicationStatement. Not dispense, administration, inventory, or a national drug catalog.

Category is `PRESCRIBED` or `REPORTED`. Terminology remains `system` + `code` + optional `display`. Structured dose is `dose_numeric` + `dose_unit` (both or neither). Optional route enum. No JSON clinical payload.

## 4. API boundary

Under `/api/v1/clinical/`:

- `POST /medications`
- `GET /medications?patient_identity_id=`
- `GET /medications/{id}`
- `POST /medications/{id}/stop`
- `POST /medications/{id}/entered-in-error`

No generic PUT. DELETE returns `405`. No `/api/v2/`.

## 5. Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone medication rejected; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## 6. Encounter

Optional for ACTIVE. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Cross-org encounter `404`. Wrong patient/encounter `409`. Medication does not create or mutate encounters.

## 7. Lifecycle

Create is always `ACTIVE`. Allowed: `ACTIVE → STOPPED`, `ACTIVE → ENTERED_IN_ERROR`, `STOPPED → ENTERED_IN_ERROR`. Terminal: `ENTERED_IN_ERROR`. Rejected: `STOPPED → ACTIVE`, `STOPPED → STOPPED`, `ENTERED_IN_ERROR → anything`. No `COMPLETED`. No-op mutations return `409` and do not duplicate success audit.

## 8. Immutability

Frozen after insert: `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `category`, medication/code identity, dose fields, `route`, `started_at`, `recorded_at`, recorder, `provenance_id`. `stopped_at` is immutable once set. ENTERED_IN_ERROR freezes the complete row. Enforced at API, service, and `trg_medications_history_immutable`. Direct `app_dml` UPDATE of immutable fields is blocked.

## 9. Authorization / purpose

Permissions: `clinical.medication.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar + `TREATMENT`: `403`. Unauthenticated `401`. Unprovisioned JWT `403`. Facility out-of-scope `403`. Cross-org resource `404`. `clinical.diagnosis.create` remains deny-by-default. `X-Purpose` required and audited; missing/unknown `422`. Purpose does not grant access.

## 10. Audit / provenance / logs

Events: `MEDICATION_CREATED`, `MEDICATION_STOPPED`, `MEDICATION_ENTERED_IN_ERROR`. Metadata does not store drug names, doses, NIK, BPJS, tokens, passwords, or secrets. Logging redacts `dose_numeric`, `dose_unit`, `dose`, and `code_display`. Provenance reuses insert-only `clinical_provenances` with `subject_type=MEDICATION`. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance rejected. Referenced provenance cannot be deleted. Wave 1 DENIED-audit rollback was not redesigned.

## 11. Concurrency / DELETE

Mutations use PostgreSQL `SELECT FOR UPDATE`. Concurrent stop, concurrent ENTERED_IN_ERROR, and stop versus ENTERED_IN_ERROR: one success, competing mutation `409`, consistent final state, no duplicate lifecycle audit. Redis is not a medication lock. API DELETE `405`. Trigger and `app_dml` block DELETE. TRUNCATE denied.

## 12. Database

Live `medications`: UUID PK; FKs to patient, encounter, organization, facility, provenance all `ON DELETE RESTRICT`. CHECKs for category, status, route, dose pair, stopped_at shape, version ≥ 1. Immutability/DELETE trigger present. Orphan provenance count: 0. `app_dml`: INSERT/SELECT/UPDATE allowed; DELETE/TRUNCATE denied.

## 13. Docker runtime

| Check | Result |
|---|---|
| `/api/v1/health/live` | alive |
| `/api/v1/health/ready` | postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |

## 14. Quality gates

ruff check/format PASS. mypy PASS (105 app files). pytest **156 passed**.

## 15. Clinical boundary

Medication is present. Allergy, consent, FHIR, AI, RAG, CDS remain absent. Frozen Condition, Observation, and Laboratory remain intact.

## 16. Residual P2 / P3

| Sev | Finding |
|---|---|
| P2 | DENIED audit rows roll back with `ForbiddenError` (Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read is org-scoped until Consent |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | `provenance_id` nullable with FK present (service always supplies it) |
| P3 | Duplicate medication facts for the same code/time are allowed |
| P3 | Docker backend image lags working-tree verification if the image was not rebuilt |

Residual P2/P3 are not reasons to redesign this freeze.

## 17. Publication

One commit: `feat: freeze Wave 2B.3a medication`.

Annotated tag: `wave-2b3a-medication-frozen`.

No force-push. No history rewrite. Wave 2B.3b Allergy and Wave 2B.3c Consent are not started.
