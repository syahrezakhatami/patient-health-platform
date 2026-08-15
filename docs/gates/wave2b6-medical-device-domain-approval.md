# Wave 2B.6 — Medical Device domain approval gate

**Status:** APPROVED FOR MEDICAL DEVICE
**Date:** 2026-08-15
**Kind:** Design only
**Baseline:** `wave-2b5-procedure-frozen` / `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad`
**Alembic:** `current == heads == 20260814_0014`
**Implementation:** NOT STARTED
**Git commit / tag this gate:** none

DESIGN ONLY  
NO CODE  
NO MIGRATION  
NO API IMPLEMENTATION  
NO COMMIT  
NO TAG  
NO PUSH

Companion contract: [docs/clinical/wave2b6-medical-device-domain-approval.md](../clinical/wave2b6-medical-device-domain-approval.md)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## Decision

Native Medical Device is approved as Wave 2B.6 **design**. It is a documented patient-associated device fact. It is not FHIR Device, not inventory, not Observation, not Procedure, not Patient History, not Adverse Event, not Consent-as-PDP, and not CDS.

The prior discovery pass left Wave 2B.6 undefined because no named, non-forbidden fact existed in the repository. This gate is the explicit product/architecture selection that pass required. Approval rests on pattern fit with frozen Immunization/Procedure plus absence from `FORBIDDEN_TABLES`, not on a deny-by-default stub.

## Inspected sources

- `docs/architecture/modular-monolith.md` — ends at Procedure; no 2B.6 module
- `docs/development/migrations.md` — ends at `0014`
- `docs/gates/wave2b5-procedure-final-freeze.md` — `WAVE 2B.6: NOT STARTED`
- `docs/gates/wave2b6-architecture-review.md` — prior discovery: NOT DEFINED
- Wave 2B.4 Immunization and Wave 2B.5 Procedure approval/implementation/hardening/freeze documents
- clinical models, services, repositories, lifecycle, schemas, catalog, logging, provenance, `Wave1PolicyPDP`
- `FORBIDDEN_TABLES` (no `medical_devices`; `vital_signs`, `care_plans`, `diagnoses` forbidden)
- deny-by-default stubs `clinical.care_plan.create` and `clinical.diagnosis.create`

## Contract summary

| Topic | Approval |
|---|---|
| Table | `medical_devices` only; proposed `0015` (not written) |
| Category | `DOCUMENTED` \| `REPORTED` |
| Code | `system` + `code` + optional display |
| Record lifecycle | `ACTIVE` → `AMENDED` / `ENTERED_IN_ERROR` |
| Association | amendable `IN_USE` \| `NO_LONGER_USED` (not Medication STOPPED) |
| Deferred statuses | PLANNED, IN_PROGRESS, COMPLETED, STOPPED, CANCELLED, REVOKED, EXPIRED |
| Identity | frozen MPI rules; anonymous = Immunization (standalone 409; EMER allowed) |
| Encounter | optional; never mutated; no FK to Procedure |
| UDI / serial / manufacturer / lot / expiry | deferred |
| Note | optional `note_text`; redacted; not audited |
| Version | +1 on amend; unchanged on EIE |
| Authz | `clinical.medical_device.create\|read\|update\|entered_in_error` |
| Purpose | existing `X-Purpose` |
| Audit | `MEDICAL_DEVICE_CREATED` / `AMENDED` / `ENTERED_IN_ERROR` |
| Provenance | `subject_type=MEDICAL_DEVICE`; insert-only; RESTRICT |
| API | `/api/v1/clinical/medical-devices` + amend + EIE; PUT/PATCH/DELETE 405 |
| Concurrency | `SELECT FOR UPDATE`; Redis is not a lock |

## Must not start in implementation

FHIR Device, `/fhir/`, `/api/v2/`, inventory/asset/recall/maintenance, Patient History, Adverse Event, VitalSign tables, CarePlan, Consent-as-PDP, `Wave1PolicyPDP` rewrite, AI/RAG/CDS, break-glass, patient portal, scheduling, registry, performer/site/reason/outcome, frozen-domain redesign, rewrite of `0001`–`0014`.

## Residuals carried forward

Inherited P2/P3: DENIED-audit rollback; historical identity non-rewrite; org-scoped UUID read; `app_dml` grants outside Alembic; nullable `provenance_id`; duplicate facts. None blocks this design approval.

## Verdict

**WAVE 2B.6 = APPROVED FOR MEDICAL DEVICE**

Design only. No code. No migration. No commit. No tag. No push.
