# Wave 2B.8 — Native Family History domain approval

**Status:** APPROVED FOR FAMILY HISTORY (DESIGN ONLY)
**Date:** 2026-08-16
**Baseline:** `wave-2b7-adverse-event-frozen` / `8d455b3dede07b9ada00205ff6c49b41b97a0895`
**Alembic at approval:** `20260814_0016`
**Implementation:** NOT STARTED

DESIGN ONLY  
NO CODE  
NO MIGRATION  
NO API IMPLEMENTATION  
NO COMMIT  
NO TAG  
NO PUSH

This document is a design contract. It is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize code, migration, commit, tag, or push.

Family History is a **native documented family-history fact** associated with a patient: one relative-relationship plus one coded condition/finding. It is **not** FHIR FamilyMemberHistory. It is **not** Patient History. It is **not** a clinical timeline, CarePlan, Diagnosis domain, Condition redesign, Observation redesign, aggregate, reporting projection, AI/RAG/CDS, or portal feature.

## Source vs inference

| Kind | Meaning |
|---|---|
| SOURCE | Already true in the frozen repository |
| DECISION | Resolved in this approval using a frozen-domain convention |
| DEFERRED | Explicitly out of this wave — NOT REQUIRED FOR MINIMAL NATIVE FACT |

Nothing below is filled from FHIR FamilyMemberHistory, FamilyMemberHistory.condition array, or pedigree-resource semantics.

The prior Wave 2B.8 discovery pass classified Family History as **F** (undefined). That pass required an explicit product/architecture selection plus a complete frozen-pattern contract. This document is that selection. Approval is justified because the named fact is a single native clinical documentation row, `family_histories` is absent from `FORBIDDEN_TABLES`, it is not owned by Condition/Observation/Adverse Event, and the fact can reuse Immunization / Procedure / Medical Device / Adverse Event conventions without redesigning frozen domains.

Patient History remains a presentation/read-model concept. It is **not** a table in this wave.

## A. Domain identity

**DECISION.** Native **Family History**.

Internal identifiers use `family_history` / `family_histories`. Do not name the table `patient_histories`, `family_members`, `pedigrees`, or `fhir_family_member_histories`.

One `family_histories` row represents: **this patient has a documented or reported family-history fact that a relative of a controlled relationship had a coded condition/finding.**

It does **not** represent:

- the patient's own problem-list or encounter diagnosis (Condition)
- a separate Diagnosis domain
- a vital-sign or measurement (Observation)
- an adverse event that happened to the patient (Adverse Event)
- a family-member MPI identity, name, date of birth, or national identifier
- a pedigree / genogram aggregate
- a longitudinal summary of the patient's own clinical facts (Patient History)

## B. Native fact vs aggregate

**DECISION.** One native documented fact. One table. Not an aggregate family.

Not Laboratory-style coordinated tables. Not `family_members` + `family_history_conditions`. Not CarePlan. Not FHIR FamilyMemberHistory with a nested condition array.

Multiple conditions for the same relative are multiple rows (same relationship value, different codes). That is the frozen one-fact-per-row pattern, not a relative master record.

The relative is **not** a `patient_identities` row. This wave does not create, match, or merge family-member identities.

## C. Table name

**DECISION.** Exactly one native table: `family_histories`.

Not `patient_histories`. Not `fhir_family_member_histories`. Not `vital_signs` (forbidden; Observation already owns measurements). Not `care_plans` (forbidden). Not `diagnoses` (forbidden; Condition already owns diagnosis). Not a JSON clinical payload.

Proposed additive revision (design only): `20260814_0017` revising `20260814_0016`.

`family_histories` is absent today. `FORBIDDEN_TABLES` does not include it. Wave 2B.7 tests asserting `patient_histories` is absent are Patient History absence checks, not a Family History forbidden-table rule.

## D. Family relationship

**DECISION.** Closed CHECK enum on the row. Not a terminology server. Not SNOMED family-relationship codes. Not sex-specific MOTHER/FATHER/AUNT/UNCLE splits.

| Value | Meaning |
|---|---|
| `PARENT` | Parent of the patient |
| `SIBLING` | Sibling of the patient |
| `CHILD` | Child of the patient |
| `GRANDPARENT` | Grandparent of the patient |
| `GRANDCHILD` | Grandchild of the patient |
| `AUNT_UNCLE` | Aunt or uncle of the patient |
| `COUSIN` | Cousin of the patient |
| `OTHER` | Any other relative or kinship the enumerator does not name |

