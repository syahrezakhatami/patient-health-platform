# Wave 2B.7 — Adverse Event final freeze

**Date:** 2026-08-16
**Verdict:** PASS WITH P2
**P0:** 0
**P1:** 0
**WAVE 2B.7 ADVERSE EVENT:** FROZEN
**WAVE 2B.7 ADVERSE EVENT:** PUBLISHED
**WAVE 2B.8:** NOT STARTED

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. Adverse Event is one documented coded adverse event associated with a patient. It is **not** a FHIR AdverseEvent resource, pharmacovigilance case, incident ticket, Patient History aggregate, Vital Signs table, CarePlan, Diagnosis, CDS object, or workflow engine.

Frozen Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, and Medical Device were **not redesigned**.

## A. Repository

`git@github.com:syahrezakhatami/patient-health-platform.git`

Adverse-Event-only publication on the frozen Medical Device baseline. Frozen Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, and Medical Device behavior was not redesigned. Previous-wave tests only allow the new `adverse_events` table. `Wave1PolicyPDP`, `authorize.py`, `docker-compose.yml`, and migrations `0001`–`0015` are untouched. Test-only `rate_limit_per_minute` ceiling is 10000 (production remains 120).

Native Adverse Event fact. NOT FHIR AdverseEvent. No Consent-as-PDP. No AI/RAG/CDS. No CarePlan. No Patient History. No Vital Signs table. No Diagnosis. No pharmacovigilance. No incident management. No inventory. No scheduling. No registry. No break-glass. No portal.

## B. Previous frozen baseline

Commit `fdcd24b19d9797034d89b6928c37dc6c47ffe863`  
Tag `wave-2b6-medical-device-frozen`  
Alembic `20260814_0015`

HEAD before this freeze commit was exactly that SHA. `main` tracked `origin/main`. The previous tag pointed at the Medical Device freeze.

## C. New commit

This publication commit: `feat(clinical): freeze wave 2b7 adverse event`.  
Recorded after commit as HEAD on `main`.

## D. Parent commit

`fdcd24b19d9797034d89b6928c37dc6c47ffe863`

## E. Branch

`main` tracks `origin/main`.

## F. Tag

`wave-2b7-adverse-event-frozen` (annotated)

## G. Tag target

The Adverse Event freeze commit (C). Verified with `git rev-list -n 1 wave-2b7-adverse-event-frozen` == HEAD.

## H. Push result

Normal push of `main` and `wave-2b7-adverse-event-frozen` only. No force-push. No history rewrite. The Medical Device freeze commit was not amended.

## I. Working tree

Clean after publication. No `.env`, credentials, private keys, tokens, `.venv`, volumes, logs, or cache artifacts included.

## J. Alembic current/head

`current == heads == 20260814_0016` (exactly one head)

Chain: `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014 → 0015 → 0016`

Migration `0016` is additive. Migrations `0001`–`0015` were not rewritten. No `0017`. `medical_devices` remain present and untouched. No `fhir_adverse_events` table. No JSON payload column.

## K. Test results

`ruff check app tests` PASS. `ruff format --check app tests` PASS. `mypy app` PASS (105 app files). pytest **237 passed**. Frozen Condition / Observation / Laboratory / Medication / Allergy / Consent / Immunization / Procedure / Medical Device plus Medical Device hardening: **34 passed**. Adverse Event hardening: **10 passed**. Combined frozen-domain + Adverse Event hardening: **44 passed**.

## L. Runtime health

| Check | Result |
|---|---|
| `/api/v1/health/live` | 200 alive |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage ok |
| `OBJECT_STORAGE_ENDPOINT` | `http://minio:9000` |
| Host ports | 9100 / 5433 / 6380 / 9101 / 9002 |
| `gsai-minio` | Untouched |
| Docker backend image on `:9100` | Does not expose Adverse Event routes (P3 lag; working-tree tests cover the implementation) |

## M. API boundary

Under `/api/v1/clinical/`:

- `POST /adverse-events`
- `GET /adverse-events?patient_identity_id=`
- `GET /adverse-events/{id}`
- `POST /adverse-events/{id}/amend`
- `POST /adverse-events/{id}/entered-in-error`

