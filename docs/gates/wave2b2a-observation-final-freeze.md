# Wave 2B.2a — Observation final freeze

**Date:** 2026-08-14
**Verdict:** PASS WITH P2
**WAVE 2B.2a OBSERVATION:** FROZEN
**WAVE 2B.2b:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Executive summary

Native Observation was verified on the frozen Wave 2B.1 Condition baseline. Alembic head is `20260814_0008`. Quality gates: ruff, mypy, **130 pytest passed**. Live health/ready pass. Observation DELETE is `405`. `app_dml` DELETE is denied.

P0 = 0. P1 = 0. Residual P2/P3 are inherited or documented and were not redesigned.

## 2. Repository baseline

| Item | Value |
|---|---|
| Branch | `main` (tracks `origin/main`) |
| Previous freeze | `e0a716b1d8a18a5c98d8bb592ac62af11c71c701` / `wave-2b1-condition-frozen` |
| Tag | `wave-2b2a-observation-frozen` (this freeze commit) |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0008` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008` |
| Migrations `0001`–`0007` | Unchanged |

## 3. Observation domain

Native measurement/finding. Not a FHIR Observation resource. Not a laboratory result domain.

Categories: `VITAL_SIGNS`, `EXAM`, `OTHER`.

Value types (exactly one per row): `NUMERIC`, `TEXT`, `BOOLEAN`, `CODED`. No JSON clinical payload. Terminology remains `system` + `code` + optional `display`.

## 4. API boundary

Under `/api/v1/clinical/`:

- `POST /observations`
- `GET /observations?patient_identity_id=`
- `GET /observations/{id}`
- `POST /observations/{id}/amend`
- `POST /observations/{id}/entered-in-error`

No generic PUT. No DELETE. No `/api/v2/`.

## 5. Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone Observation rejected; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## 6. Encounter

Optional for ACTIVE. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Observation does not create or mutate encounters.

## 7. Lifecycle

Create → `FINAL`. `FINAL → AMENDED` via amend (no-op `409`). `FINAL|AMENDED → ENTERED_IN_ERROR`. EIE is terminal. No draft. No generic status route.

## 8. Immutability

Frozen after insert: patient, encounter, organization, facility, category, code, value type, recorder, recorded time, provenance. Amend may change value/unit/range/`effective_at`/status/version until EIE. Enforced at API, service, and database trigger.

## 9. Authorization / purpose

Permissions: `clinical.observation.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar + `TREATMENT`: `403`. `clinical.laboratory.create` deny-by-default. `X-Purpose` required; missing/unknown `422`. Purpose does not grant access.

## 10. Audit / provenance

Events: `OBSERVATION_CREATED`, `OBSERVATION_AMENDED`, `OBSERVATION_ENTERED_IN_ERROR`. Metadata does not store measured values, NIK, or tokens. Provenance reuses insert-only `clinical_provenances` with `subject_type=OBSERVATION`. `provenance_id` FK `ON DELETE RESTRICT`.

## 11. Concurrency / DELETE

Mutations use PostgreSQL `SELECT FOR UPDATE`. Concurrent identical amend and concurrent EIE: one `200`, one `409`, one matching audit. Concurrent amend vs EIE: final `ENTERED_IN_ERROR`. API DELETE `405`. Trigger and `app_dml` block DELETE.

## 12. Docker runtime

| Check | Result |
|---|---|
| `/api/v1/health/live` | alive |
| `/api/v1/health/ready` | postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched (`9000`/`9001`) |

## 13. Quality gates

ruff check/format PASS. mypy PASS (104 app files). pytest **130 passed**.

## 14. Clinical boundary

Observation is present. Laboratory, medication, allergy, consent, FHIR, AI, RAG, CDS remain absent.

## 15. Residual P2 / P3

| Sev | Finding |
|---|---|
| P2 | DENIED audit rows roll back with `ForbiddenError` (Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read is org-scoped until Consent |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | Duplicate vitals for the same code/time are allowed |

## 16. Publication

One commit: `feat: freeze Wave 2B.2a observation`.

Annotated tag: `wave-2b2a-observation-frozen`.

No force-push. No history rewrite. Wave 2B.2b is not started.