This is the minimum useful first-degree (`PARENT`, `SIBLING`, `CHILD`), second-degree (`GRANDPARENT`, `GRANDCHILD`, `AUNT_UNCLE`), and common third-degree (`COUSIN`) set, plus `OTHER`.

**Rejected as first-class values:**

- `MOTHER` / `FATHER` / `AUNT` / `UNCLE` — sex-specific splits enlarge the vocabulary without changing the clinical fact; optional clarification belongs in `note_text`
- `SPOUSE` / `PARTNER` — household / social-history, not the genetic/family-history fact this wave records; use `OTHER` if documented
- `HALF_SIBLING` / `NIECE_NEPHEW` / `UNKNOWN` — covered by `SIBLING`, `OTHER`, or `OTHER`
- SNOMED / HL7 role codes as the stored relationship — would invent a terminology binding this architecture has never required on native facts

Relationship is **required** and **immutable**. Changing `PARENT` to `SIBLING` is a different fact, not an amendment of the same fact. Correction is `ENTERED_IN_ERROR` plus a new row.

`OTHER` does **not** require `note_text` (do not invent a validation rule frozen domains do not have for category).

## E. Category and coded finding

**DECISION.** Category is a two-value documented-source flag, analogous to Medical Device / Adverse Event `DOCUMENTED` \| `REPORTED`:

- `DOCUMENTED` — recorded as documented in this organization
- `REPORTED` — documented as reported (patient, family, or external report)

The coded finding uses the frozen terminology stub, not a Condition FK and not a Diagnosis table:

- `code_system` (required, non-empty)
- `code` (required, non-empty)
- `code_display` (optional)

These columns code **the relative's condition/finding**, not the patient's own Condition row. No bound code system in schema. Tests may use a synthetic system. No SNOMED / ICD server.

**Rejected:** `condition_id` FK to `conditions`. That would either attach the patient's own problem-list row to a relative, or require Condition rows that are not about the patient — both redesign frozen Condition.

## F. Occurrence and note

**DECISION.**

| Field | Null | Amendable | Notes |
|---|---|---|---|
| `occurrence_at` | YES | YES until EIE | timestamptz; when the relative's condition occurred or was known, not `recorded_at` |
| `note_text` | YES | YES until EIE | optional clinical note; max length 2000; redacted; not audited |

Note is unnecessary for a valid create. The relationship plus coded finding is the fact; `note_text` is optional commentary.

**DEFERRED — NOT REQUIRED FOR MINIMAL NATIVE FACT:** relative age-at-onset as a separate integer, deceased flag, relative sex, relative name.

## G. Status model

**DECISION.** Record lifecycle only, following Immunization / Procedure / Medical Device / Adverse Event:

`ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR`

Not FHIR `partial` / `completed`. Not Medication `STOPPED`. Not Consent `REVOKED`. Not a pedigree workflow.

Create is always `ACTIVE`.

## H. Lifecycle transitions

**DECISION.**

| From | To | Route |
|---|---|---|
| (create) | `ACTIVE` | `POST /family-histories` |
| `ACTIVE` | `AMENDED` | `POST .../amend` |
| `AMENDED` | `AMENDED` | `POST .../amend` |
| `ACTIVE` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |
| `AMENDED` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |

Rules:

- create is always record `status=ACTIVE`, `version=1`
- amend must change an amendable field; no-op → 409
- `ENTERED_IN_ERROR` is the only terminal record status and does **not** increment `version`
- successful amend increments `version` by exactly 1
- reject `AMENDED → ACTIVE`, EIE → anything, double EIE
- no revoke, no `/stop`, no stored `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`, `EXPIRED`
- no generic PUT / PATCH
- DELETE = 405
- a corrected fact after EIE is a new row

## I. Immutable fields

**DECISION** (Adverse Event / Procedure / Medical Device column set, substituting relationship for related FKs). Frozen after create:

- `patient_identity_id`
- `encounter_id`
- `organization_id`
- `facility_id`
- `relationship`
- `category`
- `code_system`, `code`, `code_display`
- `recorder_id`
- `recorded_at`
- `provenance_id`

Relationship, category, and code are the documented fact identity. Retargeting the relative class or the finding would silently rewrite history.

This list was checked against frozen Adverse Event: AE keeps `severity` amendable because seriousness can be corrected on the **same** event. Family History has no severity. Relationship is not an analogue of severity; it is an analogue of AE `category` / `code`.

## J. Amendable fields

**DECISION.** Amendable until EIE:

- `occurrence_at`
- `note_text`
- record `status` → `AMENDED`
- `version` (increment on amend)

