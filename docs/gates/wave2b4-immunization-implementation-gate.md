# Wave 2B.4 — Immunization implementation gate

**Date:** 2026-08-15
**Scope:** Native Immunization only
**Baseline:** `wave-2b3c-consent-frozen` / `0258a20e5e49f2978fb16091603b5942c745ecda` / Alembic `20260814_0012`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Immunization is **not frozen**. Hardening has **not** started.

## In scope

Native Immunization (documented administered or reported vaccination fact) on the frozen identity + Encounter + Condition + Observation + Laboratory + Medication + Allergy + Consent foundation.

## Out of scope

Procedure, CarePlan, FHIR Immunization, scheduling, forecasting, series, inventory, lot recall, national registry, CDS, AI/RAG, break-glass, patient portal, Consent-as-PDP, and changes to frozen clinical domains.

## Domain model

One explicit table: `immunizations`. Category is `ADMINISTERED` or `REPORTED`. Vaccine coding is required (`system` + `code`, optional display). Occurrence, route, site, and note are optional. No JSON clinical payload. No lot/manufacturer/series columns.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. `ENTERED_IN_ERROR` is terminal. No-op amend is 409. No revoke. No generic PUT. No DELETE.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind survivor. Write with encounter uses the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone `409`; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Immunization does not mutate encounters.

## Authorization

Immunization-specific permissions only: `clinical.immunization.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar and IDENTITY_OFFICER: none. Purpose is context, not a grant. `Wave1PolicyPDP` is unchanged. `clinical.diagnosis.create` and `clinical.procedure.create` remain deny-by-default.

## Purpose

Existing catalog. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not an Immunization decision.

## Provenance

Reuses `clinical_provenances`. Subject type `IMMUNIZATION`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0013`.

## Audit

Events: `IMMUNIZATION_CREATED`, `IMMUNIZATION_AMENDED`, `IMMUNIZATION_ENTERED_IN_ERROR`. Metadata does not store vaccine display, note, NIK, BPJS, secrets, or tokens.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / EIE and amend-versus-EIE covered by tests.

## Database integrity

Additive migration `20260814_0013`. Chain `0001 → 0013`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE/TRUNCATE revoked in `grant_dev_privileges.sql`. `0001`–`0012` unchanged.

## API

`/api/v1/clinical/immunizations` with explicit `amend` and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. Sensitive immunization values are redacted from logs and audit metadata.

## Tests

Unit: lifecycle, PDP, logging redaction.

Integration: identity, MERGED, RETIRED, anonymous + EMER, encounter mismatch, cancelled/EIE encounter, cross-org, IDOR, authorization, purpose, lifecycle, no-op amend, EIE, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, facility scope, `app_dml` DELETE/TRUNCATE.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Immunization is present as a persisted fact. Procedure, CarePlan, FHIR, AI, RAG, CDS, break-glass, and patient-portal tables remain absent. Frozen Consent remains at `0258a20`. Immunization is not wired into other clinical getters.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical immunization facts on a merged source are not rewritten. Org-scoped UUID read of clinical resources is unchanged until a later PDP wave. Duplicate immunization facts allowed. Grants remain operational outside Alembic. Not a compliance certification.

## Checks

Executed 2026-08-15 against the live stack. Immunization is implemented, not hardened, not frozen.

- Identity binding uses `patient_identities.id`
- MERGED new writes without encounter bind survivor; historical rows are not rewritten
- Anonymous immunization requires an EMER encounter
- Create record status is ACTIVE
- ENTERED_IN_ERROR is terminal
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Immunization migration
- `Wave1PolicyPDP` does not consume Immunization or Consent rows
- `ruff check` / `ruff format --check` / `mypy app` passed
- Full pytest: **187 passed**
- Alembic `current == heads == 20260814_0013` (single head)
- `/api/v1/health/live` = 200; `/api/v1/health/ready` = 200 (`postgres`, `redis`, `object_storage` ok)
- Ports remain 9100 / 5433 / 6380 / 9101 / 9002; `OBJECT_STORAGE_ENDPOINT=http://minio:9000`; `gsai-minio` untouched
- No commit, tag, or push
