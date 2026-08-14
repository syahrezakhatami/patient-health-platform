# Wave 2A — Clinical foundation gate

**Status:** PASS  
**Date:** 2026-08-14  
**Scope:** Encounter + clinical notes + terminology stub + `CLINICIAN` RBAC  
**Wave 2:** NOT COMPLETE

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## Verdict

Wave 2A foundation is implemented on top of the frozen Wave 1.5 identity baseline. Full Wave 2 (diagnosis, observation, laboratory, medication, FHIR) is not started.

## Quality gates

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` | PASS |
| `mypy` | PASS |
| `pytest` | **93 passed** |
| Alembic head | `20260814_0004` |
| `grant_dev_privileges.sql` | Re-applied after 0004 |
| Live `:9100` health/ready | PASS (postgres, redis, object_storage ok) |
| Live `/api/v1/clinical/` OpenAPI | 7 routes |
| `verify_docker_runtime.py` | 0 failures (Wave 1.5 MPI checks still hold) |

## In scope (shipped)

- `Encounter` as the care episode (`EMER|IMP|AMB|VR|HH`)
- Clinical note as the first authored resource
- Draft / final / entered-in-error
- Terminology stub (`system` + `code` + optional `display`)
- `CLINICIAN` role and `clinical.*` permissions
- Purpose `TREATMENT` (audit context only)
- Routes under `/api/v1/clinical/`

## Out of scope (not shipped)

Diagnosis, condition, observation, laboratory, medication, allergy, immunization, procedure, care plan, consent UI, FHIR APIs, AI/RAG, Kafka, PACS, timeline, documents, microservices.

## Invariants preserved

- Ports unchanged. `gsai-minio` untouched.
- Canonical identity remains `patient_identities.id`.
- Matching is evidence only. No auto-merge.
- Purpose does not grant authorization.
- PDP evaluates permission codes. Role names are never inspected.
- Migrations `0001`, `0002`, and `0003` were not edited.
- No `/api/v2/`.

## Notes

1. No first Git commit.
2. Historical `identity_merge_operations.evidence` object-shaped rows remain by design.
3. Alembic runs as `php_admin`; Docker API uses `app_dml`. Re-run grants after migrate.
4. Docker API was rebuilt from this working tree. Unauthenticated `POST /api/v1/clinical/encounters` returns 401.

## Stop

WAVE 2A CLINICAL FOUNDATION COMPLETE  
WAVE 2 NOT COMPLETE  
Do not start diagnosis, laboratory, medication, FHIR, consent, or AI unless a later wave is explicitly started.