`ENTERED_IN_ERROR` freezes the complete row. Enforce at API, service, trigger, and `app_dml`.

## K. Identity behavior

**SOURCE.** Canonical FK `patient_identities.id` (the **patient**, not the relative).

| Case | Result |
|---|---|
| ACTIVE | accepted |
| MERGED without encounter | bind survivor |
| MERGED with historical encounter | frozen same-patient check; mismatch 409 |
| historical `patient_identity_id` | never rewritten after MPI merge |
| RETIRED | 409 |
| unknown / cross-org identity | 404 |
| cross-org resource | 404 |

## L. Encounter behavior

**DECISION.** Encounter is **optional** for ACTIVE identities (Immunization / Allergy / Medication / Procedure / Medical Device / Adverse Event). Clinical notes remain the only fact that requires an encounter.

If supplied:

- same patient
- same organization
- documentable
- `CANCELLED` → 409
- `ENTERED_IN_ERROR` → 409
- cross-org → 404
- wrong patient/encounter pair → 409

Family History must never mutate an encounter.

## M. Anonymous / EMER behavior

**DECISION.** Follow Allergy / Medication / Immunization / Procedure / Medical Device / Adverse Event, not Consent.

- standalone anonymous Family History → 409
- anonymous + documentable `EMER` → allowed
- anonymous + non-`EMER` → 409
- do not store emergency implied consent

ACTIVE identities may document family history with or without an encounter, including `EMER`.

## N. Organization / facility behavior

**SOURCE convention.**

- `organization_id` required; FK `organizations.id` ON DELETE RESTRICT
- `facility_id` optional; FK `facilities.id` ON DELETE RESTRICT
- facility out of caller scope → 403
- cross-org → 404

## O. Permission codes

**DECISION.** Permission codes (not yet in catalog — design only; do not modify the catalog in this pass):

| Permission | Intent |
|---|---|
| `clinical.family_history.create` | Create |
| `clinical.family_history.read` | Read / list by patient |
| `clinical.family_history.update` | Amend |
| `clinical.family_history.entered_in_error` | Void |

## P. Role / permission matrix

**DECISION.** Same matrix as Immunization / Procedure / Medical Device / Adverse Event.

| Role | Access |
|---|---|
| CLINICIAN | create, read, update, EIE |
| PLATFORM_ADMIN | full catalog |
| ORG_ADMIN | read |
| AUDITOR | read |
| Registrar | denied, including + `TREATMENT` |
| IDENTITY_OFFICER | denied |

Permission checks only. Consent does not grant access. `Wave1PolicyPDP` untouched. After cataloguing Family History, `clinical.care_plan.create` and `clinical.diagnosis.create` remain deny-by-default stubs (forbidden aliases, not the next domain).

## Q. X-Purpose behavior

**SOURCE.** Existing `X-Purpose`. Required, normalized, catalog-validated, audited. Missing / unknown → 422. Purpose does not grant access. No new purpose values.

## R. Audit events

**DECISION.**

- `FAMILY_HISTORY_CREATED`
- `FAMILY_HISTORY_AMENDED`
- `FAMILY_HISTORY_ENTERED_IN_ERROR`

Allowed metadata: `relationship`, `category`, record `status`, `version`, `purpose` (and frozen `old_status` / `new_status` on mutations).

## S. Audit redaction

Never audit or log: condition/finding display, condition/finding code, `note_text`, NIK, BPJS, tokens, passwords, secrets, raw payload.

Log redaction keys (design only; do not modify logging in this pass): existing `note` / `note_text` / `code_display`, plus `family_history_display`, `family_history_code`, `family_history_note`.

Do not redesign Wave 1 DENIED-audit rollback.

## T. Provenance

**DECISION.** Reuse `clinical_provenances`. `subject_type = FAMILY_HISTORY` (extend the existing CHECK). Insert-only. FK `ON DELETE RESTRICT`. Service always sets `provenance_id`. Column remains nullable (frozen convention). No new provenance mechanism.

## U. Concurrency / SELECT FOR UPDATE

**SOURCE convention.** Mutations use `SELECT FOR UPDATE`. Redis is not a clinical lock.

| Race | Expected |
|---|---|
| amend vs amend | one 200, one 409, one `FAMILY_HISTORY_AMENDED` |
| EIE vs EIE | one 200, one 409, one `FAMILY_HISTORY_ENTERED_IN_ERROR` |
| amend vs EIE | final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1 |

## V. API boundary

**DECISION.** Under `/api/v1/clinical/` only. Collection path is **plural**, matching `/adverse-events`, `/medical-devices`, `/procedures`. Proposed `/family-history` was considered and rejected as inconsistent with frozen collection naming.

