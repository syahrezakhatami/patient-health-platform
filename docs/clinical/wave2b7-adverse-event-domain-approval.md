# Wave 2B.7 — Native Adverse Event domain approval

**Status:** APPROVED FOR ADVERSE EVENT (DESIGN ONLY)
**Date:** 2026-08-16
**Baseline:** `wave-2b6-medical-device-frozen` / `fdcd24b19d9797034d89b6928c37dc6c47ffe863`
**Alembic at approval:** `20260814_0015`
**Implementation:** NOT STARTED

DESIGN ONLY  
NO CODE  
NO MIGRATION  
NO API IMPLEMENTATION  
NO COMMIT  
NO TAG  
NO PUSH

This document is a design contract. It is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize code, migration, commit, tag, or push.

Adverse Event is a **native documented clinical adverse-event fact** associated with a patient. It is **not** FHIR AdverseEvent. It is **not** an incident-management system, pharmacovigilance platform, device-recall workflow, Patient History aggregate, Condition replacement, Observation replacement, CarePlan, or CDS.

## Source vs inference

| Kind | Meaning |
|---|---|
| SOURCE | Already true in the frozen repository |
| DECISION | Resolved in this approval using a frozen-domain convention |
| DEFERRED | Explicitly out of this wave — NOT REQUIRED FOR MINIMAL NATIVE FACT |

Nothing below is filled from FHIR AdverseEvent, DetectedIssue, or Flag resource semantics.

The prior Wave 2B.7 discovery pass classified Adverse Event as **F** (undefined). That pass required an explicit product/architecture selection plus a complete frozen-pattern contract. This document is that selection. Approval is justified because the named fact is a single native clinical documentation row, `adverse_events` is absent from `FORBIDDEN_TABLES`, and the fact can reuse Immunization / Procedure / Medical Device conventions without redesigning frozen domains.

## A. Domain name

**DECISION.** Native **Adverse Event**.

Internal identifiers use `adverse_event` / `adverse_events`. Do not name the table `incidents`, `safety_events`, or `fhir_adverse_events`.

## B. Domain purpose

**DECISION.** An Adverse Event row records that a clinician documented a coded adverse event for a patient.

Examples of the fact, not of schema:

- documented anaphylaxis after a recorded medication
- documented fall during an encounter
- documented device-associated harm linked to an existing Medical Device fact
- documented post-procedure complication linked to an existing Procedure fact
- reported adverse event without a linked in-system fact

It does **not** record:

- the underlying allergy/intolerance (Allergy)
- the problem-list diagnosis (Condition)
- a vital-sign measurement (Observation)
- warehouse recall or inventory (out of scope)
- a longitudinal patient history (aggregate; out of scope)

## C. Native fact vs aggregate

**DECISION.** One native documented fact. One table. Not an aggregate family.

Not Laboratory-style coordinated tables. Not CarePlan. Not FHIR AdverseEvent + suspectEntity + contributingFactor. Optional FKs to frozen facts are pointers, not ownership of those facts.

## D. Table name

**DECISION.** Exactly one native table: `adverse_events`.

Not `incidents`. Not `fhir_adverse_events`. Not `vital_signs` (forbidden; Observation already owns measurements). Not `care_plans` (forbidden). Not `patient_histories`. Not a JSON clinical payload.

Proposed additive revision (design only): `20260814_0016` revising `20260814_0015`.

`adverse_events` is absent today. `FORBIDDEN_TABLES` does not include it. Prior hardening tests asserting the table is absent are absence checks, not a forbidden-table rule.

## E. Category model

**DECISION.** Category is a two-value documented-source flag, analogous to Medical Device `DOCUMENTED` \| `REPORTED` and Procedure `PERFORMED` \| `REPORTED`:

- `DOCUMENTED` — recorded as observed or documented in this organization
- `REPORTED` — documented as reported (patient, external facility, or other report)

