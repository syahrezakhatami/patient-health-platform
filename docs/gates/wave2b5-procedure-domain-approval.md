# Wave 2B.5 — Procedure domain approval gate

**Status:** APPROVED FOR PROCEDURE
**Date:** 2026-08-15
**Kind:** Design only
**Baseline:** `wave-2b4-immunization-frozen` / `20bef7e7a7bc315f6898b508c1de1f237d00abcc`
**Alembic:** `current == heads == 20260814_0013`
**Implementation:** NOT STARTED
**Git commit / tag this gate:** none

Companion contract: [docs/clinical/wave2b5-procedure-domain-approval.md](../clinical/wave2b5-procedure-domain-approval.md)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## Decision

Native Procedure is approved as Wave 2B.5 **design**. It is a documented performed-or-reported procedure fact. It is not FHIR Procedure, not an order, not CarePlan, not Consent-as-PDP, and not CDS.

## Inspected sources

- `docs/architecture/modular-monolith.md` — ends at Immunization; no 2B.5 module
- `docs/development/migrations.md` — ends at `0013`
- `docs/gates/wave2b4-immunization-final-freeze.md` — `WAVE 2B.5: NOT STARTED`
- `docs/clinical/wave2b4-immunization.md` and Allergy / Medication / Consent / Condition / Observation / Laboratory clinical docs
- clinical models, services, repositories, lifecycle, schemas, catalog, logging, provenance, `Wave1PolicyPDP`
- `FORBIDDEN_TABLES` (`care_plans` forbidden; `procedures` not listed)
- deny-by-default stub `clinical.procedure.create`

## Contract summary

| Topic | Approval |
|---|---|
| Table | `procedures` only; proposed `0014` (not written) |
| Category | `PERFORMED` \| `REPORTED` |
| Code | `system` + `code` + optional display |
| Lifecycle | `ACTIVE` → `AMENDED` / `ENTERED_IN_ERROR` |
| Deferred statuses | PLANNED, IN_PROGRESS, COMPLETED, STOPPED, CANCELLED, REVOKED, EXPIRED |
| Identity | frozen MPI rules; anonymous = Immunization (standalone 409; EMER allowed) |
| Encounter | optional; never mutated |
| Performer / site / reason / outcome | deferred |
| Note | optional `note_text`; redacted; not audited |
| Version | +1 on amend; unchanged on EIE |
| Authz | `clinical.procedure.create\|read\|update\|entered_in_error` |
| Purpose | existing `X-Purpose` |
| Audit | `PROCEDURE_CREATED` / `AMENDED` / `ENTERED_IN_ERROR` |
| Provenance | `subject_type=PROCEDURE`; insert-only; RESTRICT |
| API | `/api/v1/clinical/procedures` + amend + EIE; PUT/PATCH/DELETE 405 |
| Concurrency | `SELECT FOR UPDATE`; Redis is not a lock |

## Must not start in implementation

FHIR Procedure, `/fhir/`, `/api/v2/`, CarePlan, Consent-as-PDP, `Wave1PolicyPDP` rewrite, AI/RAG/CDS, break-glass, patient portal, scheduling, inventory, registry, performer aggregate, anatomy catalog, frozen-domain redesign, rewrite of `0001`–`0013`.

## Residuals carried forward

Inherited P2/P3: DENIED-audit rollback; historical identity non-rewrite; org-scoped UUID read; `app_dml` grants outside Alembic; nullable `provenance_id`; duplicate facts. None blocks this design approval.

## Verdict

**WAVE 2B.5 = APPROVED FOR PROCEDURE**

Design only. No code. No migration. No commit. No tag. No push.
