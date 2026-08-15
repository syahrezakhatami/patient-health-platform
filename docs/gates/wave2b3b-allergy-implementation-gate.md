# Wave 2B.3b — Allergy implementation gate

**Date:** 2026-08-15
**Scope:** Native Allergy only
**Baseline:** `wave-2b3a-medication-frozen` / `abb6d7a238a139608d645c7e916e3182dd5ecaa9` / Alembic `20260814_0010`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Allergy is **not frozen**. Hardening has **not** started. Consent has **not** started.

## In scope

Native Allergy (documented allergy/intolerance fact) on the frozen identity + Encounter + Condition + Observation + Laboratory + Medication foundation.

## Out of scope

Consent, FHIR AllergyIntolerance, CDS, AI/RAG, medication changes, allergy desensitization. Wave 2B.3c is not started. Allergy hardening is not started.

## Domain model

One explicit table: `allergies`. Terminology stub only (`system` + `code` + optional `display`). Category is allergen class. Clinical and verification statuses are structured columns. Reaction is an optional coded pair. Invalid reaction shape returns 422. No JSON clinical payload.

## Lifecycle

Create is always record `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. No `COMPLETED`. Terminal `ENTERED_IN_ERROR` is immutable. No-op amend is 409. No generic PUT. No DELETE.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone allergy rejected; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional for ACTIVE. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Allergy does not mutate encounters.

## Authorization

Allergy-specific permissions only: `clinical.allergy.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar: none. Purpose is context, not a grant. Unknown permissions remain deny-by-default.

## Purpose

Existing catalog plus `TREATMENT`. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not a persisted Consent record.

## Provenance

Reuses `clinical_provenances`. Subject type `ALLERGY`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0011`.

## Audit

Events: `ALLERGY_CREATED`, `ALLERGY_AMENDED`, `ALLERGY_ENTERED_IN_ERROR`. Metadata does not store allergen names, reaction details, NIK, BPJS, secrets, or tokens. Logging redacts allergen display, reaction fields, severity, and criticality.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / double EIE / amend versus EIE covered by tests.

## Database integrity

Additive migration `20260814_0011`. Chain `0001 → 0011`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE revoked in `grant_dev_privileges.sql`. `0001`–`0010` unchanged.

## API

`/api/v1/clinical/allergies` with explicit `amend` and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. SQLAlchemy errors are not leaked. Sensitive allergy values are redacted from logs.

## Tests

Unit: lifecycle, reaction shape, PDP, logging redaction.

Integration: identity, MERGED, RETIRED, anonymous/EMER, encounter mismatch, cancelled/EIE encounter, cross-org, IDOR, authorization, purpose, lifecycle, no-op amend, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, facility scope, `app_dml` DELETE.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Allergy is present. Consent, FHIR, AI, RAG, CDS remain absent. Medication remains frozen at `abb6d7a`.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical allergy facts on a merged source are not rewritten. Org-scoped UUID read until Consent. Duplicate allergy facts allowed. Grants remain operational outside Alembic. Not a compliance certification.

## Checks

- Identity binding uses `patient_identities.id`
- MERGED new writes bind survivor; historical rows are not rewritten
- Anonymous allergy requires an EMER encounter
- Create record status is ACTIVE
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Allergy migration
- Alembic head `20260814_0011`
- Historical migrations `0001`–`0010` unchanged
- Quality: `ruff check` / `ruff format --check` / `mypy` pass; **164 pytest passed**
- Live `/api/v1/health/live` and `/api/v1/health/ready` return 200
- `gsai-minio` / Compose `minio` was not restarted
- No commit, tag, or push in this pass
