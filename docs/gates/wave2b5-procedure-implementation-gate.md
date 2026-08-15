# Wave 2B.5 — Procedure implementation gate

**Date:** 2026-08-15
**Scope:** Native Procedure only
**Baseline:** `wave-2b4-immunization-frozen` / `20bef7e7a7bc315f6898b508c1de1f237d00abcc` / Alembic `20260814_0013`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Procedure is **not frozen**. Hardening has **not** started.

## In scope

Native Procedure (documented performed or reported procedure fact) on the frozen identity + Encounter + Condition + Observation + Laboratory + Medication + Allergy + Consent + Immunization foundation.

## Out of scope

CarePlan, FHIR Procedure, ordered/planned procedure, performer aggregate, body site, reason/outcome, scheduling, inventory, registry, CDS, AI/RAG, break-glass, patient portal, Consent-as-PDP, and changes to frozen clinical domains.

## Domain model

One explicit table: `procedures`. Category is `PERFORMED` or `REPORTED`. Procedure coding is required (`system` + `code`, optional display). Occurrence and note are optional. No JSON clinical payload. No performer/site/reason/outcome columns.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. `ENTERED_IN_ERROR` is terminal. No-op amend is 409. No revoke. No generic PUT. No DELETE.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind survivor. Write with encounter uses the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone `409`; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Procedure does not mutate encounters.

## Authorization

Procedure-specific permissions only: `clinical.procedure.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar and IDENTITY_OFFICER: none. Purpose is context, not a grant. `Wave1PolicyPDP` is unchanged. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default.

## Purpose

Existing catalog. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not a Procedure decision.

## Provenance

Reuses `clinical_provenances`. Subject type `PROCEDURE`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0014`.

## Audit

Events: `PROCEDURE_CREATED`, `PROCEDURE_AMENDED`, `PROCEDURE_ENTERED_IN_ERROR`. Metadata does not store procedure display, note, NIK, BPJS, secrets, or tokens.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / EIE and amend-versus-EIE covered by tests.

## Database integrity

Additive migration `20260814_0014`. Chain `0001 → 0014`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE/TRUNCATE revoked in `grant_dev_privileges.sql`. `0001`–`0013` unchanged.

## API

`/api/v1/clinical/procedures` with explicit `amend` and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. Sensitive procedure values are redacted from logs and audit metadata.

## Tests

Unit: lifecycle, PDP, logging redaction.

Integration: identity, MERGED, RETIRED, anonymous + EMER + non-EMER, encounter mismatch, cancelled/EIE encounter, cross-org, IDOR, authorization, purpose, lifecycle, no-op amend, EIE, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, facility scope, `app_dml` DELETE/TRUNCATE.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Procedure is present as a persisted fact. CarePlan, FHIR, AI, RAG, CDS, break-glass, and patient-portal tables remain absent. Frozen Immunization remains at `20bef7e`. Procedure is not wired into other clinical getters.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical procedure facts on a merged source are not rewritten. Org-scoped UUID read of clinical resources is unchanged until a later PDP wave. Duplicate procedure facts allowed. Grants remain operational outside Alembic. Performer/site/reason/outcome deferred. Not a compliance certification.

## Checks

Executed 2026-08-15 against the live stack. Procedure is implemented, not hardened, not frozen.

- Identity binding uses `patient_identities.id`
- MERGED new writes without encounter bind survivor; historical rows are not rewritten
- Anonymous procedure requires an EMER encounter
- Create record status is ACTIVE
- ENTERED_IN_ERROR is terminal
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Procedure migration
- `Wave1PolicyPDP` does not consume Procedure or Consent rows
- `ruff check app tests` / `ruff format --check app tests` / `mypy app` passed
- Full pytest: **198 passed**
- Frozen-domain subset (Condition through Immunization): **49 passed**
- Alembic `current == heads == 20260814_0014` (single head; chain `0001 → 0014`)
- `/api/v1/health/live` = 200; `/api/v1/health/ready` = 200 (`postgres`, `redis`, `object_storage` ok)
- Ports remain 9100 / 5433 / 6380 / 9101 / 9002; `OBJECT_STORAGE_ENDPOINT=http://minio:9000`; `gsai-minio` untouched
- No commit, tag, or push
