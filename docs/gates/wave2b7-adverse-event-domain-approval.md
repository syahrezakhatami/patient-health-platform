# Wave 2B.7 — Adverse Event domain approval gate

**Status:** APPROVED FOR ADVERSE EVENT
**Date:** 2026-08-16
**Kind:** Design only
**Baseline:** `wave-2b6-medical-device-frozen` / `fdcd24b19d9797034d89b6928c37dc6c47ffe863`
**Alembic:** `current == heads == 20260814_0015`
**Implementation:** NOT STARTED
**Git commit / tag this gate:** none

DESIGN ONLY  
NO CODE  
NO MIGRATION  
NO API IMPLEMENTATION  
NO COMMIT  
NO TAG  
NO PUSH

Companion contract: [docs/clinical/wave2b7-adverse-event-domain-approval.md](../clinical/wave2b7-adverse-event-domain-approval.md)

Prior discovery: [docs/gates/wave2b7-architecture-review.md](wave2b7-architecture-review.md) (`WAVE 2B.7 = NOT DEFINED`)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## Decision

Native Adverse Event is approved as Wave 2B.7 **design**. It is a documented patient-associated adverse-event fact. It is not FHIR AdverseEvent, not incident management, not pharmacovigilance, not Patient History, not Vital Signs, not CarePlan, not Consent-as-PDP, and not CDS.

The prior discovery pass left Wave 2B.7 undefined because no named, non-forbidden fact had an implementation-ready contract. This gate is the explicit product/architecture selection that pass required. Approval rests on pattern fit with frozen Immunization / Procedure / Medical Device plus absence of `adverse_events` from `FORBIDDEN_TABLES`, not on a deny-by-default stub.

## Inspected sources

- Frozen baseline `fdcd24b19d9797034d89b6928c37dc6c47ffe863` / `wave-2b6-medical-device-frozen`
- `docs/architecture/modular-monolith.md` — ends at Medical Device; no 2B.7 module
- `docs/development/migrations.md` — ends at `0015`
- `docs/gates/wave2b6-medical-device-final-freeze.md` — `WAVE 2B.7: NOT STARTED`
- `docs/gates/wave2b7-architecture-review.md` — prior discovery: NOT DEFINED
- Wave 2B.4 Immunization, Wave 2B.5 Procedure, Wave 2B.6 Medical Device approval/implementation/hardening/freeze documents
- Allergy severity / category conventions
- clinical models, services, repositories, lifecycle, schemas, catalog, logging, provenance, `Wave1PolicyPDP`
- `FORBIDDEN_TABLES` (no `adverse_events`; `vital_signs`, `care_plans`, `diagnoses` forbidden)
- deny-by-default stubs `clinical.care_plan.create` and `clinical.diagnosis.create`

## Approval criteria

| Criterion | Result |
|---|---|
| One native clinical fact | Pass — one table `adverse_events` |
| Does not redesign frozen domains | Pass — optional FKs are additive on AE only |
| Not a new aggregate | Pass — no relationship table, no Patient History |
| Fits Immunization / Procedure / Medical Device | Pass — same lifecycle, identity, encounter, provenance, FOR UPDATE |
| Complete implementation contract | Pass — 18 critical decisions closed |
| Additive migration only | Pass — proposed `0016` revising `0015` (not written) |
| `/api/v1/clinical` only | Pass |
| No FHIR / Consent-as-PDP / AI / RAG / CDS | Pass |

## Contract summary

| Topic | Approval |
|---|---|
| Table | `adverse_events` only; proposed `0016` (not written) |
| Category | `DOCUMENTED` \| `REPORTED` (not MEDICATION/DEVICE/PROCEDURE as category) |
| Code | `system` + `code` + optional display |
| Severity | required `MILD` \| `MODERATE` \| `SEVERE`; `LIFE_THREATENING` deferred |
| Record lifecycle | `ACTIVE` → `AMENDED` / `ENTERED_IN_ERROR` |
| Related facts | optional at most one of `medication_id` / `medical_device_id` / `procedure_id`; immutable; no target-table edits |
| Causality | deferred |
| Outcome | deferred |
| Identity | frozen MPI rules; anonymous = Immunization (standalone 409; EMER allowed) |
| Encounter | optional; never mutated |
| Note | optional `note_text`; redacted; not audited |
| Version | +1 on amend; unchanged on EIE |
| Authz | `clinical.adverse_event.create\|read\|update\|entered_in_error` |
| Purpose | existing `X-Purpose` |
| Audit | `ADVERSE_EVENT_CREATED` / `AMENDED` / `ENTERED_IN_ERROR` |
| Provenance | `subject_type=ADVERSE_EVENT`; insert-only; RESTRICT |
| API | `/api/v1/clinical/adverse-events` + amend + EIE; PUT/PATCH/DELETE 405 |
| Concurrency | `SELECT FOR UPDATE`; Redis is not a lock |

## Must not start in implementation

FHIR AdverseEvent, `/fhir/`, `/api/v2/`, pharmacovigilance platform, AI causality, CDS, RAG, Consent-as-PDP, CarePlan, Diagnosis, VitalSign tables, Patient History aggregate, device recall/inventory, medication inventory, scheduling, notification engine, external reporting, break-glass, patient portal, frozen-domain redesign, rewrite of `0001`–`0015`, `Wave1PolicyPDP` rewrite.

## Residuals carried forward

Inherited P2/P3: DENIED-audit rollback; historical identity non-rewrite; org-scoped UUID read; `app_dml` grants outside Alembic; nullable `provenance_id`; duplicate facts. Wave-specific P3: causality / outcome / `LIFE_THREATENING` deferred. None blocks this design approval.

## Verdict

**WAVE 2B.7 NATIVE ADVERSE EVENT = APPROVED FOR DESIGN ONLY**

Design only. No code. No migration. No commit. No tag. No push.
