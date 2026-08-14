# Wave 2B.2b — Laboratory implementation gate

**Date:** 2026-08-14
**Scope:** Native Laboratory only
**Baseline:** `wave-2b2a-observation-frozen` / `32500d1492994154c58c6eb65cade6cf42486d4f` / Alembic `20260814_0008`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Laboratory is **not frozen**. Hardening has **not** started.

## In scope

Native laboratory order, specimen, and result on the frozen identity + Encounter + Condition + Observation foundation.

## Out of scope

Medication, allergy, consent, FHIR, AI/RAG, CDS, terminology servers. Wave 2B.3 is not started. Laboratory hardening is not started.

## Domain model

Three explicit tables: `laboratory_orders`, `laboratory_specimens`, `laboratory_results`. Typed result values. Terminology stub only (`system` + `code` + optional `display`). Reference ranges and units are structured. Invalid value shapes return 422.

## Lifecycle

- Order: `REGISTERED` → `IN_PROGRESS` (first specimen) / `CANCELLED` / `ENTERED_IN_ERROR`. Cancel only from `REGISTERED`. No `COMPLETED`.
- Specimen: create `COLLECTED` → `REJECTED` / `ENTERED_IN_ERROR`.
- Result: create `FINAL` → `AMENDED` / `ENTERED_IN_ERROR`. Value type immutable. No-op amend is 409.

Terminal states are immutable. No generic status endpoint. Transitions use `SELECT FOR UPDATE`.

## Identity behavior

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown/cross-org `404`. Anonymous standalone laboratory rejected; EMER encounter required. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter behavior

Optional for ACTIVE. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Laboratory does not mutate encounters.

## Authorization

Laboratory-specific permissions only. Registrar does not receive them. Purpose is context, not a grant. Unknown permissions remain deny-by-default.

## Purpose

Existing catalog plus `TREATMENT`. Required on protected routes. Invalid purpose 422. Missing purpose 422.

## Provenance

Reuses `clinical_provenances`. Subject types `LABORATORY_ORDER`, `LABORATORY_SPECIMEN`, `LABORATORY_RESULT`. `provenance_id` FK `ON DELETE RESTRICT` from migration `0009` (Condition H4 pattern is not repeated).

## Audit

Explicit `LAB_*` events. Metadata does not store measured values, NIK, BPJS, secrets, or tokens. Logging redacts laboratory value fields.

## Concurrency

PostgreSQL `SELECT FOR UPDATE`. Redis is not authoritative. Concurrent amend / double EIE / amend versus EIE covered by tests.

## Database integrity

Additive migration `20260814_0009`. Chain `0001 → 0009`. Single head. `ON DELETE RESTRICT`. History/DELETE triggers. `app_dml` INSERT/SELECT/UPDATE only; DELETE revoked in `grant_dev_privileges.sql`. `0001`–`0008` unchanged.

## API

`/api/v1/clinical/laboratory/{orders,specimens,results}` with explicit transition routes. No DELETE. No `/api/v2/`. Status codes: 401, 403, 404, 409, 422, 405.

## Security

Authentication, organization scope, facility scope, permission, and purpose validation on protected routes. Cross-org 404 without existence leakage. SQLAlchemy errors are not leaked.

## Clinical boundary

Laboratory is present. Medication, allergy, consent, FHIR, AI, RAG, CDS remain absent.

## Known residual risks

Denial-audit rows still roll back with `ForbiddenError`. Historical laboratory facts on a merged source are not rewritten. Org-scoped UUID read until Consent. Duplicate lab facts allowed. Grants remain operational outside Alembic. Not a compliance certification.

## Checks

- Identity binding uses `patient_identities.id`
- MERGED new writes bind survivor; historical rows are not rewritten
- Anonymous laboratory requires an EMER encounter
- Create statuses are REGISTERED / COLLECTED / FINAL
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Laboratory migration
- Alembic head `20260814_0009`
- Historical migrations `0001`–`0008` unchanged
- Quality: `ruff check` / `ruff format --check` / `mypy` pass; **139 pytest passed**
- Live `/api/v1/health/live` and `/api/v1/health/ready` return 200
- `gsai-minio` / Compose `minio` was not restarted
- No commit, tag, or push in this pass
