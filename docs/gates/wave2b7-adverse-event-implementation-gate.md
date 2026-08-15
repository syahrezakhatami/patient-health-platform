# Wave 2B.7 — Adverse Event implementation gate

**Date:** 2026-08-16
**Scope:** Native Adverse Event only
**Baseline:** `wave-2b6-medical-device-frozen` / `fdcd24b19d9797034d89b6928c37dc6c47ffe863` / Alembic `20260814_0015`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Adverse Event is **not frozen**. Hardening has **not** started.

## In scope

Native Adverse Event (documented coded adverse event) on the frozen identity + Encounter + Condition + Observation + Laboratory + Medication + Allergy + Consent + Immunization + Procedure + Medical Device foundation.

## Out of scope

Causality, outcome, `LIFE_THREATENING`, pharmacovigilance, incident/notification/reporting/regulatory workflow, Patient History, VitalSign tables, CarePlan, FHIR AdverseEvent, AI/RAG/CDS, scheduling, inventory, and changes to frozen clinical domains.

## Domain model

One explicit table: `adverse_events`. Category is `DOCUMENTED` or `REPORTED`. Event coding is required (`system` + `code`, optional display). Severity is `MILD` | `MODERATE` | `SEVERE`. Occurrence and note are optional. Optional related FKs: at most one of `medication_id` / `medical_device_id` / `procedure_id`. No JSON clinical payload. No causality or outcome columns.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via `POST .../amend`. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. `ENTERED_IN_ERROR` is terminal and does not increment version. No-op amend is 409. No generic PUT. No DELETE.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind survivor. Write with encounter uses the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone `409`; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Adverse Event does not mutate encounters.

## Related facts

Zero or exactly one related Medication / Medical Device / Procedure. More than one is rejected (422 + CHECK). Related ids are immutable. Create requires the related row to exist, same org, same canonical patient, and not EIE. Adverse Event does not mutate related rows. Later EIE of a related row leaves the Adverse Event unchanged.

## Authorization

Adverse-event-specific permissions only: `clinical.adverse_event.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar and IDENTITY_OFFICER: none. Purpose is context, not a grant. `Wave1PolicyPDP` is unchanged. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default.

## Purpose

Existing catalog. Required on protected routes. Invalid purpose 422. Missing purpose 422. `X-Purpose` is not an Adverse Event decision.

## Provenance

Reuses `clinical_provenances`. Subject type `ADVERSE_EVENT`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0016`.

## Audit

Events: `ADVERSE_EVENT_CREATED`, `ADVERSE_EVENT_AMENDED`, `ADVERSE_EVENT_ENTERED_IN_ERROR`. Metadata does not store event display, note, NIK, BPJS, secrets, or tokens.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / EIE and amend-versus-EIE covered by tests.

## Database integrity

Additive migration `20260814_0016`. Chain `0001 → 0016`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE/TRUNCATE revoked in `grant_dev_privileges.sql`. `0001`–`0015` unchanged.

## API

`/api/v1/clinical/adverse-events` with explicit `amend` and `entered-in-error` routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. Sensitive event values are redacted from logs and audit metadata.

## Tests

Unit: lifecycle, PDP, logging redaction, related-fact request validator.

Integration: identity, MERGED, RETIRED, anonymous + EMER + non-EMER, encounter mismatch, cancelled/EIE encounter, cross-org, IDOR, authorization, purpose, lifecycle, no-op amend, EIE, immutability, DELETE protection, provenance restrict, audit redaction, concurrency, facility scope, `app_dml` DELETE/TRUNCATE, CHECK constraints, related-fact combinations.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. Compose object storage remains `http://minio:9000`. `gsai-minio` was not modified.

## Clinical boundary

Adverse Event is present as a persisted fact. Patient History, VitalSign tables, CarePlan, FHIR, AI, RAG, CDS, pharmacovigilance, and incident-management tables remain absent. Frozen Medical Device remains at `fdcd24b`. Adverse Event is not wired into other clinical getters beyond optional read-only related-fact checks at create.

## Contract note (severity)

The approved design contract makes `severity` **amendable** until EIE (Allergy analog). The implementation prompt also listed `severity` under immutable fields. This implementation follows the approved design: category/code/related FKs are immutable; `severity` is amendable. No extra amendable fields were invented.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical adverse-event facts on a merged source are not rewritten. Org-scoped UUID read of clinical resources is unchanged until a later PDP wave. Duplicate adverse-event facts allowed. Grants remain operational outside Alembic. Causality, outcome, and `LIFE_THREATENING` deferred. Not a compliance certification.

## Checks

Executed 2026-08-16 against the live stack. Adverse Event is implemented, not hardened, not frozen.

- Identity binding uses `patient_identities.id`
- MERGED new writes without encounter bind survivor; historical rows are not rewritten
- Anonymous adverse event requires an EMER encounter
- Create record status is ACTIVE
- ENTERED_IN_ERROR is terminal and does not increment version
- Related-fact invariant: none or exactly one of medication / device / procedure
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Adverse Event migration
- `ruff check app tests` / `ruff format --check app tests` / `mypy app` passed
- Full pytest: **227 passed**
- Frozen-domain subset (Condition through Medical Device integration files): **34 passed**
- Alembic `current == heads == 20260814_0016` (single head; chain `0001 → 0016`)
- `/api/v1/health/live` = 200; `/api/v1/health/ready` = 200 (`postgres`, `redis`, `object_storage` ok)
- Ports remain 9100 / 5433 / 6380 / 9101 / 9002; `OBJECT_STORAGE_ENDPOINT=http://minio:9000`; `gsai-minio` untouched
- Secret scan: no `.env`, private keys, cloud credentials, DB passwords, tokens, runtime volumes, or logs in the working tree
- Live Docker `:9100` image does not expose Adverse Event routes (image lag; same class as Medical Device). Not rebuilt.
- No commit, tag, or push
