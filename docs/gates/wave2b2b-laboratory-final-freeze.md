# Wave 2B.2b — Laboratory final freeze

**Date:** 2026-08-14
**Verdict:** PASS WITH P2
**WAVE 2B.2b LABORATORY:** FROZEN
**WAVE 2B.3:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Executive summary

Native Laboratory (order, specimen, result) was verified on the frozen Wave 2B.2a Observation baseline. Alembic head is `20260814_0009`. Quality gates: ruff, mypy, **144 pytest passed**. Live health/ready pass. Laboratory DELETE is `405`. `app_dml` DELETE is denied.

P0 = 0. P1 = 0. Residual P2/P3 are inherited or documented and were not redesigned.

## 2. Repository baseline

| Item | Value |
|---|---|
| Branch | `main` (tracks `origin/main`) |
| Previous freeze | `32500d1492994154c58c6eb65cade6cf42486d4f` / `wave-2b2a-observation-frozen` |
| Tag | `wave-2b2b-laboratory-frozen` (this freeze commit) |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0009` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009` |
| Migrations `0001`–`0008` | Unchanged |

## 3. Laboratory domain

Native order, specimen, and result. Not FHIR DiagnosticReport / ServiceRequest / Specimen / Observation. Not a terminology server.

Result value types (exactly one per row): `NUMERIC`, `TEXT`, `BOOLEAN`, `CODED`. No JSON clinical payload. Terminology remains `system` + `code` + optional `display`.

## 4. API boundary

Under `/api/v1/clinical/`:

- `POST|GET /laboratory/orders`
- `GET /laboratory/orders/{id}`
- `POST /laboratory/orders/{id}/cancel`
- `POST /laboratory/orders/{id}/entered-in-error`
- `POST|GET /laboratory/specimens`
- `GET /laboratory/specimens/{id}`
- `POST /laboratory/specimens/{id}/reject`
- `POST /laboratory/specimens/{id}/entered-in-error`
- `POST|GET /laboratory/results`
- `GET /laboratory/results/{id}`
- `POST /laboratory/results/{id}/amend`
- `POST /laboratory/results/{id}/entered-in-error`

No generic PUT. No DELETE. No `/api/v2/`.

## 5. Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone laboratory rejected; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## 6. Encounter

Optional for ACTIVE on the order. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Specimen and result inherit encounter from the order. Laboratory does not create or mutate encounters.

## 7. Lifecycle

Order: create `REGISTERED`; first specimen → `IN_PROGRESS`; cancel only from `REGISTERED`; `ENTERED_IN_ERROR` terminal. No `COMPLETED`.

Specimen: create `COLLECTED` → `REJECTED` or `ENTERED_IN_ERROR`.

Result: create `FINAL` → `AMENDED`; `FINAL|AMENDED` → `ENTERED_IN_ERROR`. No draft. No-op amend `409`. Value type immutable.

No-op / invalid transitions are `409` and do not duplicate success audit.

## 8. Immutability

Frozen after insert: patient, encounter, organization, facility, codes, value type, recorder, ordered/collected/recorded time, provenance. Result amend may change value/unit/range/interpretation/`effective_at`/status/version until EIE. Enforced at API, service, and database trigger.

## 9. Authorization / purpose

Permissions: `clinical.laboratory.{order,specimen,result}.{create,read,update,entered_in_error}`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar + `TREATMENT`: `403`. `clinical.laboratory.create`, `clinical.medication.create`, and `clinical.diagnosis.create` remain deny-by-default. `X-Purpose` required; missing/unknown `422`. Purpose does not grant access.

## 10. Audit / provenance

Events: `LAB_ORDER_CREATED`, `LAB_ORDER_IN_PROGRESS`, `LAB_ORDER_CANCELLED`, `LAB_ORDER_ENTERED_IN_ERROR`, `LAB_SPECIMEN_COLLECTED`, `LAB_SPECIMEN_REJECTED`, `LAB_SPECIMEN_ENTERED_IN_ERROR`, `LAB_RESULT_CREATED`, `LAB_RESULT_AMENDED`, `LAB_RESULT_ENTERED_IN_ERROR`. Metadata does not store measured values, NIK, BPJS, or tokens. Logging redacts value keys and `reference_range_low` / `reference_range_high`. Provenance reuses insert-only `clinical_provenances` with laboratory subject types. `provenance_id` FK `ON DELETE RESTRICT`.

## 11. Concurrency / DELETE

Mutations use PostgreSQL `SELECT FOR UPDATE`. Concurrent cancel vs first specimen, double cancel, specimen reject vs EIE, identical amend, double EIE, and amend vs EIE: one `200`, one `409`, no duplicate success audit. Redis is not a laboratory lock. API DELETE `405`. Trigger and `app_dml` block DELETE.

## 12. Docker runtime

| Check | Result |
|---|---|
| `/api/v1/health/live` | alive |
| `/api/v1/health/ready` | postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |

## 13. Quality gates

ruff check/format PASS. mypy PASS (105 app files). pytest **144 passed**.

## 14. Clinical boundary

Laboratory is present. Medication, allergy, consent, FHIR, AI, RAG, CDS remain absent.

## 15. Residual P2 / P3

| Sev | Finding |
|---|---|
| P2 | DENIED audit rows roll back with `ForbiddenError` (Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read is org-scoped until Consent |
| P2 | Result amend/EIE does not re-check parent order/specimen terminal state (independent resource lifecycles) |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | Duplicate laboratory facts for the same code/time are allowed |
| P3 | `provenance_id` nullable with FK present (same Observation pattern) |

## 16. Publication

One commit: `feat: freeze Wave 2B.2b laboratory`.

Annotated tag: `wave-2b2b-laboratory-frozen`.

No force-push. No history rewrite. Wave 2B.3 is not started.
