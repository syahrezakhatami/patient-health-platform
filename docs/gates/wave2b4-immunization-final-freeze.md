# Wave 2B.4 — Immunization final freeze

**Date:** 2026-08-15
**Verdict:** PASS WITH P2
**P0:** 0
**P1:** 0
**WAVE 2B.4 IMMUNIZATION:** FROZEN
**WAVE 2B.5:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. Immunization is a persisted administered/reported vaccination fact. It is **not** a FHIR Immunization resource, schedule, forecast, inventory, registry, or CDS engine.

## A. Repository

`git@github.com:syahrezakhatami/patient-health-platform.git`

Immunization-only publication on the frozen Consent baseline. Frozen Condition, Observation, Laboratory, Medication, Allergy, and Consent behavior was not redesigned. Previous-wave tests only allow the new `immunizations` table and move deny-by-default stubs to `clinical.procedure.create`. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched.

Native Immunization fact. NOT FHIR Immunization. No Consent-as-PDP. No AI/RAG/CDS. No Procedure. No CarePlan.

## B. Branch

`main` tracks `origin/main`.

## C. Previous frozen baseline

Commit `0258a20e5e49f2978fb16091603b5942c745ecda`  
Tag `wave-2b3c-consent-frozen`

## D. Immunization freeze commit SHA

The SHA of this publication commit: `feat: freeze Wave 2B.4 immunization`.  
Recorded after commit as HEAD on `main`.

## E. Parent SHA

`0258a20e5e49f2978fb16091603b5942c745ecda`

## F. Tag name

`wave-2b4-immunization-frozen` (annotated)

## G. Tag target SHA

The Immunization freeze commit (D). Verified with `git rev-list -n 1 wave-2b4-immunization-frozen` == HEAD.

## H. Push result

Normal push of `main` and `wave-2b4-immunization-frozen` only. No force-push. No history rewrite.

## I. Working tree

Clean after publication. No `.env`, credentials, private keys, tokens, `.venv`, volumes, logs, or cache artifacts included.

## J. Alembic current/head

`current == heads == 20260814_0013` (exactly one head)

## K. Migration chain

`0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013`

Migrations `0001`–`0012` were not rewritten. No `0014`.

## L. Docker / runtime

| Check | Result |
|---|---|
| `/api/v1/health/live` | 200 alive |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |

## M. Test results

ruff check / ruff format --check PASS. mypy PASS (105 app files). pytest **191 passed**.

## N. Security / secret scan

No `.env`, private keys, GitHub tokens, production secrets, passwords beyond existing documented local-dev grant placeholders, runtime volumes, logs, `.venv`, or cache artifacts in the publication tree. `.gitignore` unchanged.

## O. Immunization API boundary

Under `/api/v1/clinical/`:

- `POST /immunizations`
- `GET /immunizations?patient_identity_id=`
- `GET /immunizations/{id}`
- `POST /immunizations/{id}/amend`
- `POST /immunizations/{id}/entered-in-error`

PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No FHIR Immunization. No scheduling, forecasting, inventory, or registry routes.

## P. Identity behavior

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter follows the frozen same-patient check and returns 409. RETIRED 409. Unknown / cross-org 404. Standalone anonymous 409. Anonymous + documentable `EMER` allowed. Historical `patient_identity_id` is not rewritten after MPI merge (by design).

## Q. Encounter behavior

Optional. Same patient, same org, documentable. CANCELLED / ENTERED_IN_ERROR encounters 409. Cross-org encounter 404. Wrong pair 409. Immunization does not mutate encounters.

## R. Lifecycle

CREATE → ACTIVE.  
ACTIVE / AMENDED → AMENDED only when a mutable field changes.  
ACTIVE / AMENDED → ENTERED_IN_ERROR (terminal; version unchanged).  

Terminal: ENTERED_IN_ERROR.  
Rejected: no-op amend, double EIE, AMENDED → ACTIVE, terminal → anything, generic PUT, PATCH, DELETE.  
`REVOKED` and `EXPIRED` are not persisted. A corrected vaccination after EIE is a new fact.

## S. Immutability

Frozen after create: patient, encounter, org, facility, category, vaccine system / code / display, recorder, `recorded_at`, provenance. Amendable until EIE: `occurrence_at`, `route`, `site`, `note_text`, status → AMENDED, version. ENTERED_IN_ERROR freezes the complete row. Enforced at API, service, trigger, and `app_dml`.

## T. Authorization

`clinical.immunization.create|read|update|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: full. ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: denied, including Registrar + TREATMENT. Unauthenticated 401. Unprovisioned JWT 403. Facility out-of-scope 403. Cross-org 404. `clinical.diagnosis.create` and `clinical.procedure.create` remain deny-by-default. Consent does not grant Immunization access.

## U. X-Purpose

`X-Purpose` required, normalized, validated, and audited. Missing / unknown = 422. A valid purpose does not grant authorization.

## V. Audit

Events: `IMMUNIZATION_CREATED`, `IMMUNIZATION_AMENDED`, `IMMUNIZATION_ENTERED_IN_ERROR`. Metadata excludes vaccine display, vaccine code, note, NIK / BPJS, tokens, passwords, and secrets. Logging redacts `note`, `note_text`, `code_display`, `vaccine_display`, `vaccine_code`, and `immunization_note`. Wave 1 DENIED-audit rollback remains inherited and was not redesigned.

## W. Provenance

`subject_type = IMMUNIZATION`. Insert-only. Invalid provenance rejected. Referenced provenance cannot be deleted. FK `ON DELETE RESTRICT`. Service always assigns `provenance_id`. Column remains nullable (frozen convention).

## X. Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not a lock. Live results: amend/amend and EIE/EIE = 200 + 409 with exactly one matching success audit. Amend vs EIE produces final `ENTERED_IN_ERROR` and exactly one EIE audit.

## Y. Clinical boundary

Native `immunizations` is present. Procedure, CarePlan, FHIR Immunization, AI, RAG, CDS, break-glass, patient portal, Consent-as-PDP, scheduling, forecasting, inventory, and national registry remain absent. Frozen Consent remains at `0258a20`.

## Z. Residual P2 / P3

| Sev | Finding |
|---|---|
| P2 | DENIED audit rows roll back with `ForbiddenError` (Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read remains org-scoped until a later PDP wave |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | `provenance_id` nullable with FK present (service always sets it) |
| P3 | Duplicate immunization facts are allowed |
| P3 | Docker backend image may lag working-tree verification if the image was not rebuilt |

Residual P2/P3 are not reasons to redesign this freeze.

## AA. Final verdict

**PASS WITH P2**

P0 = 0. P1 = 0. One freeze commit. One annotated tag. Normal push only. Wave 2B.5 is not started.