| Method | Path | Permission |
|---|---|---|
| POST | `/family-histories` | `clinical.family_history.create` |
| GET | `/family-histories?patient_identity_id=` | `clinical.family_history.read` |
| GET | `/family-histories/{id}` | `clinical.family_history.read` |
| POST | `/family-histories/{id}/amend` | `clinical.family_history.update` |
| POST | `/family-histories/{id}/entered-in-error` | `clinical.family_history.entered_in_error` |

List requires `patient_identity_id`. PUT / PATCH / DELETE = 405. No `/api/v2/`. No `/fhir/`. No FHIR FamilyMemberHistory resource. No `/revoke`. No `/stop`.

## W. Database constraints

**DECISION** (not implemented). Table `family_histories`:

| Column | Null | Notes |
|---|---|---|
| `id` | NO | UUID PK |
| `patient_identity_id` | NO | FK `patient_identities.id` ON DELETE RESTRICT |
| `encounter_id` | YES | FK `encounters.id` ON DELETE RESTRICT |
| `organization_id` | NO | FK `organizations.id` ON DELETE RESTRICT |
| `facility_id` | YES | FK `facilities.id` ON DELETE RESTRICT |
| `relationship` | NO | CHECK `PARENT` \| `SIBLING` \| `CHILD` \| `GRANDPARENT` \| `GRANDCHILD` \| `AUNT_UNCLE` \| `COUSIN` \| `OTHER` |
| `category` | NO | CHECK `DOCUMENTED` \| `REPORTED` |
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

No JSON payload column. No `fhir_family_member_histories` table. No FK to `conditions`, `observations`, `adverse_events`, or `allergies`.

Indexes: `patient_identity_id`, `encounter_id`, `organization_id`, `recorded_at`.

Trigger: `trg_family_histories_history_immutable` / `prevent_family_history_history_mutation()` — Immunization/Procedure/Medical Device/Adverse Event-shaped (EIE freezes row; illegal status transitions rejected; DELETE blocked; relationship/category/code/identity immutable; `occurrence_at` and `note_text` are **not** in the immutable trigger list).

`app_dml`: INSERT / SELECT / UPDATE. DELETE / TRUNCATE denied in `grant_dev_privileges.sql` (operational, outside Alembic — inherited).

Create `version = 1`. Successful amend increments version by exactly 1. EIE does **not** increment version.

Do not rewrite `0001`–`0016`.

## X. Proposed Alembic number

**DECISION.** `20260814_0017` revising `20260814_0016`.

This pass does **not** create that migration.

## Y. Frozen-domain boundaries

Implementation, if started later, must not redesign Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, Medical Device, or Adverse Event. Must not rewrite `0001`–`0016`. Must not modify `Wave1PolicyPDP`. Must not turn Consent into a PDP. Allowed previous-wave edits: catalog registration and deny-by-default stub movement only.

No additive FKs onto frozen fact tables. Family History does not mutate Condition, Observation, Adverse Event, or MPI relative identities.

Vital signs remain Observation. Patient History remains a presentation/read-model, not a table. Diagnosis remains Condition. CarePlan remains forbidden.

## Z. Security (design tests)

Implementation, if started later, must prove:

| Case | Expected |
|---|---|
| Unauthenticated | 401 |
| Unprovisioned JWT / missing permission | 403 |
| Registrar + `TREATMENT` or PERMIT consent | 403 (Consent is not a PDP) |
| IDENTITY_OFFICER | 403 |
| Missing / unknown `X-Purpose` | 422; purpose does not grant access |
| Unknown patient | 404 |
| Cross-org identity or resource | 404 |
| RETIRED patient | 409 |
| Standalone anonymous | 409 |
| Anonymous + non-EMER | 409 |
| Unauthorized body must not leak finding code, display, or note | Pass |
| SQL / parameterized access only | Pass (SQLAlchemy; no string-built SQL) |
| Same-org UUID read | 200 if org-scoped permission exists (inherited P2 until a later PDP wave) |

## AA. Semantic boundaries

| Concept | Owner |
|---|---|
| Mother had breast cancer (documented about the patient) | Family History (`PARENT` + coded finding) |
| Patient has breast cancer on the problem list | Condition (frozen) |
| Encounter diagnosis of the patient | Condition (frozen) |
| Heart rate / BP / SpO2 | Observation (frozen) |
| Patient anaphylaxis event | Adverse Event (frozen) |
| Pacemaker associated with the patient | Medical Device (frozen) |
| Longitudinal summary of the patient's own facts | Out of scope (Patient History read-model / aggregate) |
| Pedigree / genogram / relative MPI | Out of scope |
| Care plan | Forbidden (`care_plans`) |
| FHIR FamilyMemberHistory | Forbidden architecture |