**Rejected** as category values: `MEDICATION`, `MEDICAL_DEVICE`, `PROCEDURE`, `OTHER`.

Those names describe a suspected related-domain type, not how the fact was recorded. Repository category conventions are either documentation source (Immunization / Procedure / Medical Device) or allergen class on Allergy (the allergen itself, not an FK to Medication). Using related-domain names as category would duplicate optional FKs, force an `OTHER` junk drawer when no in-system fact exists, and drift toward FHIR `suspectEntity`. Related Medication / Medical Device / Procedure pointers are optional FKs (section J), not category.

The coded event (`code_system` + `code` + optional `code_display`) says **what** happened. No bound code system in schema. Tests may use a synthetic system. No MedDRA / SNOMED / ICD server.

## F. Severity

**DECISION.** Required. Reuse Allergy's three-value scale:

- `MILD`
- `MODERATE`
- `SEVERE`

Severity is part of the adverse-event fact (harm was documented). It is not Allergy `criticality` and not Observation value.

**DEFERRED — NOT REQUIRED FOR MINIMAL NATIVE FACT:** `LIFE_THREATENING`.

Reason: Allergy already froze `MILD` \| `MODERATE` \| `SEVERE`. A fourth grade is CTCAE / FDA pharmacovigilance vocabulary. Seriousness can be documented as `SEVERE` plus optional `note_text` in this wave. Adding `LIFE_THREATENING` is not required to persist the native fact.

## G. Status model

**DECISION.** Record lifecycle only, following Immunization / Procedure / Medical Device:

`ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR`

Not FHIR `in-progress` / `completed` / `cancelled`. Not Medication `STOPPED`. Not Consent `REVOKED`. Not incident-ticket workflow statuses.

Create is always `ACTIVE`.

## H. Lifecycle transitions

**DECISION.**

| From | To | Route |
|---|---|---|
| (create) | `ACTIVE` | `POST /adverse-events` |
| `ACTIVE` | `AMENDED` | `POST .../amend` |
| `AMENDED` | `AMENDED` | `POST .../amend` |
| `ACTIVE` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |
| `AMENDED` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |

Rules:

- create is always record `status=ACTIVE`
- amend must change an amendable field; no-op → 409
- `ENTERED_IN_ERROR` is the only terminal record status and does **not** increment `version`
- successful amend increments `version` by exactly 1
- reject `AMENDED → ACTIVE`, EIE → anything, double EIE
- no revoke, no `/stop`, no stored `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`, `EXPIRED`
- no generic PUT / PATCH
- DELETE = 405
- a corrected fact after EIE is a new row

## I. Occurrence and note

**DECISION.**

| Field | Null | Amendable | Notes |
|---|---|---|---|
| `occurrence_at` | YES | YES until EIE | timestamptz; when the event occurred or was observed |
| `note_text` | YES | YES until EIE | optional clinical note; max length 2000; redacted; not audited |

Note is unnecessary for a valid create. Keep text minimal. The coded event is the fact; `note_text` is optional commentary.

## J. Related clinical fact

**DECISION.** Optional, explicit, at most one pointer. No polymorphic `(related_type, related_id)`. The repository has no generic FK mechanism. A relationship table would be a second aggregate table and is rejected.

Nullable FKs on `adverse_events` (additive; do **not** modify the target tables):

| Column | Target | Null | On delete |
|---|---|---|---|
| `medication_id` | `medications.id` | YES | RESTRICT |
| `medical_device_id` | `medical_devices.id` | YES | RESTRICT |
| `procedure_id` | `procedures.id` | YES | RESTRICT |

CHECK: at most one of the three is non-null. Zero is allowed (event without an in-system suspected fact).

If a related id is supplied at create:

- the row must exist
- same organization
- same canonical patient as the Adverse Event
- related record `status` must not be `ENTERED_IN_ERROR` (409)
- cross-org related id → 404
- Adverse Event must **not** mutate the related row

