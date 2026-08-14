# Wave 2B.3a — Medication implementation gate

**Date:** 2026-08-14
**Scope:** Native Medication only
**Baseline:** `wave-2b2b-laboratory-frozen` / `7ddd87ca33833d9298a9cd80c91fa847484fa027` / Alembic `20260814_0009`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Medication is **not frozen**. Hardening has **not** started. Allergy and Consent have **not** started.

## In scope

Native Medication (prescribed or reported medication fact) on the frozen identity + Encounter + Condition + Observation + Laboratory foundation.

## Out of scope

Allergy, consent, FHIR MedicationRequest / MedicationAdministration, medication administration/dispense/inventory, AI/RAG, CDS, terminology servers. Wave 2B.3b and 2B.3c are not started. Medication hardening is not started.

## Domain model

One explicit table: `medications`. Terminology stub only (`system` + `code` + optional `display`). Dose is structured (`dose_numeric` + `dose_unit` together or neither). Route is an optional enum. Category distinguishes `PRESCRIBED` vs `REPORTED`. Invalid dose shape returns 422. No JSON clinical payload. No shared mutable lifecycle with Laboratory or Observation beyond reused identity/PDP/provenance infrastructure.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE → STOPPED` via `POST .../stop`. `ACTIVE|STOPPED → ENTERED_IN_ERROR` via the dedicated void route. No `COMPLETED`. Terminal `ENTERED_IN_ERROR` is immutable. No-op stop is 409. No generic PUT. No DELETE.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone medication rejected; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional for ACTIVE. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Medication does not mutate encounters.

## Authorization

Medication-specific permissions only: `clinical.medication.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar: none. Purpose is context, not a grant. Unknown permissions remain deny-by-default.

## Purpose

Existing catalog plus `TREATMENT`. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not a persisted Consent record.

## Provenance

Reuses `clinical_provenances`. Subject type `MEDICATION`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0010`.

## Audit

Events: `MEDICATION_CREATED`, `MEDICATION_STOPPED`, `MEDICATION_ENTERED_IN_ERROR`. Metadata does not store drug names, doses, NIK, BPJS, secrets, or tokens. Logging redacts dose fields and `code_display`.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent stop / double EIE covered by tests: one 200, one 409, one matching success audit.

## Database integrity

Additive migration `20260814_0010`. Chain `0001 → 0010`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE revoked in `grant_dev_privileges.sql`. `0001`–`0009` unchanged.

## API

`/api/v1/clinical/medications` with explicit `stop` and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. SQLAlchemy errors are not leaked. Sensitive medication values are redacted from logs.

## Tests

Unit: lifecycle, dose shape, PDP, logging redaction.

Integration: identity, MERGED, RETIRED, anonymous/EMER, encounter mismatch, cross-org, IDOR, authorization, purpose, lifecycle, no-op stop, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, `app_dml` DELETE.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Medication is present. Allergy, consent, FHIR, AI, RAG, CDS remain absent.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical medication facts on a merged source are not rewritten. Org-scoped UUID read until Consent. Duplicate medication facts allowed. Grants remain operational outside Alembic. Not a compliance certification.

## Checks

- Identity binding uses `patient_identities.id`
- MERGED new writes bind survivor; historical rows are not rewritten
- Anonymous medication requires an EMER encounter
- Create status is ACTIVE
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Medication migration
- Alembic head `20260814_0010`
- Historical migrations `0001`–`0009` unchanged
- Quality: `ruff check` / `ruff format --check` / `mypy` pass; **152 pytest passed**
- Live `/api/v1/health/live` and `/api/v1/health/ready` return 200
- `gsai-minio` / Compose `minio` was not restarted
- No commit, tag, or push in this pass
