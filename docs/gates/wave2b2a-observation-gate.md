# Wave 2B.2a — Observation implementation gate

**Date:** 2026-08-14
**Scope:** Native Observation only
**Baseline:** `wave-2b1-condition-frozen` / `e0a716b1d8a18a5c98d8bb592ac62af11c71c701` / Alembic `20260814_0007`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Observation is **not frozen**.

## In scope

Native Observation measurements/findings on the frozen identity + Encounter + Condition foundation.

## Out of scope

Laboratory, medication, allergy, consent, FHIR, AI/RAG, CDS, terminology servers. Wave 2B.2b is not started.

## Checks

- Identity binding uses `patient_identities.id`
- MERGED new writes bind survivor; historical rows are not rewritten
- Anonymous Observation requires an EMER encounter
- Create is FINAL; amend and entered-in-error are explicit operations
- No DELETE API; database DELETE is blocked
- `provenance_id` FK `ON DELETE RESTRICT` from the first Observation migration
- Alembic head `20260814_0008`
- Historical migrations `0001`–`0007` unchanged
