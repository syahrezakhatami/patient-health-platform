# Wave 2B.6 — Native Medical Device domain approval

**Status:** APPROVED FOR MEDICAL DEVICE (DESIGN ONLY)
**Date:** 2026-08-15
**Baseline:** `wave-2b5-procedure-frozen` / `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad`
**Alembic at approval:** `20260814_0014`
**Implementation:** NOT STARTED

DESIGN ONLY  
NO CODE  
NO MIGRATION  
NO API IMPLEMENTATION  
NO COMMIT  
NO TAG  
NO PUSH

This document is a design contract. It is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize code, migration, commit, tag, or push.

Medical Device is a **native documented patient-associated device fact**. It is **not** FHIR Device. It is **not** inventory, asset management, scheduling, recall workflow, Observation, Procedure, Patient History, or Adverse Event.

## Source vs inference

| Kind | Meaning |
|---|---|
| SOURCE | Already true in the frozen repository |
| DECISION | Resolved in this approval using a frozen-domain convention |
| DEFERRED | Explicitly out of this wave |

Nothing below is filled from FHIR Device, DeviceDefinition, DeviceRequest, or DeviceAssociation resource semantics.

The prior Wave 2B.6 discovery pass classified device/implant as **undefined**. That pass required explicit product/architecture selection before naming a next fact. This contract is that selection. Approval is justified because the named fact is a single native clinical association, is absent from `FORBIDDEN_TABLES`, and can reuse the Immunization/Procedure conventions without redesigning frozen domains. A user proposal alone would not have been sufficient; the repository pattern fit is.

## A. Domain name

**DECISION.** Native **Medical Device**.

Internal identifiers use `medical_device` / `medical_devices`. Do not name the table `devices` or `fhir_devices`.

## B. Domain purpose

**DECISION.** A Medical Device row records that a patient **has, uses, or is associated with** a coded medical device.

Examples of the fact, not of schema:

- pacemaker associated with the patient
- insulin pump in use
- implanted device association
- hearing aid association
- prosthetic device association

It does **not** record:

- a measurement produced by or about the device (Observation)
- the implantation or explant act (Procedure)
- hospital stock, warehouse, procurement, or asset tracking
- maintenance, recall, or registry synchronization

## C. Native fact vs aggregate

**DECISION.** One native documented fact. One table. Not an aggregate family.

Not Laboratory-style coordinated tables. Not CarePlan. Not FHIR Device + DeviceAssociation + DeviceRequest.

## D. Table name

**DECISION.** Exactly one native table: `medical_devices`.

Not `devices`. Not `fhir_devices`. Not `vital_signs` (forbidden; Observation already owns measurements). Not `care_plans` (forbidden). Not a JSON clinical payload.

Proposed additive revision (design only): `20260814_0015` revising `20260814_0014`.

`medical_devices` is absent today. `FORBIDDEN_TABLES` does not include it.

## E. Category model

**DECISION.** Category is a two-value documented-source flag, analogous to Procedure `PERFORMED` \| `REPORTED` and Immunization `ADMINISTERED` \| `REPORTED`:

- `DOCUMENTED` — recorded as present or used in this organization
- `REPORTED` — documented as reported (patient, external facility, or other report)

Not FHIR `Device.status`. Not implanted-versus-external as the category axis. Implanted pump versus hearing aid is expressed by the terminology stub (`code_system` + `code` + optional `code_display`), not by a second enum in this wave.

No bound code system in schema. Tests may use a synthetic system. No GMDN/SNOMED/UDI server.

## F. Status model

**DECISION.** Two axes, following Allergy rather than Medication:

| Axis | Values | Meaning |
|---|---|---|
| Record `status` | `ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR` | Documentation lifecycle (Immunization / Procedure) |
| `association_status` | `IN_USE` \| `NO_LONGER_USED` | Whether the patient is still associated with the device |

Record `status` is **not** FHIR Device status. `association_status` is **not** warehouse retirement and **not** Medication `STOPPED`.

Create defaults: record `status=ACTIVE`, `association_status=IN_USE` unless supplied as `NO_LONGER_USED` (historical reported association).

`NO_LONGER_USED` covers explanted, discontinued, or replaced association. It is an amendable clinical field, not a new lifecycle family, not `EXPIRED`, and not DELETE.

