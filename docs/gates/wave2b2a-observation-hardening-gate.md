# Wave 2B.2a — Observation production hardening gate

**Status:** PASS WITH P2
**Date:** 2026-08-14
**Frozen Wave 2B.1:** `wave-2b1-condition-frozen` / `e0a716b1d8a18a5c98d8bb592ac62af11c71c701`
**Frozen Alembic:** `20260814_0007`
**Observation Alembic:** `20260814_0008`
**Wave 2B.2b:** NOT STARTED
**Observation freeze:** NOT issued
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Baseline

| Item | Live value |
|---|---|
| Branch | `main` (tracks `origin/main`, 0 ahead / 0 behind) |
| HEAD | `e0a716b1d8a18a5c98d8bb592ac62af11c71c701` = `wave-2b1-condition-frozen` |
| Working tree | Dirty / untracked Observation implementation + this hardening pass |
| Remote | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Alembic | `current == heads == 20260814_0008` (single head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008` |
| Migrations `0001`–`0007` | Untouched |
| Ports | API `9100`, Postgres `5433`, Redis `6380`, EMR MinIO `9101` / `9002` |
| Backend → MinIO | `http://minio:9000` |
| `gsai-minio` | Untouched |

## 2. Files inspected

Observation path: `observation_values.py`, `application/services.py`, `domain/enums.py`, `domain/lifecycle.py`, `infrastructure/models.py`, `infrastructure/repositories.py`, `api/v1/clinical.py`, `api/v1/schemas.py`, authorization catalog / PDP / purpose / `authorize.py`, `core/logging.py`, Alembic `0008`, `grant_dev_privileges.sql`, live PostgreSQL constraints / grants / triggers, Docker Compose runtime, Wave 1.5 / 2A / 2B.1 / 2B.2a tests. MPI modules were not modified.

## 3. Files changed (this hardening gate)

- `backend/app/core/logging.py` — redact coded/boolean Observation value keys
- `backend/tests/unit/test_wave2b2a_observation_domain.py` — coded-value redaction assertions
- `backend/tests/integration/test_wave2b2a_hardening.py` — concurrency, encounter, authz, purpose, IDOR, facility, provenance, `app_dml`
- `docs/clinical/wave2b2a-observation.md` — residual org-scoped read / grants notes
- `docs/gates/wave2b2a-observation-hardening-gate.md` — this report

No new migration. `0001`–`0008` were not rewritten. No commit, tag, or push.

## 4. Schema

Live `observations`: UUID PK; FKs to patient, encounter, organization, facility, provenance all `ON DELETE RESTRICT`; CHECKs for category, status, value type, value shape, reference range, version ≥ 1, non-empty code/system. Trigger `trg_observations_history_immutable`. `clinical_provenances.subject_type` includes `OBSERVATION`. `app_dml`: INSERT/SELECT/UPDATE, no DELETE.

## 5. Lifecycle

Create → `FINAL`. `FINAL → AMENDED` via amend (no-op 409). `FINAL|AMENDED → ENTERED_IN_ERROR`. EIE is terminal. No draft. No generic status route. No DELETE.

## 6. Identity

ACTIVE allowed. MERGED new writes bind survivor. RETIRED 409. Unknown/cross-org 404. Anonymous standalone 409; EMER encounter allowed. Historical `patient_identity_id` is not rewritten and is SQL-immutable.

## 7. Encounter binding

Optional for ACTIVE. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected (409). Cross-org encounter 404. Observation does not mutate encounters.

## 8. Authorization

Permissions: `clinical.observation.create|read|update|entered_in_error`. CLINICIAN/PLATFORM_ADMIN: all. ORG_ADMIN/AUDITOR: read. Registrar: 403 even with `TREATMENT`. `clinical.laboratory.create` deny-by-default. Facility-bound membership: in-scope 200, out-of-scope 403.

## 9. Purpose

`X-Purpose` required (422 missing/unknown). Normalized with the Wave 1.5 catalog plus `TREATMENT`. Purpose does not grant authorization.

## 10–15. Immutability / concurrency / audit / provenance / DELETE

Mutations use `SELECT FOR UPDATE`. Concurrent identical amend and concurrent EIE: one 200, one 409, one matching audit. Concurrent amend vs EIE: final status always `ENTERED_IN_ERROR`, one EIE audit, version 1 or 2. Audit events do not store measured values. Provenance is insert-only, `subject_type=OBSERVATION`, FK `ON DELETE RESTRICT`. API DELETE 405. Trigger and `app_dml` block DELETE.

## 16. Docker runtime

`/api/v1/health/live` alive. `/api/v1/health/ready` postgres/redis/object_storage ok. Ports unchanged.

## 17. Quality gates

ruff check/format PASS. mypy PASS (104 app files). pytest **130 passed**.

## 18. Clinical boundary

Observation present. Laboratory, medication, allergy, consent, FHIR, AI, RAG, CDS absent.

## 19–22. Findings / residual risks / scorecard

| Sev | Finding | Action |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Inherited Wave 1; not redesigned |
| P2 | Historical `patient_identity_id` not rewritten after MPI merge | Documented; by design |
| P2 | Same-org UUID read is org-scoped until Consent | Documented; not a new ACL |
| P2 | Coded Observation log keys were incomplete | Closed: allowlist extended |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | Inherited operational note |
| P3 | No uniqueness on duplicate vitals | Allowed in this slice |

**Verdict: PASS WITH P2**
