# Wave 2B.3c — Consent final freeze

**Date:** 2026-08-15
**Verdict:** PASS WITH P2
**P0:** 0
**P1:** 0
**WAVE 2B.3c CONSENT:** FROZEN
**WAVE 2B.4:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. Consent is a persisted permit/refuse fact. It is **not** a PDP, FHIR Consent resource, or authorization grant.

Companion canvas: [wave2b3c-consent-final-freeze.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/wave2b3c-consent-final-freeze.canvas.tsx)

## A. Repository

`git@github.com:syahrezakhatami/patient-health-platform.git`

Consent-only publication on the frozen Allergy baseline. Frozen Condition, Observation, Laboratory, Medication, and Allergy behavior was not redesigned. Previous-wave tests only allow the new `consents` table and move deny-by-default stubs to `clinical.immunization.create`. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched.

## B. Branch

`main` tracks `origin/main`.

## C. Previous frozen baseline

Commit `21b20b998a7c3ccad41a1273ac4c85101b94144c`  
Tag `wave-2b3b-allergy-frozen`

## D. Consent freeze commit SHA

The SHA of this publication commit: `feat: freeze Wave 2B.3c consent`.  
Recorded after commit as HEAD on `main`.

## E. Parent SHA

`21b20b998a7c3ccad41a1273ac4c85101b94144c`

## F. Tag name

`wave-2b3c-consent-frozen` (annotated)

## G. Tag target SHA

The Consent freeze commit (D). Verified with `git rev-list -n 1 wave-2b3c-consent-frozen` == HEAD.

## H. Push result

Normal push of `main` and `wave-2b3c-consent-frozen` only. No force-push. No history rewrite.

## I. Working tree

Clean after publication. No `.env`, credentials, private keys, tokens, `.venv`, volumes, logs, or cache artifacts included.

## J. Alembic current/head

`current == heads == 20260814_0012` (exactly one head)

## K. Migration chain

`0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012`

Migrations `0001`–`0011` were not rewritten. No `0013`.

## L. Database integrity

Live `consents`:

- UUID PK
- FKs to `patient_identities`, `encounters`, `organizations`, `facilities`, `clinical_provenances`
- All `ON DELETE RESTRICT`
- CHECKs: category, scope, decision, source, status, version ≥ 1, period order, `revoked_at` consistency, coded pair
- Indexes: patient, encounter, org, facility, status, recorded_at, `(patient, org, status)`, `period_end`
- Trigger `trg_consents_history_immutable`
- `app_dml`: INSERT / SELECT / UPDATE only
- DELETE / TRUNCATE denied
- Orphan provenance: 0
- Null / invalid provenance references: 0

## M. Docker runtime

| Check | Result |
|---|---|
| `/api/v1/health/live` | 200 alive |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |

## N. Quality gates

ruff check / ruff format --check PASS. mypy PASS (105 app files). pytest **180 passed**.

## O. Security / secret scan

No `.env`, private keys, GitHub tokens, production secrets, passwords beyond existing documented local-dev grant placeholders, runtime volumes, logs, `.venv`, or cache artifacts in the publication tree.

## P. Consent API boundary

Under `/api/v1/clinical/`:

- `POST /consents`
- `GET /consents?patient_identity_id=`
- `GET /consents/{id}`
- `POST /consents/{id}/amend`
- `POST /consents/{id}/revoke`
- `POST /consents/{id}/entered-in-error`

PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No FHIR Consent. No Consent-as-PDP.

## Q. Identity behavior

Canonical FK `patient_identities.id`. ACTIVE accepted. MERGED without encounter binds the survivor. MERGED with a historical source encounter follows the frozen same-patient check and returns 409. RETIRED 409. Unknown / cross-org 404. ANONYMOUS 409 including with EMER. Historical `patient_identity_id` is not rewritten after MPI merge (by design).

## R. Encounter behavior

Optional. Same patient, same org, documentable. CANCELLED / ENTERED_IN_ERROR encounters 409. Cross-org encounter 404. Wrong pair 409. Consent does not mutate encounters.

## S. Lifecycle

CREATE → ACTIVE.  
ACTIVE / AMENDED → AMENDED only when a mutable field changes.  
ACTIVE / AMENDED → REVOKED (sets `revoked_at`, increments version).  
ACTIVE / AMENDED → ENTERED_IN_ERROR (terminal; version unchanged).  

Terminal: REVOKED, ENTERED_IN_ERROR.  
Rejected: no-op amend, double revoke, double EIE, AMENDED → ACTIVE, terminal → anything, generic PUT, DELETE.  
`EXPIRED` is not persisted. `is_effective` is computed.

## T. Immutability

Frozen after create: patient, encounter, org, facility, category, scope, decision, code / display, source, recorder, `recorded_at`, provenance. Amendable until terminal: period, note, status → AMENDED, version. ENTERED_IN_ERROR freezes the complete row. Enforced at API, service, trigger, and `app_dml`.

## U. Authorization

`clinical.consent.create|read|update|revoke|entered_in_error`. CLINICIAN / PLATFORM_ADMIN: full. ORG_ADMIN / AUDITOR: read. Registrar and IDENTITY_OFFICER: denied, including Registrar + TREATMENT. Unauthenticated 401. Unprovisioned JWT 403. Facility out-of-scope 403. Cross-org 404. `clinical.diagnosis.create` and `clinical.immunization.create` remain deny-by-default.

## V. Purpose

`X-Purpose` required, normalized, validated, and audited. Missing / unknown = 422. A valid purpose does not grant authorization.

## W. Audit

Events: `CONSENT_CREATED`, `CONSENT_AMENDED`, `CONSENT_REVOKED`, `CONSENT_ENTERED_IN_ERROR`. Metadata excludes note, `consent_note`, code display, NIK / BPJS, tokens, passwords, and secrets. Logging redacts `note`, `note_text`, `consent_note`, and `code_display`. Wave 1 DENIED-audit rollback remains inherited and was not redesigned.

## X. Provenance

`subject_type = CONSENT`. Insert-only. Invalid provenance rejected. Referenced provenance cannot be deleted. FK `ON DELETE RESTRICT`.

## Y. Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not a lock. Live results: amend/amend, revoke/revoke, EIE/EIE = 200 + 409. Amend vs revoke and amend vs EIE produce a deterministic terminal state. Revoke vs EIE has exactly one terminal winner.

## Z. Clinical boundary

Native `consents` is present. Immunization, Procedure, CarePlan, FHIR, AI, RAG, CDS, break-glass, patient portal, and Consent-as-PDP remain absent. Frozen Allergy remains at `21b20b9`.

## AA. Residual P2 / P3

| Sev | Finding |
|---|---|
| P2 | DENIED audit rows roll back with `ForbiddenError` (Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read remains org-scoped until a later PDP wave |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | `provenance_id` nullable with FK present (service always sets it) |
| P3 | Duplicate ACTIVE consent facts are allowed |
| P3 | Docker backend image may lag working-tree verification if the image was not rebuilt |

Residual P2/P3 are not reasons to redesign this freeze.

## AB. Final verdict

**PASS WITH P2**

P0 = 0. P1 = 0. One freeze commit. One annotated tag. Normal push only. Wave 2B.4 is not started.