PUT = 405. PATCH = 405. DELETE = 405. No `/api/v2/`. No `/fhir/`. No `/fhir/AdverseEvent/`. No Adverse Event `/revoke` or `/stop`. No FHIR AdverseEvent. No pharmacovigilance, incident, CarePlan, Patient History, Vital Signs, Diagnosis, AI, RAG, or CDS routes.

Category: `DOCUMENTED` \| `REPORTED`.  
Severity: `MILD` \| `MODERATE` \| `SEVERE`. `LIFE_THREATENING` remains deferred. Severity is amendable until `ENTERED_IN_ERROR`.  
CREATE → ACTIVE, version 1. ACTIVE/AMENDED → AMENDED (version +1). ACTIVE/AMENDED → ENTERED_IN_ERROR (terminal; version does not increment). No-op amend = 409. Double EIE = 409. AMENDED → ACTIVE = 409. No DELETE. No generic PUT/PATCH. No revoke/stop/expire lifecycle.

Related facts: none, or exactly one of `medication_id` / `medical_device_id` / `procedure_id`. Enforced at API/service and database CHECK. Related facts are immutable. Related Medication, Medical Device, and Procedure rows are not mutated. Related FKs use `ON DELETE RESTRICT`.

## N. Security

Unauthenticated 401. Unprovisioned JWT 403. Cross-org resource / identity 404. Wrong identity/encounter pair 409. Invalid purpose 422. Unauthorized responses do not leak adverse-event code, display, note, NIK, BPJS, tokens, secrets, or SQL details. Authorization is permission-based (`clinical.adverse_event.create|read|update|entered_in_error`). CLINICIAN / PLATFORM_ADMIN full. ORG_ADMIN / AUDITOR read. Registrar / IDENTITY_OFFICER denied. `Wave1PolicyPDP` is unchanged. Consent does not grant Adverse Event access. Purpose does not grant authorization. Clinical concurrency uses PostgreSQL `SELECT FOR UPDATE`. Redis is not the clinical lock.

Secret scan: no `.env`, private keys, GitHub tokens, production secrets, runtime volumes, logs, `.venv`, or cache artifacts in the publication tree. `.gitignore` unchanged. No vendor/test/doc false positives required ignore.

## O. Clinical boundary

Native `adverse_events` is present. CarePlan, FHIR AdverseEvent, Patient History, Vital Signs table, Diagnosis, pharmacovigilance, incident management, AI, RAG, CDS, break-glass, patient portal, Consent-as-PDP, scheduling, inventory, and registry remain absent. Frozen Medical Device remains at `fdcd24b`. WAVE 2B.8 is NOT STARTED.

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
| P3 | Duplicate adverse-event facts are allowed |
| P3 | Causality / outcome deferred |
| P3 | `LIFE_THREATENING` deferred |
| P3 | Test `rate_limit_per_minute` ceiling is 10000 (production remains 120) |
| P3 | Docker backend image lags this working-tree publication |

Residual P2/P3 are inherited or explicitly deferred. They were not silently fixed during this freeze.

## Q. Scope and contract confirmation

Wave 2B.7 scope is Native Adverse Event only. Approved contract confirmed: one documented coded adverse event associated with a patient; table `adverse_events`; category `DOCUMENTED` \| `REPORTED`; severity `MILD` \| `MODERATE` \| `SEVERE` and amendable until EIE; lifecycle ACTIVE → AMENDED → ENTERED_IN_ERROR and ACTIVE → ENTERED_IN_ERROR; related-fact XOR; frozen MPI/encounter reuse; permission-based authorization; mandatory `X-Purpose`; audit `ADVERSE_EVENT_CREATED` / `AMENDED` / `ENTERED_IN_ERROR` without note/code/display/NIK/BPJS/tokens; provenance `subject_type=ADVERSE_EVENT`; PostgreSQL `SELECT FOR UPDATE`; history trigger blocks immutable UPDATE and DELETE; TRUNCATE denied.

## R. Final verdict

**PASS WITH P2**

P0 = 0. P1 = 0. Approved contract deviations = 0. Quality gates pass. Migration chain is valid. Frozen-domain regression passes. Working tree scope is Adverse-Event-only plus required migration, tests, and previously approved Wave 2B.7 design documents. One freeze commit. One annotated tag. Normal push only.

WAVE 2B.7 ADVERSE EVENT = FROZEN  
WAVE 2B.7 ADVERSE EVENT = PUBLISHED  
WAVE 2B.8 = NOT STARTED
