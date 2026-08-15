# Wave 2B.3b — Allergy final freeze

**Date:** 2026-08-15
**Verdict:** PASS WITH P2
**WAVE 2B.3b ALLERGY:** FROZEN
**WAVE 2B.3c CONSENT:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Executive summary

Native Allergy was verified on the frozen Wave 2B.3a Medication baseline. Alembic head is `20260814_0011`. Quality gates: ruff, mypy, **168 pytest passed**. Live health/ready pass. Allergy DELETE is `405`. `app_dml` DELETE/TRUNCATE are denied.

P0 = 0. P1 = 0. Residual P2/P3 are inherited or documented and were not redesigned.

## 2. Repository baseline

| Item | Value |
|---|---|
| Branch | `main` (tracks `origin/main`) |
| Previous freeze | `abb6d7a238a139608d645c7e916e3182dd5ecaa9` / `wave-2b3a-medication-frozen` |
| Tag | `wave-2b3b-allergy-frozen` (this freeze commit) |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0011` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011` |
| Migrations `0001`–`0010` | Unchanged |

## 3. Allergy scope

Native documented allergy/intolerance fact. Not FHIR AllergyIntolerance. Not a medication order, dispense, administration, or Consent record.

Category is `DRUG`, `FOOD`, `ENVIRONMENT`, or `OTHER`. Record status is `ACTIVE`, `AMENDED`, or `ENTERED_IN_ERROR`. Clinical status is `ACTIVE` or `INACTIVE`. Verification is `UNCONFIRMED`, `CONFIRMED`, or `REFUTED`. Optional criticality, severity, coded reaction, and onset. Terminology remains `system` + `code` + optional `display`. No JSON clinical payload.

## 4. API boundary

Under `/api/v1/clinical/`:

- `POST /allergies`
- `GET /allergies?patient_identity_id=`
- `GET /allergies/{id}`
- `POST /allergies/{id}/amend`
- `POST /allergies/{id}/entered-in-error`

No generic PUT. DELETE returns `405`. No `/api/v2/`.

## 5. Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone allergy rejected; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## 6. Encounter

Optional for ACTIVE. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Cross-org encounter `404`. Wrong patient/encounter `409`. Allergy does not create or mutate encounters.

## 7. Lifecycle

Create is always record `ACTIVE`. Allowed: `ACTIVE|AMENDED → AMENDED` via amend (must change a mutable field), `ACTIVE|AMENDED → ENTERED_IN_ERROR`. Terminal: `ENTERED_IN_ERROR`. Rejected: `AMENDED → ACTIVE`, no-op amend, double EIE, `ENTERED_IN_ERROR → anything`. No `COMPLETED`. No-op mutations return `409` and do not duplicate success audit.

## 8. Immutability

Frozen after insert: `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `category`, allergen code/display, `recorded_at`, recorder, `provenance_id`. Amendable until EIE: clinical/verification status, criticality, severity, reaction, `onset_at`, record status, version. ENTERED_IN_ERROR freezes the complete row. Enforced at API, service, and `trg_allergies_history_immutable`. Direct `app_dml` UPDATE of immutable fields is blocked.

## 9. Authorization / purpose

Permissions: `clinical.allergy.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar + `TREATMENT`: `403`. Unauthenticated `401`. Unprovisioned JWT `403`. Facility out-of-scope `403`. Cross-org resource `404`. `clinical.consent.create` and `clinical.diagnosis.create` remain deny-by-default. `X-Purpose` required and audited; missing/unknown `422`. Purpose does not grant access.

## 10. Audit / provenance / logs

Events: `ALLERGY_CREATED`, `ALLERGY_AMENDED`, `ALLERGY_ENTERED_IN_ERROR`. Metadata does not store allergen names, reaction details, severity, criticality, NIK, BPJS, tokens, passwords, or secrets. Logging redacts `code_display`, `reaction`, reaction coded fields, `severity`, and `criticality`. Provenance reuses insert-only `clinical_provenances` with `subject_type=ALLERGY`. `provenance_id` FK `ON DELETE RESTRICT`. Invalid provenance rejected. Referenced provenance cannot be deleted. Wave 1 DENIED-audit rollback was not redesigned.

## 11. Concurrency / DELETE

Mutations use PostgreSQL `SELECT FOR UPDATE`. Concurrent amend, concurrent ENTERED_IN_ERROR, and amend versus ENTERED_IN_ERROR: one success, competing mutation `409`, final state `ENTERED_IN_ERROR` for the race, no duplicate lifecycle audit. Redis is not an allergy lock. API DELETE `405`. Trigger and `app_dml` block DELETE. TRUNCATE denied.

## 12. Database

Live `allergies`: UUID PK; FKs to patient, encounter, organization, facility, provenance all `ON DELETE RESTRICT`. CHECKs for category, record status, clinical status, verification, criticality, severity, reaction pair, version ≥ 1. Immutability/DELETE trigger present. Orphan provenance count: 0. `app_dml`: INSERT/SELECT/UPDATE allowed; DELETE/TRUNCATE denied.

## 13. Docker runtime

| Check | Result |
|---|---|
| `/api/v1/health/live` | alive |
| `/api/v1/health/ready` | postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |

## 14. Quality gates

ruff check/format PASS. mypy PASS (105 app files). pytest **168 passed**.

## 15. Clinical boundary

Allergy is present. Consent, FHIR, AI, RAG, CDS remain absent. Frozen Condition, Observation, Laboratory, and Medication remain intact.

## 16. Residual P2 / P3

| Sev | Finding |
|---|---|
| P2 | DENIED audit rows roll back with `ForbiddenError` (Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read is org-scoped until Consent |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | `provenance_id` nullable with FK present (service always supplies it) |
| P3 | Duplicate allergy facts for the same allergen are allowed |
| P3 | Docker backend image lags working-tree verification if the image was not rebuilt |

Residual P2/P3 are not reasons to redesign this freeze.

## 17. Publication

One commit: `feat: freeze Wave 2B.3b allergy`.

Annotated tag: `wave-2b3b-allergy-frozen`.

No force-push. No history rewrite. Wave 2B.3c Consent is not started.