After create, if the related fact is later marked `ENTERED_IN_ERROR`, the Adverse Event row is unchanged. No circular lifecycle. Related ids are **immutable** after create; a wrong link is corrected by EIE + new fact, not by retargeting.

**DEFERRED — NOT REQUIRED FOR MINIMAL NATIVE FACT:** FKs to Allergy, Condition, Immunization, Observation, Laboratory, or Encounter-as-cause. Encounter remains the optional care-episode bind (section N), not a causal target.

## K. Causality

**DEFERRED — NOT REQUIRED FOR MINIMAL NATIVE FACT.**

No `SUSPECTED` / `CONFIRMED` / `UNKNOWN` column in this wave.

Reason: causality assessment is a pharmacovigilance judgment (WHO-UMC / Naranjo-class scoring). The minimal fact is that an adverse event was documented, optionally pointing at one existing Medication / Medical Device / Procedure row. Allergy already models confirmation separately (`verification_status`); copying that here without a frozen AE verification convention would invent a second assessment model. Causality can be added later as an amendable column without rewriting identity, FKs, or lifecycle.

Do not introduce causality scoring, Bayesian models, external pharmacovigilance integrations, or AI inference.

## L. Outcome

**DEFERRED — NOT REQUIRED FOR MINIMAL NATIVE FACT.**

No recovered / fatal / ongoing outcome enum. That is a result model (FHIR AdverseEvent.outcome / seriousness extensions), not required to document that the event occurred. `SEVERE` plus optional `note_text` is sufficient for this wave.

## M. Immutable fields

**DECISION** (Procedure / Medical Device column set, plus related FKs). Frozen after create:

- `patient_identity_id`
- `encounter_id`
- `organization_id`
- `facility_id`
- `category`
- `code_system`, `code`, `code_display`
- `medication_id`, `medical_device_id`, `procedure_id`
- `recorder_id`
- `recorded_at`
- `provenance_id`

Related FKs are frozen because retargeting the suspected fact would silently rewrite history. Category and code are the documented event type.

## N. Amendable fields

**DECISION.** Amendable until EIE:

- `occurrence_at`
- `severity`
- `note_text`
- record `status` → `AMENDED`
- `version` (increment on amend)

`ENTERED_IN_ERROR` freezes the complete row. Enforce at API, service, trigger, and `app_dml`.

Severity is amendable because seriousness may be corrected after initial documentation (same class of clinical correction as Allergy severity). It is not a second lifecycle.

## O. Identity behavior

**SOURCE.** Canonical FK `patient_identities.id`.

| Case | Result |
|---|---|
| ACTIVE | accepted |
| MERGED without encounter | bind survivor |
| MERGED with historical encounter | frozen same-patient check; mismatch 409 |
| historical `patient_identity_id` | never rewritten after MPI merge |
| RETIRED | 409 |
| unknown / cross-org identity | 404 |
| cross-org resource | 404 |

## P. Encounter behavior

**DECISION.** Encounter is **optional** for ACTIVE identities (Immunization / Allergy / Medication / Procedure / Medical Device). Clinical notes remain the only fact that requires an encounter.

If supplied:

- same patient
- same organization
- documentable
- `CANCELLED` → 409
- `ENTERED_IN_ERROR` → 409
- cross-org → 404
- wrong patient/encounter pair → 409

Adverse Event must never mutate an encounter.

## Q. Anonymous / EMER behavior

**DECISION.** Follow Allergy / Medication / Immunization / Procedure / Medical Device, not Consent.

- standalone anonymous Adverse Event → 409
- anonymous + documentable `EMER` → allowed
- anonymous + non-`EMER` → 409
- do not store emergency implied consent

ACTIVE identities may document an adverse event with or without an encounter, including `EMER`.

## R. Organization / facility behavior

**SOURCE convention.**

- `organization_id` required; FK `organizations.id` ON DELETE RESTRICT
- `facility_id` optional; FK `facilities.id` ON DELETE RESTRICT
- facility out of caller scope → 403
- cross-org → 404

