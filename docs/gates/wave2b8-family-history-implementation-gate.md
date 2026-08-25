# Wave 2B.8 — Family History implementation gate

**Status:** IMPLEMENTED  
**Hardening:** NOT STARTED  
**Frozen:** NO  
**Date:** 2026-08-25
**Scope:** Native Family History only
**Baseline:** `wave-2b7-adverse-event-frozen` / `8d455b3dede07b9ada00205ff6c49b41b97a0895` / Alembic `20260814_0016`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Family History is **not frozen**. Hardening has **not** started.

## In scope

Native Family History (documented/reported relationship + coded finding) on the frozen identity + Encounter + Condition + Observation + Laboratory + Medication + Allergy + Consent + Immunization + Procedure + Medical Device + Adverse Event foundation.

## Out of scope

Patient History table, pedigree/relative MPI, sex-specific relationship values, deceased/age-at-onset, Condition FK, CarePlan, Diagnosis, VitalSign tables, FHIR FamilyMemberHistory, AI/RAG/CDS, and changes to frozen clinical domains.

## Domain model

One explicit table: `family_histories`. Relationship is `PARENT` | `SIBLING` | `CHILD` | `GRANDPARENT` | `GRANDCHILD` | `AUNT_UNCLE` | `COUSIN` | `OTHER`. Category is `DOCUMENTED` or `REPORTED`. Finding coding is required (`system` + `code`, optional display). Occurrence and note are optional. No JSON clinical payload. No Condition FK.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. `ENTERED_IN_ERROR` is terminal and does not increment version. No-op amend is 409. No generic PUT. No DELETE.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind survivor. Write with encounter uses the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone `409`; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Family History does not mutate encounters.

## Authorization

Family-history-specific permissions only: `clinical.family_history.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar and IDENTITY_OFFICER: none. Purpose is context, not a grant. `Wave1PolicyPDP` is unchanged. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default. Consent does not grant Family History access.

## Purpose

Existing catalog. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not a Family History decision.

## Provenance

Reuses `clinical_provenances`. Subject type `FAMILY_HISTORY`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0017`.

## Audit

Events: `FAMILY_HISTORY_CREATED`, `FAMILY_HISTORY_AMENDED`, `FAMILY_HISTORY_ENTERED_IN_ERROR`. Metadata does not store finding display, code, note, NIK, BPJS, secrets, or tokens.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / EIE and amend-versus-EIE covered by tests.

## Database integrity

Additive migration `20260814_0017`. Chain `0001 → 0017`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE/TRUNCATE revoked in `grant_dev_privileges.sql`. `0001`–`0016` unchanged.

## API

`/api/v1/clinical/family-histories` with explicit `amend` and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. Sensitive finding values are redacted from logs and audit metadata.

## Tests

Unit: lifecycle, PDP, logging redaction, sex-specific relationship rejection.

Integration: identity, MERGED, RETIRED, anonymous + EMER + non-EMER, encounter mismatch, cancelled/EIE encounter, cross-org, IDOR, authorization, consent does not grant, purpose, lifecycle, no-op amend, EIE, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, facility scope, `app_dml` DELETE/TRUNCATE, CHECK constraints, Condition/Patient History/FHIR semantic boundaries.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Family History is present as a persisted fact. Patient History, VitalSign tables, CarePlan, Diagnosis, FHIR, AI, RAG, and CDS remain absent. Frozen Adverse Event remains at `8d455b3`. Family History is not wired into Condition getters.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical family-history facts on a merged source are not rewritten. Org-scoped UUID read of clinical resources is unchanged until a later PDP wave. Duplicate family-history facts allowed. Grants remain operational outside Alembic. Relative identity / deceased / age-at-onset deferred. Not a compliance certification.

## Checks

Executed 2026-08-25 against the live stack. Family History is implemented, not hardened, not frozen.

- Identity binding uses `patient_identities.id`
- MERGED new writes without encounter bind survivor; historical rows are not rewritten
- Anonymous family history requires an EMER encounter
- Create record status is ACTIVE
- ENTERED_IN_ERROR is terminal and does not increment version
- Relationship is immutable; finding is not a Condition FK
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Family History migration
- `ruff check app tests` / `ruff format --check app tests` / `mypy app` passed
- Full pytest: **247 passed**
- Frozen-domain subset (Condition through Adverse Event integration + hardening files): **89 passed**
- Alembic `current == heads == 20260814_0017` (single head; chain `0001 → 0017`)
- `/api/v1/health/live` = 200; `/api/v1/health/ready` = 200 (`postgres`, `redis`, `object_storage` ok)
- Ports remain 9100 / 5433 / 6380 / 9101 / 9002; `OBJECT_STORAGE_ENDPOINT=http://minio:9000`; `gsai-minio` untouched
- Secret scan: no `.env`, private keys, cloud credentials, DB passwords, tokens, runtime volumes, or logs in the working tree
- Live Docker `:9100` image does not expose Family History routes (P3 image lag; same class as Adverse Event). Not rebuilt.
- No commit, tag, or push
