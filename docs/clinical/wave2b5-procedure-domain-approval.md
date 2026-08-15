# Wave 2B.5 — Native Procedure domain approval

**Status:** APPROVED FOR PROCEDURE (DESIGN ONLY)
**Date:** 2026-08-15
**Baseline:** `wave-2b4-immunization-frozen` / `20bef7e7a7bc315f6898b508c1de1f237d00abcc`
**Alembic at approval:** `20260814_0013`
**Implementation:** NOT STARTED

This document is a design contract. It is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize code, migration, commit, tag, or push.

Procedure is a **native documented procedure fact**. It is **not** FHIR Procedure. It is **not** an order, schedule, CarePlan, inventory, or CDS engine.

## Source vs inference

| Kind | Meaning |
|---|---|
| SOURCE | Already true in the frozen repository |
| DECISION | Resolved in this approval using a frozen-domain convention |
| DEFERRED | Explicitly out of this wave |

Nothing below is filled from FHIR Procedure resource semantics.

## A. Domain purpose

**DECISION.** A Procedure row records that a coded procedure was **performed** or **reported as performed**.

It does **not** record:

- an ordered / planned procedure
- an in-progress workflow
- a completed-vs-cancelled work queue
- a care-plan activity

Prescribed/ordered therapy is already Medication (`PRESCRIBED` \| `REPORTED`). Vaccination is already Immunization (`ADMINISTERED` \| `REPORTED`). Procedure is the remaining documented-act fact for a coded clinical procedure that is neither a drug course nor a vaccine.

Smallest slice: one fact, one table, Allergy/Immunization lifecycle. Not two semantics (order + performance).

## B. Table

**DECISION.** Exactly one native table: `procedures`.

Not `care_plans` (FORBIDDEN_TABLES). Not `fhir_procedures`. Not a JSON clinical payload. Not `treatments` (also forbidden).

Proposed additive revision (design only): `20260814_0014` revising `20260814_0013`.

`procedures` is absent today. Wave 2B.4 tests assert that absence as a later-domain boundary. That is not a forbidden-table rule. `FORBIDDEN_TABLES` does not include `procedures`.

## C. Identity

**SOURCE.** Canonical FK `patient_identities.id`.

| Case | Result |
|---|---|
| ACTIVE | accepted |
| MERGED without encounter | bind survivor |
| MERGED with historical encounter | frozen same-patient check; mismatch 409 |
| RETIRED | 409 |
| unknown / cross-org | 404 |
| historical `patient_identity_id` | never rewritten after MPI merge |

**DECISION — anonymous.** Follow Allergy / Medication / Immunization, not Consent.

- standalone anonymous Procedure → 409
- anonymous Procedure requires a documentable `EMER` encounter
- do not store emergency implied consent

## D. Encounter

**DECISION.** Encounter is **optional** for ACTIVE identities (Immunization / Allergy / Medication). Clinical notes remain the only fact that requires an encounter.

If supplied:

- same patient
- same organization
- documentable
- `CANCELLED` → 409
- `ENTERED_IN_ERROR` → 409
- cross-org → 404
- wrong patient/encounter pair → 409

Procedure must never mutate an encounter.

## E. Category / terminology

**DECISION.** Category is a two-value documented-source flag, analogous to Immunization `ADMINISTERED` \| `REPORTED` and Medication `PRESCRIBED` \| `REPORTED`:

- `PERFORMED` — documented as done in this organization
- `REPORTED` — documented as reported (patient, external facility, or other report)

Not FHIR `status`. Not an order state.

Terminology stub (SOURCE pattern from every coded Wave 2B fact):

- required `code_system`
- required `code`
- optional `code_display`

No bound code system in schema. Tests may use a synthetic system. No ICD/SNOMED/CPT server.

## F. Status / lifecycle

**DECISION.** Allergy / Immunization record lifecycle. Not Medication `STOPPED`. Not FHIR `PLANNED` / `IN_PROGRESS` / `COMPLETED` / `CANCELLED`.

| From | To | Route |
|---|---|---|
| (create) | `ACTIVE` | `POST /procedures` |
| `ACTIVE` | `AMENDED` | `POST .../amend` |
| `AMENDED` | `AMENDED` | `POST .../amend` |
| `ACTIVE` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |
| `AMENDED` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |

Rules:

- create is always `ACTIVE`
- amend must change an amendable field; no-op → 409
- `ENTERED_IN_ERROR` is the only terminal status
- reject `AMENDED → ACTIVE`, EIE → anything, double EIE
- no revoke
- no stored `EXPIRED`, `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `STOPPED`, `CANCELLED`
- no generic PUT / PATCH
- DELETE = 405
- a corrected procedure after EIE is a new fact

## G. Immutability

**DECISION** (Immunization column set minus deferred route/site).

**Frozen after create**

- `patient_identity_id`
- `encounter_id`
- `organization_id`
- `facility_id`
- `category`
- `code_system`, `code`, `code_display`
- `recorder_id`
- `recorded_at`
- `provenance_id`

**Amendable until EIE**

- `occurrence_at`
- `note_text`
- `status` → `AMENDED`
- `version` (increment on amend)

`ENTERED_IN_ERROR` freezes the complete row. Enforce at API, service, trigger, and `app_dml`.

## H. Performer

**DEFERRED.** Frozen facts store `recorder_id` (who documented), not a performer aggregate. Encounter already has `encounter_participants`. A Procedure performer table would be a second aggregate.

This wave records authorship only: `recorder_id`. No performer, no practitioner role, no organization-as-performer.

## I. Body site

**DEFERRED.** Immunization `site` is a closed vaccine-site enum. The repository has no procedure anatomy catalog. Inventing one would be a new terminology domain.

No `site` column in this wave.

## J. Reason / outcome

**DEFERRED.** Linking reason to Condition, or storing outcome codes, would couple frozen domains or invent a second coded pair. Immunization has neither.

No reason column. No outcome column. No FK to `conditions`.

## K. Notes

**DECISION.** Optional `note_text` (Text). Amendable until EIE. Never written to audit metadata. Log redaction keys: existing `note` / `note_text`, plus `procedure_note` and `procedure_display` (same pattern as `immunization_note` / `vaccine_display`).

## L. Versioning

**DECISION.** Allergy / Immunization:

- create `version = 1`
- successful amend increments version by exactly 1
- EIE does **not** increment version

## Authorization

**DECISION.** Permission codes (not yet in catalog — design only):

| Permission | Intent |
|---|---|
| `clinical.procedure.create` | Create |
| `clinical.procedure.read` | Read / list by patient |
| `clinical.procedure.update` | Amend |
| `clinical.procedure.entered_in_error` | Void |

| Role | Access |
|---|---|
| CLINICIAN | create, read, update, EIE |
| PLATFORM_ADMIN | full catalog |
| ORG_ADMIN | read |
| AUDITOR | read |
| Registrar | denied, including + `TREATMENT` |
| IDENTITY_OFFICER | denied |

Permission checks only. Consent does not grant access. `Wave1PolicyPDP` untouched. After cataloguing Procedure, the deny-by-default stub must move off `clinical.procedure.create` to a still-absent alias (not a new domain).

## Purpose

**SOURCE.** Existing `X-Purpose`. Required, normalized, catalog-validated, audited. Missing / unknown → 422. Purpose does not grant access. No new purpose values.

## Audit

**DECISION.**

- `PROCEDURE_CREATED`
- `PROCEDURE_AMENDED`
- `PROCEDURE_ENTERED_IN_ERROR`

Allowed metadata: `category`, `status`, `version`, `purpose` (and frozen `old_status` / `new_status` on mutations).

Never: procedure display, procedure code, note, NIK, BPJS, tokens, passwords, secrets, raw payload.

Do not redesign Wave 1 DENIED-audit rollback.

## Provenance

**DECISION.** Reuse `clinical_provenances`. `subject_type = PROCEDURE` (extend the existing CHECK). Insert-only. FK `ON DELETE RESTRICT`. Service always sets `provenance_id`. Column remains nullable (frozen convention).

## Database design (not implemented)

Table `procedures`:

| Column | Null | Notes |
|---|---|---|
| `id` | NO | UUID PK |
| `patient_identity_id` | NO | FK `patient_identities.id` ON DELETE RESTRICT |
| `encounter_id` | YES | FK `encounters.id` ON DELETE RESTRICT |
| `organization_id` | NO | FK `organizations.id` ON DELETE RESTRICT |
| `facility_id` | YES | FK `facilities.id` ON DELETE RESTRICT |
| `category` | NO | CHECK `PERFORMED` \| `REPORTED` |
| `code_system` | NO | CHECK `char_length > 0` |
| `code` | NO | CHECK `char_length > 0` |
| `code_display` | YES | |
| `occurrence_at` | YES | timestamptz |
| `note_text` | YES | |
| `status` | NO | CHECK `ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR` |
| `recorded_at` | NO | timestamptz |
| `recorder_id` | YES | |
| `version` | NO | CHECK `>= 1` |
| `provenance_id` | YES | FK `clinical_provenances.id` ON DELETE RESTRICT |
| `created_at` / `updated_at` | NO | TimestampMixin |

Indexes: `patient_identity_id`, `encounter_id`, `organization_id`, `recorded_at`.

Trigger: `trg_procedures_history_immutable` / `prevent_procedure_history_mutation()` — Immunization-shaped (EIE freezes row; illegal status transitions rejected; DELETE blocked).

`app_dml`: INSERT / SELECT / UPDATE. DELETE / TRUNCATE denied in `grant_dev_privileges.sql` (operational, outside Alembic — inherited).

Do not rewrite `0001`–`0013`.

## API design (not implemented)

Under `/api/v1/clinical/` only:

| Method | Path | Permission |
|---|---|---|
| POST | `/procedures` | `clinical.procedure.create` |
| GET | `/procedures?patient_identity_id=` | `clinical.procedure.read` |
| GET | `/procedures/{id}` | `clinical.procedure.read` |
| POST | `/procedures/{id}/amend` | `clinical.procedure.update` |
| POST | `/procedures/{id}/entered-in-error` | `clinical.procedure.entered_in_error` |

List requires `patient_identity_id`. PUT / PATCH / DELETE = 405. No `/api/v2/`. No `/fhir/`. No FHIR Procedure resource.

## Concurrency

**SOURCE convention.** Mutations use `SELECT FOR UPDATE`. Redis is not a clinical lock.

| Race | Expected |
|---|---|
| amend vs amend | one 200, one 409, one `PROCEDURE_AMENDED` |
| EIE vs EIE | one 200, one 409, one `PROCEDURE_ENTERED_IN_ERROR` |
| amend vs EIE | final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1 |

## Security / leakage

Unauthenticated 401. Unprovisioned JWT 403. Insufficient permission 403. Facility out-of-scope 403. Unknown UUID 404. Cross-org resource 404. Cross-org identity 404. Wrong patient/encounter 409. Invalid purpose 422.

Denied / 404 bodies must not leak procedure code, display, note, patient identifiers, NIK, BPJS, or SQL/ORM details.

## Dependencies

Reuses: MPI identity resolution, optional documentable encounter, organization/facility scope, `clinical_provenances`, existing purpose catalog, permission catalog registration, audit insert, `app_dml` grants, history trigger, `SELECT FOR UPDATE`.

Does **not** require: Consent-as-PDP, FHIR, AI, RAG, CDS, break-glass, patient portal, scheduling, inventory, registry, performer aggregate, anatomy catalog.

## Frozen-domain safety

Implementation, if started later, must not redesign Condition, Observation, Laboratory, Medication, Allergy, Consent, or Immunization. Must not rewrite `0001`–`0013`. Must not modify `Wave1PolicyPDP`. Must not turn Consent into a PDP. Allowed previous-wave edits: catalog registration and deny-by-default stub movement only.

## Risk register

| Sev | Kind | Finding |
|---|---|---|
| P0 | — | None at design time |
| P1 | — | None at design time |
| P2 | Inherited | DENIED-audit rows roll back with `ForbiddenError` |
| P2 | Inherited | Historical `patient_identity_id` is not rewritten after MPI merge |
| P2 | Inherited | Same-org UUID read until a later PDP wave |
| P2 | Procedure | Duplicate procedure facts allowed (same as Immunization) |
| P3 | Inherited | `app_dml` grants live outside Alembic |
| P3 | Inherited | `provenance_id` nullable; service always sets it |
| P3 | Procedure | Performer, site, reason, and outcome are deferred; callers must not infer them |

## Approval

All implementation-critical decisions are resolved. Deferred items are explicit non-scope, not open questions.

```
WAVE 2B.5 = APPROVED FOR PROCEDURE
DESIGN ONLY
```
