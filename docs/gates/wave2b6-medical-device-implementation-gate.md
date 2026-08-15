# Wave 2B.6 — Medical Device implementation gate

**Date:** 2026-08-15
**Scope:** Native Medical Device only
**Baseline:** `wave-2b5-procedure-frozen` / `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad` / Alembic `20260814_0014`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Medical Device is **not frozen**. Hardening has **not** started.

## In scope

Native Medical Device (documented patient-device association) on the frozen identity + Encounter + Condition + Observation + Laboratory + Medication + Allergy + Consent + Immunization + Procedure foundation.

## Out of scope

Patient History, Adverse Event, VitalSign tables, CarePlan, FHIR Device, inventory/asset/recall/maintenance, scheduling, registry, CDS, AI/RAG, break-glass, patient portal, Consent-as-PDP, UDI/serial/manufacturer/lot, Procedure FK, performer/site/reason/outcome, and changes to frozen clinical domains.

## Domain model

One explicit table: `medical_devices`. Category is `DOCUMENTED` or `REPORTED`. Device coding is required (`system` + `code`, optional display). Association status is `IN_USE` or `NO_LONGER_USED`. Occurrence and note are optional. No JSON clinical payload. No inventory columns.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. `ENTERED_IN_ERROR` is terminal. No-op amend is 409. No revoke. No generic PUT. No DELETE. `NO_LONGER_USED` is association, not Medication `STOPPED`.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind survivor. Write with encounter uses the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone `409`; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Medical Device does not mutate encounters.

## Authorization

Medical-device-specific permissions only: `clinical.medical_device.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar and IDENTITY_OFFICER: none. Purpose is context, not a grant. `Wave1PolicyPDP` is unchanged. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default.

## Purpose

Existing catalog. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not a Medical Device decision.

## Provenance

Reuses `clinical_provenances`. Subject type `MEDICAL_DEVICE`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0015`.

## Audit

Events: `MEDICAL_DEVICE_CREATED`, `MEDICAL_DEVICE_AMENDED`, `MEDICAL_DEVICE_ENTERED_IN_ERROR`. Metadata does not store device display, note, NIK, BPJS, secrets, or tokens.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / EIE and amend-versus-EIE covered by tests.

## Database integrity

Additive migration `20260814_0015`. Chain `0001 → 0015`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE/TRUNCATE revoked in `grant_dev_privileges.sql`. `0001`–`0014` unchanged.

## API

`/api/v1/clinical/medical-devices` with explicit `amend` and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. Sensitive device values are redacted from logs and audit metadata.

## Tests

Unit: lifecycle, PDP, logging redaction.

Integration: identity, MERGED, RETIRED, anonymous + EMER + non-EMER, encounter mismatch, cancelled/EIE encounter, cross-org, IDOR, authorization, purpose, lifecycle, no-op amend, EIE, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, facility scope, `app_dml` DELETE/TRUNCATE, CHECK constraints.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Medical Device is present as a persisted fact. Patient History, Adverse Event, VitalSign tables, CarePlan, FHIR, AI, RAG, CDS, break-glass, and patient-portal tables remain absent. Frozen Procedure remains at `0a61ee6`. Medical Device is not wired into other clinical getters.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical medical-device facts on a merged source are not rewritten. Org-scoped UUID read of clinical resources is unchanged until a later PDP wave. Duplicate device-association facts allowed. Grants remain operational outside Alembic. UDI/serial/manufacturer/lot and Procedure FK deferred. Not a compliance certification.

## Checks

Executed 2026-08-15 against the live stack. Medical Device is implemented, not hardened, not frozen.

- Identity binding uses `patient_identities.id`
- MERGED new writes without encounter bind survivor; historical rows are not rewritten
- Anonymous medical device requires an EMER encounter
- Create record status is ACTIVE
- ENTERED_IN_ERROR is terminal
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Medical Device migration
- `Wave1PolicyPDP` does not consume Medical Device or Consent rows
- `ruff check app tests` / `ruff format --check app tests` / `mypy app` passed
- Full pytest: **210 passed**, 1 skipped
- Frozen-domain subset (Condition through Procedure): **55 passed**
- Alembic `current == heads == 20260814_0015` (single head; chain `0001 → 0015`)
- `/api/v1/health/live` = 200; `/api/v1/health/ready` = 200 (`postgres`, `redis`, `object_storage` ok)
- Ports remain 9100 / 5433 / 6380 / 9101 / 9002; `OBJECT_STORAGE_ENDPOINT=http://minio:9000`; `gsai-minio` untouched
- No commit, tag, or push
