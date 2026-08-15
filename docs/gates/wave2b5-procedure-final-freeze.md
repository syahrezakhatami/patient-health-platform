# Wave 2B.5 — Procedure final freeze

**Date:** 2026-08-15
**Verdict:** PASS WITH P2
**P0:** 0
**P1:** 0
**WAVE 2B.5 PROCEDURE:** FROZEN
**WAVE 2B.5 PROCEDURE:** PUBLISHED
**WAVE 2B.6:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. Procedure is a persisted performed/reported procedure fact. It is **not** a FHIR Procedure resource, order, care plan, scheduling object, CDS object, or workflow engine.

## A. Repository

`git@github.com:syahrezakhatami/patient-health-platform.git`

Procedure-only publication on the frozen Immunization baseline. Frozen Condition, Observation, Laboratory, Medication, Allergy, Consent, and Immunization behavior was not redesigned. Previous-wave tests only allow the new `procedures` table and move deny-by-default stubs to `clinical.care_plan.create`. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched. Test-only `rate_limit_per_minute` ceiling is 10000 (production remains 120).

Native Procedure fact. NOT FHIR Procedure. No Consent-as-PDP. No AI/RAG/CDS. No CarePlan.

## B. Previous frozen baseline

Commit `20bef7e7a7bc315f6898b508c1de1f237d00abcc`  
Tag `wave-2b4-immunization-frozen`  
Alembic `20260814_0013`

## C. New commit

This publication commit: `feat: freeze Wave 2B.5 procedure`.  
Recorded after commit as HEAD on `main`.

## D. Parent commit

`20bef7e7a7bc315f6898b508c1de1f237d00abcc`

## E. Branch

`main` tracks `origin/main`.

## F. Tag

`wave-2b5-procedure-frozen` (annotated)

## G. Tag target

The Procedure freeze commit (C). Verified with `git rev-list -n 1 wave-2b5-procedure-frozen` == HEAD.

## H. Push result

Normal push of `main` and `wave-2b5-procedure-frozen` only. No force-push. No history rewrite.

## I. Working tree

Clean after publication. No `.env`, credentials, private keys, tokens, `.venv`, volumes, logs, or cache artifacts included.

## J. Alembic current/head

`current == heads == 20260814_0014` (exactly one head)

Chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014`

Migrations `0001`–`0013` were not rewritten. No `0015`.

## K. Test results

`ruff check app tests` PASS. `ruff format --check app tests` PASS. `mypy app` PASS (105 app files). pytest **204 passed**. Frozen Condition / Observation / Laboratory / Medication / Allergy / Consent / Immunization: **49 passed**.

## L. Runtime health

| Check | Result |
|---|---|
| `/api/v1/health/live` | 200 alive |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |

## M. API boundary

Under `/api/v1/clinical/`:

- `POST /procedures`
- `GET /procedures?patient_identity_id=`
- `GET /procedures/{id}`
- `POST /procedures/{id}/amend`
- `POST /procedures/{id}/entered-in-error`

PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No `/fhir/`. No FHIR Procedure. No CarePlan, scheduling, inventory, registry, AI, RAG, or CDS routes.

Category: `PERFORMED` \| `REPORTED`.  
CREATE → ACTIVE. ACTIVE/AMENDED → AMENDED. ACTIVE/AMENDED → ENTERED_IN_ERROR. No revoke. No `EXPIRED`.

## N. Security

Unauthenticated 401. Unprovisioned JWT 403. Facility out-of-scope 403. Cross-org resource / identity 404. Wrong identity/encounter pair 409. Invalid purpose 422. Unauthorized responses do not leak procedure code, display, note, NIK, BPJS, tokens, secrets, or SQL details. Authorization is permission-based (`clinical.procedure.create|read|update|entered_in_error`). `Wave1PolicyPDP` is unchanged. Consent does not grant Procedure access. Purpose does not grant authorization.

Secret scan: no `.env`, private keys, GitHub tokens, production secrets, runtime volumes, logs, `.venv`, or cache artifacts in the publication tree. `.gitignore` unchanged.

## O. Clinical boundary

Native `procedures` is present. CarePlan, FHIR Procedure, AI, RAG, CDS, break-glass, patient portal, Consent-as-PDP, scheduling, forecasting, inventory, and registry remain absent. Frozen Immunization remains at `20bef7e`.

## P. P0 / P1 / P2 / P3 residuals

| Sev | Finding |
|---|---|
| P0 | None |
| P1 | None |
| P2 | DENIED audit rows roll back with `ForbiddenError` (Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read remains org-scoped until a later PDP wave |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | `provenance_id` nullable with FK present (service always sets it) |
| P3 | Duplicate procedure facts are allowed |
| P3 | Performer / body site / reason / outcome deferred |
| P3 | Docker backend image may lag working-tree verification if the image was not rebuilt |

Residual P2/P3 are not reasons to redesign this freeze.

## Q. Final verdict

**PASS WITH P2**

P0 = 0. P1 = 0. One freeze commit. One annotated tag. Normal push only.

WAVE 2B.5 PROCEDURE = FROZEN  
WAVE 2B.5 PROCEDURE = PUBLISHED  
WAVE 2B.6 = NOT STARTED