## S. Permission codes

**DECISION.** Permission codes (not yet in catalog — design only; do not modify the catalog in this pass):

| Permission | Intent |
|---|---|
| `clinical.adverse_event.create` | Create |
| `clinical.adverse_event.read` | Read / list by patient |
| `clinical.adverse_event.update` | Amend |
| `clinical.adverse_event.entered_in_error` | Void |

## T. Role / permission matrix

**DECISION.** Same matrix as Immunization / Procedure / Medical Device.

| Role | Access |
|---|---|
| CLINICIAN | create, read, update, EIE |
| PLATFORM_ADMIN | full catalog |
| ORG_ADMIN | read |
| AUDITOR | read |
| Registrar | denied, including + `TREATMENT` |
| IDENTITY_OFFICER | denied |

Permission checks only. Consent does not grant access. `Wave1PolicyPDP` untouched. After cataloguing Adverse Event, `clinical.care_plan.create` and `clinical.diagnosis.create` remain deny-by-default stubs (forbidden aliases, not the next domain).

## U. X-Purpose behavior

**SOURCE.** Existing `X-Purpose`. Required, normalized, catalog-validated, audited. Missing / unknown → 422. Purpose does not grant access. No new purpose values.

## V. Audit events

**DECISION.**

- `ADVERSE_EVENT_CREATED`
- `ADVERSE_EVENT_AMENDED`
- `ADVERSE_EVENT_ENTERED_IN_ERROR`

Allowed metadata: `category`, `severity`, record `status`, `version`, `purpose` (and frozen `old_status` / `new_status` on mutations). Related FK presence may be recorded as booleans (`has_medication_id`, etc.) if needed; never the related display/code.

## W. Audit redaction

Never audit or log: event display, event code, `note_text`, NIK, BPJS, tokens, passwords, secrets, raw payload.

Log redaction keys (design only; do not modify logging in this pass): existing `note` / `note_text` / `code_display`, plus `adverse_event_display`, `adverse_event_code`, `adverse_event_note`.

Do not redesign Wave 1 DENIED-audit rollback.

## X. Provenance

**DECISION.** Reuse `clinical_provenances`. `subject_type = ADVERSE_EVENT` (extend the existing CHECK). Insert-only. FK `ON DELETE RESTRICT`. Service always sets `provenance_id`. Column remains nullable (frozen convention). No new provenance mechanism.

## Y. Concurrency / SELECT FOR UPDATE

**SOURCE convention.** Mutations use `SELECT FOR UPDATE`. Redis is not a clinical lock.

| Race | Expected |
|---|---|
| amend vs amend | one 200, one 409, one `ADVERSE_EVENT_AMENDED` |
| EIE vs EIE | one 200, one 409, one `ADVERSE_EVENT_ENTERED_IN_ERROR` |
| amend vs EIE | final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1 |

## Z. API boundary

**DECISION.** Under `/api/v1/clinical/` only:

| Method | Path | Permission |
|---|---|---|
| POST | `/adverse-events` | `clinical.adverse_event.create` |
| GET | `/adverse-events?patient_identity_id=` | `clinical.adverse_event.read` |
| GET | `/adverse-events/{id}` | `clinical.adverse_event.read` |
| POST | `/adverse-events/{id}/amend` | `clinical.adverse_event.update` |
| POST | `/adverse-events/{id}/entered-in-error` | `clinical.adverse_event.entered_in_error` |

List requires `patient_identity_id`. PUT / PATCH / DELETE = 405. No `/api/v2/`. No `/fhir/`. No FHIR AdverseEvent resource.

## AA. Database constraints

**DECISION** (not implemented). Table `adverse_events`:

| Column | Null | Notes |
|---|---|---|
| `id` | NO | UUID PK |
| `patient_identity_id` | NO | FK `patient_identities.id` ON DELETE RESTRICT |
| `encounter_id` | YES | FK `encounters.id` ON DELETE RESTRICT |
| `organization_id` | NO | FK `organizations.id` ON DELETE RESTRICT |
| `facility_id` | YES | FK `facilities.id` ON DELETE RESTRICT |
| `category` | NO | CHECK `DOCUMENTED` \| `REPORTED` |
| `code_system` | NO | CHECK `char_length > 0` |
| `code` | NO | CHECK `char_length > 0` |
| `code_display` | YES | |
| `severity` | NO | CHECK `MILD` \| `MODERATE` \| `SEVERE` |
| `medication_id` | YES | FK `medications.id` ON DELETE RESTRICT |
| `medical_device_id` | YES | FK `medical_devices.id` ON DELETE RESTRICT |
| `procedure_id` | YES | FK `procedures.id` ON DELETE RESTRICT |
| `occurrence_at` | YES | timestamptz |
| `note_text` | YES | |
| `status` | NO | CHECK `ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR` |
| `recorded_at` | NO | timestamptz |
| `recorder_id` | YES | |
| `version` | NO | CHECK `>= 1` |
| `provenance_id` | YES | FK `clinical_provenances.id` ON DELETE RESTRICT |
| `created_at` / `updated_at` | NO | TimestampMixin |

CHECK: at most one of `medication_id`, `medical_device_id`, `procedure_id` is non-null.

Indexes: `patient_identity_id`, `encounter_id`, `organization_id`, `recorded_at`.

Trigger: `trg_adverse_events_history_immutable` / `prevent_adverse_event_history_mutation()` — Immunization/Procedure/Medical Device-shaped (EIE freezes row; illegal status transitions rejected; DELETE blocked; related FKs immutable).

`app_dml`: INSERT / SELECT / UPDATE. DELETE / TRUNCATE denied in `grant_dev_privileges.sql` (operational, outside Alembic — inherited).

Create `version = 1`. Successful amend increments version by exactly 1. EIE does **not** increment version.

Do not rewrite `0001`–`0015`.

## AB. Proposed Alembic number

**DECISION.** `20260814_0016` revising `20260814_0015`.

This pass does **not** create that migration.

## AC. Frozen-domain boundaries

Implementation, if started later, must not redesign Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, or Medical Device. Must not rewrite `0001`–`0015`. Must not modify `Wave1PolicyPDP`. Must not turn Consent into a PDP. Allowed previous-wave edits: catalog registration and deny-by-default stub movement only.

Optional FKs to `medications`, `medical_devices`, and `procedures` are additive on `adverse_events` only. They do not add columns to those frozen tables and do not change their lifecycles.

Vital signs remain Observation. Patient History remains out of scope.

## AD. Out-of-scope items

Do not start as part of Wave 2B.7 Adverse Event:

- FHIR AdverseEvent / DetectedIssue / Flag
- `/fhir/`, `/api/v2/`
- Consent-as-PDP or `Wave1PolicyPDP` rewrite
- AI, RAG, CDS, AI causality inference
- pharmacovigilance platform, causality scoring, external reporting workflow
- notification engine
- break-glass, patient portal
- scheduling, forecasting
- device recall / inventory, medication inventory
- registry synchronization
- Patient History aggregate
- VitalSign tables
- CarePlan, separate Diagnosis
- Family History
- outcome / seriousness / seriousness-criteria models beyond `severity`
- `LIFE_THREATENING` grade
- causality column
- polymorphic related-fact mechanism
- relationship table / suspect-entity aggregate
- EXPIRED, generic DELETE, PUT, PATCH

## Distinctions

| Concept | Owner |
|---|---|
| Documented anaphylaxis event | Adverse Event |
| Penicillin allergy on the problem-style allergy list | Allergy (already frozen) |
| Pacemaker associated with the patient | Medical Device (already frozen) |
| Pacemaker implantation performed | Procedure (already frozen) |
| Harm linked to that pacemaker | Adverse Event with optional `medical_device_id` |
| Heart rate / BP / SpO2 | Observation (already frozen) |
| Longitudinal summary of all facts | Out of scope (Patient History aggregate) |
| Warehouse recall | Out of scope (inventory) |