Medication `STOPPED` is rejected for this wave: the user-required pattern is Immunization/Procedure record lifecycle. Allergy already shows how an ongoing association can become inactive without copying Medication stop.

## G. Lifecycle transitions

**DECISION.** Allergy / Immunization / Procedure record lifecycle. Not Medication `STOPPED`. Not Consent `REVOKED`. Not FHIR `inactive` as the row status.

| From | To | Route |
|---|---|---|
| (create) | `ACTIVE` | `POST /medical-devices` |
| `ACTIVE` | `AMENDED` | `POST .../amend` |
| `AMENDED` | `AMENDED` | `POST .../amend` |
| `ACTIVE` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |
| `AMENDED` | `ENTERED_IN_ERROR` | `POST .../entered-in-error` |

Rules:

- create is always record `status=ACTIVE`
- amend must change an amendable field; no-op → 409
- changing `association_status` is a valid amend (for example `IN_USE` → `NO_LONGER_USED`)
- `ENTERED_IN_ERROR` is the only terminal record status
- reject `AMENDED → ACTIVE`, EIE → anything, double EIE
- no revoke
- no stored `EXPIRED`, `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `STOPPED`, `CANCELLED`, `INACTIVE` as record status
- no generic PUT / PATCH
- DELETE = 405
- a corrected association after EIE is a new fact

## H. Immutable fields

**DECISION** (Immunization/Procedure column set). Frozen after create:

- `patient_identity_id`
- `encounter_id`
- `organization_id`
- `facility_id`
- `category`
- `code_system`, `code`, `code_display`
- `recorder_id`
- `recorded_at`
- `provenance_id`

## I. Amendable fields

**DECISION.** Amendable until EIE:

- `association_status`
- `occurrence_at`
- `note_text`
- record `status` → `AMENDED`
- `version` (increment on amend)

`ENTERED_IN_ERROR` freezes the complete row. Enforce at API, service, trigger, and `app_dml`.

## Derived / out-of-scope fields

| Field class | Items |
|---|---|
| Derived | none in this wave |
| Explicitly out of scope | UDI, serial, lot, manufacturer, model, brand, expiry, parent device, owner, location, URL, safety, quantity, inventory status, recall, maintenance schedule, performer, body site, reason, outcome, FK to `procedures`, vital signs, adverse event |

## J. Identity behavior

**SOURCE.** Canonical FK `patient_identities.id`.

| Case | Result |
|---|---|
| ACTIVE | accepted |

## K. MERGED behavior

**SOURCE convention.**

| Case | Result |
|---|---|
| MERGED without encounter | bind survivor |
| MERGED with historical encounter | frozen same-patient check; mismatch 409 |
| historical `patient_identity_id` | never rewritten after MPI merge |

## L. RETIRED behavior

**SOURCE.** RETIRED identity → 409.

## M. Unknown / cross-org behavior

**SOURCE.** Unknown identity or cross-org resource/identity → 404.

## N. Encounter behavior

**DECISION.** Encounter is **optional** for ACTIVE identities (Immunization / Allergy / Medication / Procedure). Clinical notes remain the only fact that requires an encounter.

If supplied:

- same patient
- same organization
- documentable
- `CANCELLED` → 409
- `ENTERED_IN_ERROR` → 409
- cross-org → 404
- wrong patient/encounter pair → 409

Medical Device must never mutate an encounter. Do not infer implantation from a linked Procedure. Do not add `procedure_id`.

## O. Anonymous behavior

**DECISION.** Follow Allergy / Medication / Immunization / Procedure, not Consent.

- standalone anonymous Medical Device → 409
- anonymous Medical Device requires a documentable `EMER` encounter
- do not store emergency implied consent

## P. EMER behavior

**DECISION.** Anonymous writes are allowed only on a documentable `EMER` encounter. ACTIVE identities may document a device with or without an encounter, including `EMER`.

Vital signs and emergency measurements remain Observation. Do not create EmergencyVitalSign or EmergencyObservation tables.

## Q. Organization / facility behavior

**SOURCE convention.**

- `organization_id` required; FK `organizations.id` ON DELETE RESTRICT
- `facility_id` optional; FK `facilities.id` ON DELETE RESTRICT
- facility out of caller scope → 403
- cross-org → 404
- Medical Device is not a facility asset register

## R. Permission codes

**DECISION.** Permission codes (not yet in catalog — design only):

| Permission | Intent |
|---|---|
| `clinical.medical_device.create` | Create |
| `clinical.medical_device.read` | Read / list by patient |
| `clinical.medical_device.update` | Amend |
| `clinical.medical_device.entered_in_error` | Void |

## S. Role / permission matrix

**DECISION.** Same matrix as Immunization / Procedure.

| Role | Access |
|---|---|
| CLINICIAN | create, read, update, EIE |
| PLATFORM_ADMIN | full catalog |
| ORG_ADMIN | read |
| AUDITOR | read |
| Registrar | denied, including + `TREATMENT` |
| IDENTITY_OFFICER | denied |

Permission checks only. Consent does not grant access. `Wave1PolicyPDP` untouched. After cataloguing Medical Device, `clinical.care_plan.create` and `clinical.diagnosis.create` remain deny-by-default stubs (forbidden aliases, not the next domain).

## T. X-Purpose behavior

**SOURCE.** Existing `X-Purpose`. Required, normalized, catalog-validated, audited. Missing / unknown → 422. Purpose does not grant access. No new purpose values.

## U. Audit events

**DECISION.**

- `MEDICAL_DEVICE_CREATED`
- `MEDICAL_DEVICE_AMENDED`
- `MEDICAL_DEVICE_ENTERED_IN_ERROR`

Allowed metadata: `category`, record `status`, `association_status`, `version`, `purpose` (and frozen `old_status` / `new_status` on mutations).

## V. Audit redaction

Never audit or log: device display, device code, note, UDI/serial (also not stored), NIK, BPJS, tokens, passwords, secrets, raw payload.

Log redaction keys (design only; do not modify logging in this pass): existing `note` / `note_text` / `code_display`, plus `device_display`, `device_code`, `medical_device_note`.

Do not redesign Wave 1 DENIED-audit rollback.

## W. Provenance subject_type

**DECISION.** Reuse `clinical_provenances`. `subject_type = MEDICAL_DEVICE` (extend the existing CHECK).

## X. Provenance FK behavior

**SOURCE convention.** Insert-only. FK `ON DELETE RESTRICT`. Service always sets `provenance_id`. Column remains nullable (frozen convention).

## Y. Concurrency / SELECT FOR UPDATE

**SOURCE convention.** Mutations use `SELECT FOR UPDATE`. Redis is not a clinical lock.

| Race | Expected |
|---|---|
| amend vs amend | one 200, one 409, one `MEDICAL_DEVICE_AMENDED` |
| EIE vs EIE | one 200, one 409, one `MEDICAL_DEVICE_ENTERED_IN_ERROR` |
| amend vs EIE | final `ENTERED_IN_ERROR`; one EIE audit; amend audit 0 or 1 |

## Z. API boundary

**DECISION.** Under `/api/v1/clinical/` only:

| Method | Path | Permission |
|---|---|---|
| POST | `/medical-devices` | `clinical.medical_device.create` |
| GET | `/medical-devices?patient_identity_id=` | `clinical.medical_device.read` |
| GET | `/medical-devices/{id}` | `clinical.medical_device.read` |
| POST | `/medical-devices/{id}/amend` | `clinical.medical_device.update` |
| POST | `/medical-devices/{id}/entered-in-error` | `clinical.medical_device.entered_in_error` |

List requires `patient_identity_id`. No `/api/v2/`. No `/fhir/`. No FHIR Device resource. No `/stop` route.

## AA. PUT / PATCH / DELETE behavior

**SOURCE convention.** PUT / PATCH / DELETE = 405.

## AB. Database constraints

**DECISION** (not implemented). Table `medical_devices`:

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
| `association_status` | NO | CHECK `IN_USE` \| `NO_LONGER_USED` |
| `occurrence_at` | YES | timestamptz; when association was observed or began |
| `note_text` | YES | |
| `status` | NO | CHECK `ACTIVE` \| `AMENDED` \| `ENTERED_IN_ERROR` |
| `recorded_at` | NO | timestamptz |
| `recorder_id` | YES | |
| `version` | NO | CHECK `>= 1` |
| `provenance_id` | YES | FK `clinical_provenances.id` ON DELETE RESTRICT |
| `created_at` / `updated_at` | NO | TimestampMixin |

Indexes: `patient_identity_id`, `encounter_id`, `organization_id`, `recorded_at`.

Trigger: `trg_medical_devices_history_immutable` / `prevent_medical_device_history_mutation()` — Immunization/Procedure-shaped (EIE freezes row; illegal status transitions rejected; DELETE blocked).

`app_dml`: INSERT / SELECT / UPDATE. DELETE / TRUNCATE denied in `grant_dev_privileges.sql` (operational, outside Alembic — inherited).

Create `version = 1`. Successful amend increments version by exactly 1. EIE does **not** increment version.

Do not rewrite `0001`–`0014`.

## AC. Proposed Alembic number

**DECISION.** `20260814_0015` revising `20260814_0014`.

This pass does **not** create that migration.

## AD. Frozen-domain boundaries

Implementation, if started later, must not redesign Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, or Procedure. Must not rewrite `0001`–`0014`. Must not modify `Wave1PolicyPDP`. Must not turn Consent into a PDP. Allowed previous-wave edits: catalog registration and deny-by-default stub movement only.

Deferred Procedure fields (performer, site, reason, outcome) do **not** move into Medical Device.

## AE. Out-of-scope items

Do not start as part of Wave 2B.6 Medical Device:

- FHIR Device / DeviceDefinition / DeviceRequest / DeviceAssociation
- `/fhir/`, `/api/v2/`
- Consent-as-PDP or `Wave1PolicyPDP` rewrite
- AI, RAG, CDS
- break-glass, patient portal
- scheduling, forecasting
- inventory, warehouse, procurement, asset management, maintenance, recall
- registry synchronization
- Patient History
- Adverse Event
- VitalSign / EmergencyVitalSign / EmergencyObservation (Observation already owns measurements)
- CarePlan, separate Diagnosis
- UDI / serial / manufacturer / lot / expiry columns
- FK to `procedures`
- performer / site / reason / outcome
- EXPIRED, generic DELETE, `/stop`

## Distinctions

| Concept | Owner |
|---|---|
| Patient has a pacemaker | Medical Device |
| Pacemaker implantation performed | Procedure (already frozen) |
| Heart rate 45 bpm | Observation |
| Blood pressure 80/50 | Observation |
| SpO2 88% | Observation |
| Device sitting in a hospital warehouse | Out of scope (inventory) |
| Family history / adverse event | Out of scope this wave |

## Dependencies

Reuses: MPI identity resolution, optional documentable encounter, organization/facility scope, `clinical_provenances`, existing purpose catalog, permission catalog registration, audit insert, `app_dml` grants, history trigger, `SELECT FOR UPDATE`.

Does **not** require: Consent-as-PDP, FHIR, AI, RAG, CDS, break-glass, patient portal, scheduling, inventory, registry, performer aggregate, anatomy catalog, new aggregate family.

## AF. Risk register

| Sev | Kind | Finding |
|---|---|---|
| P0 | — | None at design time |
| P1 | — | None at design time |
| P2 | Inherited | DENIED-audit rows roll back with `ForbiddenError` |
| P2 | Inherited | Historical `patient_identity_id` is not rewritten after MPI merge |
| P2 | Inherited | Same-org UUID read until a later PDP wave |
| P2 | Medical Device | Duplicate device-association facts allowed (same as Immunization / Procedure) |
| P3 | Inherited | `app_dml` grants live outside Alembic |
| P3 | Inherited | `provenance_id` nullable; service always sets it |
| P3 | Medical Device | UDI, serial, manufacturer, lot, and expiry are deferred; callers must not infer them |
| P3 | Medical Device | `NO_LONGER_USED` is association, not inventory retirement |
| P3 | Medical Device | No FK to Procedure; implantation/explant remain separate facts |

## AG. Explicit approval decision

All implementation-critical decisions are resolved. Deferred items are explicit non-scope, not open questions.

```
WAVE 2B.6 = APPROVED FOR MEDICAL DEVICE
DESIGN ONLY
NO CODE
NO MIGRATION
NO API IMPLEMENTATION
NO COMMIT
NO TAG
NO PUSH
```
