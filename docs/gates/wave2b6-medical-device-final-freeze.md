# Wave 2B.6 — Medical Device final freeze

**Date:** 2026-08-15
**Verdict:** PASS WITH P2
**P0:** 0
**P1:** 0
**WAVE 2B.6 MEDICAL DEVICE:** FROZEN
**WAVE 2B.6 MEDICAL DEVICE:** PUBLISHED
**WAVE 2B.7:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. Medical Device is a persisted documented patient-device association. It is **not** a FHIR Device resource, inventory object, asset record, warehouse item, maintenance ticket, recall workflow, UDI registry, scheduling object, CDS object, Procedure, Patient History, or Adverse Event.

Frozen Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, and Procedure were **not redesigned**.

## A. Repository

`git@github.com:syahrezakhatami/patient-health-platform.git`

Medical-Device-only publication on the frozen Procedure baseline. Frozen Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, and Procedure behavior was not redesigned. Previous-wave tests only allow the new `medical_devices` table. `Wave1PolicyPDP`, `authorize.py`, and `docker-compose.yml` are untouched. Test-only `rate_limit_per_minute` ceiling is 10000 (production remains 120).

Native Medical Device fact. NOT FHIR Device. No Consent-as-PDP. No AI/RAG/CDS. No CarePlan. No inventory. No Patient History. No Adverse Event.

## B. Previous frozen baseline

Commit `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad`  
Tag `wave-2b5-procedure-frozen`  
Alembic `20260814_0014`

## C. New commit

This publication commit: `feat(clinical): freeze wave 2b6 medical device`.  
Recorded after commit as HEAD on `main`.

## D. Parent commit

`0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad`

## E. Branch

`main` tracks `origin/main`.

## F. Tag

`wave-2b6-medical-device-frozen` (annotated)

## G. Tag target

The Medical Device freeze commit (C). Verified with `git rev-list -n 1 wave-2b6-medical-device-frozen` == HEAD.

## H. Push result

Normal push of `main` and `wave-2b6-medical-device-frozen` only. No force-push. No history rewrite.

## I. Working tree

Clean after publication. No `.env`, credentials, private keys, tokens, `.venv`, volumes, logs, or cache artifacts included.

## J. Alembic current/head

`current == heads == 20260814_0015` (exactly one head)

Chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014 → 0015`

Migrations `0001`–`0014` were not rewritten. No `0016`. `procedures` remain present and untouched.

## K. Test results

`ruff check app tests` PASS. `ruff format --check app tests` PASS. `mypy app` PASS (105 app files). pytest **217 passed**. Frozen Condition / Observation / Laboratory / Medication / Allergy / Consent / Immunization / Procedure plus prior hardening: **65 passed**. Medical Device hardening: **6 passed**. Combined frozen-domain + Medical Device hardening: **71 passed**.

## L. Runtime health

| Check | Result |
|---|---|
| `/api/v1/health/live` | 200 alive |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |
| Docker backend image on `:9100` | Does not list Medical Device routes (P3 lag; working-tree tests cover the implementation) |

## M. API boundary

Under `/api/v1/clinical/`:

- `POST /medical-devices`
- `GET /medical-devices?patient_identity_id=`
- `GET /medical-devices/{id}`
- `POST /medical-devices/{id}/amend`
- `POST /medical-devices/{id}/entered-in-error`

PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No `/fhir/`. No FHIR Device. No inventory, asset, maintenance, recall, CarePlan, Patient History, Adverse Event, Vital Signs, Diagnosis, AI, RAG, or CDS routes.

Category: `DOCUMENTED` \| `REPORTED`.  
Association: `IN_USE` \| `NO_LONGER_USED` (clinical association, not inventory).  
CREATE → ACTIVE. ACTIVE/AMENDED → AMENDED. ACTIVE/AMENDED → ENTERED_IN_ERROR. No revoke. No `STOPPED`. No `EXPIRED`. EIE is terminal and does not increment version.

## N. Security

Unauthenticated 401. Unprovisioned JWT 403. Cross-org resource / identity 404. Wrong identity/encounter pair 409. Invalid purpose 422. Unauthorized responses do not leak device code, display, note, NIK, BPJS, tokens, secrets, or SQL details. Authorization is permission-based (`clinical.medical_device.create|read|update|entered_in_error`). CLINICIAN / PLATFORM_ADMIN full. ORG_ADMIN / AUDITOR read. Registrar / IDENTITY_OFFICER denied. `Wave1PolicyPDP` is unchanged. Consent does not grant Medical Device access. Purpose does not grant authorization.

Secret scan: no `.env`, private keys, GitHub tokens, production secrets, runtime volumes, logs, `.venv`, or cache artifacts in the publication tree. `.gitignore` unchanged. No vendor/test/doc false positives required ignore.

## O. Clinical boundary

Native `medical_devices` is present. CarePlan, FHIR Device, Patient History, Adverse Event, Vital Signs, Diagnosis, AI, RAG, CDS, break-glass, patient portal, Consent-as-PDP, scheduling, inventory, asset, maintenance, recall, and registry remain absent. Frozen Procedure remains at `0a61ee6`. WAVE 2B.7 is NOT STARTED.

## P. P0 / P1 / P2 / P3 residuals

| Sev | Finding |
|---|---|
| P0 | None |
| P1 | None |
| P2 | DENIED audit rows roll back with `ForbiddenError` (inherited Wave 1; not redesigned) |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge (by design) |
| P2 | Same-org UUID read remains org-scoped until a later PDP wave |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` |
| P3 | `provenance_id` nullable with FK present (service always sets it) |
| P3 | Duplicate device-association facts are allowed |
| P3 | UDI / serial / manufacturer / lot deferred |
| P3 | Procedure FK / performer / body site / reason / outcome deferred |
| P3 | Test `rate_limit_per_minute` ceiling is 10000 (production remains 120) |
| P3 | Docker backend image lags this working-tree publication |

Residual P2/P3 are not reasons to redesign this freeze.

## Q. Final verdict

**PASS WITH P2**

P0 = 0. P1 = 0. One freeze commit. One annotated tag. Normal push only.

WAVE 2B.6 MEDICAL DEVICE = FROZEN  
WAVE 2B.6 MEDICAL DEVICE = PUBLISHED  
WAVE 2B.7 = NOT STARTED