## Dependencies

Reuses: MPI identity resolution, optional documentable encounter, organization/facility scope, `clinical_provenances`, existing purpose catalog, permission catalog registration, audit insert, `app_dml` grants, history trigger, `SELECT FOR UPDATE`.

Does **not** require: Consent-as-PDP, FHIR, AI, RAG, CDS, break-glass, patient portal, scheduling, inventory, registry, causality engine, new aggregate family, or mutation of frozen Medication / Procedure / Medical Device rows.

## AE. Implementation-critical decisions (closed)

| # | Topic | Resolution |
|---|---|---|
| 1 | Table name | `adverse_events` |
| 2 | Category | `DOCUMENTED` \| `REPORTED` (not related-domain type) |
| 3 | Severity | required `MILD` \| `MODERATE` \| `SEVERE`; `LIFE_THREATENING` deferred |
| 4 | Status lifecycle | `ACTIVE` → `AMENDED` / `ENTERED_IN_ERROR` |
| 5 | `occurrence_at` | optional; amendable until EIE |
| 6 | `note_text` | optional; amendable until EIE; redacted |
| 7 | Causality | DEFERRED — NOT REQUIRED FOR MINIMAL NATIVE FACT |
| 8 | Related facts | optional at most one of `medication_id` / `medical_device_id` / `procedure_id`; immutable |
| 9 | Amendable fields | `occurrence_at`, `severity`, `note_text`, status, version |
| 10 | Immutable fields | identity, encounter, org, facility, category, code, related FKs, recorder, recorded_at, provenance |
| 11 | Anonymous / EMER | standalone 409; EMER allowed; non-EMER 409 |
| 12 | Encounter | optional; never mutated; same frozen documentable rules |
| 13 | Permissions | `clinical.adverse_event.create\|read\|update\|entered_in_error` |
| 14 | Audit events | `ADVERSE_EVENT_CREATED` / `AMENDED` / `ENTERED_IN_ERROR` |
| 15 | Provenance | `subject_type=ADVERSE_EVENT`; insert-only; RESTRICT |
| 16 | API routes | `/api/v1/clinical/adverse-events` + amend + EIE |
| 17 | Migration number | `20260814_0016` revising `0015` (not written) |
| 18 | Concurrency | `SELECT FOR UPDATE`; Redis is not a lock |

Coded event (`system` + `code` + optional display) is required, matching every frozen native fact. Outcome is deferred.

## AF. Risk register

| Sev | Kind | Finding |
|---|---|---|
| P0 | — | None at design time |
| P1 | — | None at design time |
| P2 | Inherited | DENIED-audit rows roll back with `ForbiddenError` |
| P2 | Inherited | Historical `patient_identity_id` is not rewritten after MPI merge |
| P2 | Inherited | Same-org UUID read until a later PDP wave |
| P2 | Adverse Event | Duplicate adverse-event facts allowed (same as Immunization / Procedure / Medical Device) |
| P3 | Inherited | `app_dml` grants live outside Alembic |
| P3 | Inherited | `provenance_id` nullable; service always sets it |
| P3 | Adverse Event | Causality and outcome deferred; callers must not infer them |
| P3 | Adverse Event | `LIFE_THREATENING` deferred; `SEVERE` is the top grade |
| P3 | Adverse Event | Related FKs are optional pointers; frozen facts are not redesigned |

## AG. Explicit approval decision

All implementation-critical decisions are resolved. Deferred items are explicit non-scope, not open questions.

```
WAVE 2B.7 NATIVE ADVERSE EVENT = APPROVED FOR DESIGN ONLY
DESIGN ONLY
NO CODE
NO MIGRATION
NO API IMPLEMENTATION
NO COMMIT
NO TAG
NO PUSH
```
