# Wave 2B.8 — Family History domain approval gate

**Status:** APPROVED FOR FAMILY HISTORY
**Date:** 2026-08-16
**Kind:** Design only
**Baseline:** `wave-2b7-adverse-event-frozen` / `8d455b3dede07b9ada00205ff6c49b41b97a0895`
**Alembic:** `current == heads == 20260814_0016`
**Implementation:** NOT STARTED
**Git commit / tag this gate:** none

DESIGN ONLY  
NO CODE  
NO MIGRATION  
NO API IMPLEMENTATION  
NO COMMIT  
NO TAG  
NO PUSH

Companion contract: [docs/clinical/wave2b8-family-history-domain-approval.md](../clinical/wave2b8-family-history-domain-approval.md)

Prior discovery: [docs/gates/wave2b8-architecture-review.md](wave2b8-architecture-review.md) (`WAVE 2B.8 = NOT DEFINED`)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## Decision

Native Family History is approved as Wave 2B.8 **design**. It is a documented patient-associated family-history fact: one controlled relationship plus one coded condition/finding. It is not FHIR FamilyMemberHistory, not Patient History, not a clinical timeline, not CarePlan, not Diagnosis, not Condition redesign, not Observation redesign, not Consent-as-PDP, and not CDS.

The prior discovery pass left Wave 2B.8 undefined because no named, non-forbidden fact had an implementation-ready contract. This gate is the explicit product/architecture selection that pass required. Approval rests on pattern fit with frozen Immunization / Procedure / Medical Device / Adverse Event plus absence of `family_histories` from `FORBIDDEN_TABLES`, not on a deny-by-default stub.

## Inspected sources

- Frozen baseline `8d455b3dede07b9ada00205ff6c49b41b97a0895` / `wave-2b7-adverse-event-frozen`
- `docs/architecture/modular-monolith.md` — ends at Adverse Event; no 2B.8 module
- `docs/development/migrations.md` — ends at `0016`
- `docs/gates/wave2b7-adverse-event-final-freeze.md` — `WAVE 2B.8: NOT STARTED`
- `docs/gates/wave2b8-architecture-review.md` — prior discovery: NOT DEFINED; Family History class F
- Wave 2B.5 Procedure, Wave 2B.6 Medical Device, Wave 2B.7 Adverse Event approval contracts
- clinical models, services, repositories, lifecycle, schemas, catalog, logging, provenance, `Wave1PolicyPDP`
- `FORBIDDEN_TABLES` (no `family_histories`; `vital_signs`, `care_plans`, `diagnoses`, `patient_histories` is an absence probe not a forbidden-table entry)
- deny-by-default stubs `clinical.care_plan.create` and `clinical.diagnosis.create`

## Approval criteria

| Criterion | Result |
|---|---|
| One native clinical fact | Pass — one table `family_histories` |
| Does not redesign frozen domains | Pass — no FKs onto Condition/Observation/Adverse Event |
| Not a new aggregate | Pass — no relative master table, no Patient History table |
| Fits Immunization / Procedure / Medical Device / Adverse Event | Pass — same lifecycle, identity, encounter, provenance, FOR UPDATE |
| Complete implementation contract | Pass — 18 critical decisions closed |
| Additive migration only | Pass — proposed `0017` revising `0016` (not written) |
| `/api/v1/clinical` only | Pass |
| No FHIR / Consent-as-PDP / AI / RAG / CDS | Pass |

## Contract summary

| Topic | Approval |
|---|---|
| Table | `family_histories` only; proposed `0017` (not written) |
| One row | patient + relationship + coded finding |
| Relationship | `PARENT` \| `SIBLING` \| `CHILD` \| `GRANDPARENT` \| `GRANDCHILD` \| `AUNT_UNCLE` \| `COUSIN` \| `OTHER`; immutable |
| Category | `DOCUMENTED` \| `REPORTED` |
| Code | `system` + `code` + optional display; not a Condition FK |
| Record lifecycle | `ACTIVE` → `AMENDED` / `ENTERED_IN_ERROR` |
| Identity | frozen MPI rules; anonymous = Immunization (standalone 409; EMER allowed) |
| Encounter | optional; never mutated |
| Note | optional `note_text`; redacted; not audited |
| Version | +1 on amend; unchanged on EIE |
| Authz | `clinical.family_history.create\|read\|update\|entered_in_error` |
| Purpose | existing `X-Purpose` |
| Audit | `FAMILY_HISTORY_CREATED` / `AMENDED` / `ENTERED_IN_ERROR` |
| Provenance | `subject_type=FAMILY_HISTORY`; insert-only; RESTRICT |
| API | `/api/v1/clinical/family-histories` + amend + EIE; PUT/PATCH/DELETE 405 |
| Concurrency | `SELECT FOR UPDATE`; Redis is not a lock |

## Must not start in implementation

FHIR FamilyMemberHistory, `/fhir/`, `/api/v2/`, Patient History table, pedigree/relative MPI, CarePlan, Diagnosis, VitalSign tables, Condition FK, AI/RAG/CDS, genetic-risk scoring, Consent-as-PDP, break-glass, patient portal, frozen-domain redesign, rewrite of `0001`–`0016`, `Wave1PolicyPDP` rewrite.

## Residuals carried forward

Inherited P2/P3: DENIED-audit rollback; historical identity non-rewrite; org-scoped UUID read; `app_dml` grants outside Alembic; nullable `provenance_id`; duplicate facts. Wave-specific P3: relative identity / deceased / age-at-onset deferred; `OTHER` residual kinship. None blocks this design approval.

## Verdict

**WAVE 2B.8 NATIVE FAMILY HISTORY = APPROVED FOR DESIGN ONLY**

Design only. No code. No migration. No commit. No tag. No push.