## AB. Out-of-scope items

Do not start as part of Wave 2B.8 Family History:

- FHIR FamilyMemberHistory / pedigree resources
- `/fhir/`, `/api/v2/`
- Consent-as-PDP or `Wave1PolicyPDP` rewrite
- AI, RAG, CDS, genetic-risk scoring
- Patient History table or clinical timeline
- CarePlan, separate Diagnosis, Vital Signs table
- relative MPI / name / NIK / date of birth
- `family_members` master table or nested condition array
- FK to `conditions`
- deceased flag, age-at-onset integer, relative sex as schema
- SNOMED relationship binding
- break-glass, patient portal
- scheduling, inventory, registry
- expanding frozen Adverse Event / Medical Device / Procedure deferred fields
- EXPIRED, generic DELETE, PUT, PATCH

## AC. Dependencies

Reuses: MPI identity resolution, optional documentable encounter, organization/facility scope, `clinical_provenances`, existing purpose catalog, permission catalog registration, audit insert, `app_dml` grants, history trigger, `SELECT FOR UPDATE`.

Does **not** require: Consent-as-PDP, FHIR, AI, RAG, CDS, break-glass, patient portal, scheduling, inventory, registry, relative identity, Condition FK, new aggregate family, or mutation of frozen clinical rows.

## AD. Implementation-critical decisions (closed)

| # | Topic | Resolution |
|---|---|---|
| 1 | Table name | `family_histories` |
| 2 | One row | one patient + one relationship + one coded finding |
| 3 | Relationship | `PARENT` \| `SIBLING` \| `CHILD` \| `GRANDPARENT` \| `GRANDCHILD` \| `AUNT_UNCLE` \| `COUSIN` \| `OTHER`; immutable |
| 4 | Category | `DOCUMENTED` \| `REPORTED` |
| 5 | Finding code | `code_system` + `code` + optional display; not a Condition FK |
| 6 | Status lifecycle | `ACTIVE` → `AMENDED` / `ENTERED_IN_ERROR` |
| 7 | `occurrence_at` | optional; amendable until EIE |
| 8 | `note_text` | optional; amendable until EIE; redacted; max 2000 |
| 9 | Amendable fields | `occurrence_at`, `note_text`, status, version |
| 10 | Immutable fields | identity, encounter, org, facility, relationship, category, code, recorder, recorded_at, provenance |
| 11 | Anonymous / EMER | standalone 409; EMER allowed; non-EMER 409 |
| 12 | Encounter | optional; never mutated; same frozen documentable rules |
| 13 | Permissions | `clinical.family_history.create\|read\|update\|entered_in_error` |
| 14 | Audit events | `FAMILY_HISTORY_CREATED` / `AMENDED` / `ENTERED_IN_ERROR` |
| 15 | Provenance | `subject_type=FAMILY_HISTORY`; insert-only; RESTRICT |
| 16 | API routes | `/api/v1/clinical/family-histories` + amend + EIE |
| 17 | Migration number | `20260814_0017` revising `0016` (not written) |
| 18 | Concurrency | `SELECT FOR UPDATE`; Redis is not a lock |

## AE. Risk register

| Sev | Kind | Finding |
|---|---|---|
| P0 | — | None at design time |
| P1 | — | None at design time |
| P2 | Inherited | DENIED-audit rows roll back with `ForbiddenError` |
| P2 | Inherited | Historical `patient_identity_id` is not rewritten after MPI merge |
| P2 | Inherited | Same-org UUID read until a later PDP wave |
| P2 | Family History | Duplicate family-history facts allowed (same as Immunization / Procedure / Medical Device / Adverse Event) |
| P3 | Inherited | `app_dml` grants live outside Alembic |
| P3 | Inherited | `provenance_id` nullable; service always sets it |
| P3 | Family History | Relative identity / deceased / age-at-onset / sex-specific relationship deferred |
| P3 | Family History | `OTHER` is a residual kinship bucket, not a terminology system |

## AF. Explicit approval decision

All implementation-critical decisions are resolved. Deferred items are explicit non-scope, not open questions.

```
WAVE 2B.8 NATIVE FAMILY HISTORY = APPROVED FOR DESIGN ONLY
DESIGN ONLY
NO CODE
NO MIGRATION
NO API IMPLEMENTATION
NO COMMIT
NO TAG
NO PUSH
```
