# Wave 2B.1 — Condition gate

**Date:** 2026-08-14
**Scope:** Diagnosis / Condition only
**Wave 2A:** remains frozen at `wave-2a-frozen` / `20260814_0005`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## In scope

Encounter diagnosis and problem-list Condition on the frozen Wave 2A clinical foundation.

## Out of scope

Observation, laboratory, medication, allergy, consent, FHIR APIs, terminology servers, AI/RAG, CDS.

## Checks

- Identity binding uses `patient_identities.id`
- Anonymous problem list rejected; anonymous EMER encounter diagnosis allowed
- MERGED writes bind the survivor; historical rows are not rewritten
- ENTERED_IN_ERROR is immutable at API, service, and database
- No DELETE API; database DELETE is blocked
- Unknown permission `clinical.diagnosis.create` still denies
- Alembic head `20260814_0006`
- Historical migrations `0001`–`0005` unchanged
