# Wave 2B.3c — Consent implementation gate

**Date:** 2026-08-15
**Scope:** Native Consent only
**Baseline:** `wave-2b3b-allergy-frozen` / `21b20b998a7c3ccad41a1273ac4c85101b94144c` / Alembic `20260814_0011`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Consent is **not frozen**. Hardening has **not** started.

## In scope

Native Consent (documented permit/refuse decision) on the frozen identity + Encounter + Condition + Observation + Laboratory + Medication + Allergy foundation.

## Out of scope

FHIR Consent, PDP enforcement, break-glass, patient portal, representative PII, stored `EXPIRED`, new Purpose values, AI/RAG/CDS, and changes to frozen clinical domains.

## Domain model

One explicit table: `consents`. Optional terminology stub. Category, scope, decision, and source are structured columns. Period and note are optional. Invalid period order returns 422. No JSON clinical payload.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → REVOKED` via `POST .../revoke`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. Both `REVOKED` and `ENTERED_IN_ERROR` are terminal. No-op amend is 409. No generic PUT. No DELETE. Effectiveness is computed; `EXPIRED` is not stored.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind the survivor. New writes with encounter use `encounter.patient_identity_id`. RETIRED `409`. Unknown/cross-org `404`. Anonymous writes `409` even with EMER. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Consent does not mutate encounters.

## Authorization

Consent-specific permissions only: `clinical.consent.create|read|update|revoke|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar and IDENTITY_OFFICER: none. Purpose is context, not a grant. `Wave1PolicyPDP` is not a Consent evaluator.

## Purpose

Existing catalog. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not the Consent decision.

## Provenance

Reuses `clinical_provenances`. Subject type `CONSENT`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0012`.

## Audit

Events: `CONSENT_CREATED`, `CONSENT_AMENDED`, `CONSENT_REVOKED`, `CONSENT_ENTERED_IN_ERROR`. Metadata does not store note text, code display, NIK, BPJS, secrets, or tokens.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / revoke / EIE and terminal races covered by tests.

## Database integrity

Additive migration `20260814_0012`. Chain `0001 → 0012`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE/TRUNCATE revoked in `grant_dev_privileges.sql`. `0001`–`0011` unchanged.

## API

`/api/v1/clinical/consents` with explicit `amend`, `revoke`, and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. Sensitive consent values are redacted from logs and audit metadata.

## Tests

Unit: lifecycle, period/effectiveness, code shape, PDP, logging redaction.

Integration: identity, MERGED, RETIRED, anonymous rejection, encounter mismatch, cancelled/EIE encounter, cross-org, IDOR, authorization, purpose, lifecycle, no-op amend, revoke, EIE, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, facility scope, `app_dml` DELETE/TRUNCATE.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Consent is present as a persisted fact. FHIR, AI, RAG, CDS, break-glass, and patient-portal tables remain absent. Frozen Allergy remains at `21b20b9`. Consent is not wired into other clinical getters.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical consent facts on a merged source are not rewritten. Org-scoped UUID read of other clinical domains is unchanged until a later PDP wave. Duplicate consent facts allowed. Grants remain operational outside Alembic. Not a compliance certification.

## Checks

- Identity binding uses `patient_identities.id`
- MERGED new writes without encounter bind survivor; historical rows are not rewritten
- Anonymous consent is rejected even with EMER
- Create record status is ACTIVE
- REVOKED and ENTERED_IN_ERROR are terminal
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Consent migration
- `Wave1PolicyPDP` does not consume Consent rows
