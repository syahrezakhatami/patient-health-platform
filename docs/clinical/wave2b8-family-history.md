# Wave 2B.8 — Native Family History

**Status:** FROZEN  
**Hardening:** COMPLETE  
**Frozen:** YES

Wave 2B.8 adds **Family History** as a bounded native clinical fact on the frozen Wave 2B.7 Adverse Event baseline.

It is **not** a FHIR FamilyMemberHistory server. It is **not** Patient History, a clinical timeline, CarePlan, Diagnosis, Condition redesign, Observation redesign, aggregate, reporting projection, or AI/RAG/CDS.

## Purpose

Record one documented or reported family-history fact for a patient: one controlled relative relationship plus one coded condition/finding.

## Domain boundary

In scope: native `family_histories` table, relationship vocabulary, category `DOCUMENTED` or `REPORTED`, finding terminology stub, optional occurrence/note, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: Patient History table, pedigree/relative MPI, sex-specific relationship values, deceased/age-at-onset columns, Condition FK, CarePlan, FHIR mapping, AI/RAG/CDS.

## Intentional differences from Adverse Event / Condition

Family History is a documented fact **about a relative**, stored on the patient's record.

- Relationship is a closed CHECK enum: `PARENT` | `SIBLING` | `CHILD` | `GRANDPARENT` | `GRANDCHILD` | `AUNT_UNCLE` | `COUSIN` | `OTHER`. It is immutable.
- Category is documentation source: `DOCUMENTED` | `REPORTED`.
- The coded finding uses the frozen terminology stub on the row. There is no `condition_id` and no Diagnosis table.
- Multiple findings for the same relative are multiple rows.
- The relative is not a `patient_identities` row.
- Amendable fields are `occurrence_at` and `note_text` (plus record status/version). Relationship, category, and code stay frozen.
- Anonymous writes follow Allergy/Medication/Immunization/Procedure/Medical Device/Adverse Event: standalone 409; allowed only on a documentable `EMER` encounter.

Record status follows Adverse Event: create `ACTIVE`, first successful amend → `AMENDED`, dedicated void → `ENTERED_IN_ERROR`.

## Data model

`family_histories` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `relationship` | controlled relative class (immutable) |
| `category` | `DOCUMENTED` or `REPORTED` (immutable) |
| `code_*` | relative's finding coding (immutable) |
| `occurrence_at` | optional; amendable until EIE |
| `note_text` | optional; amendable until terminal; never audited |
| `status` | `ACTIVE`, `AMENDED`, `ENTERED_IN_ERROR` |
| `recorded_at` | immutable after insert |

No JSON clinical payload. No Condition FK. No relative identity columns.

## Lifecycle

Create is always `ACTIVE`, version 1. `ACTIVE|AMENDED → AMENDED` via amend (must change a mutable field). `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. EIE does not increment version.

Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, `ENTERED_IN_ERROR → anything`.

No generic PUT. No DELETE. A corrected fact after EIE is a new row.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind the survivor. New writes with encounter use the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`.

Anonymous identities may **not** receive a standalone Family History. They may receive a Family History only on an `EMER` encounter.

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Cross-org encounter `404`. Wrong pair `409`. Family History does not mutate encounters.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.family_history.create` | Create |
| `clinical.family_history.read` | Read / list by patient |
| `clinical.family_history.update` | Amend |
| `clinical.family_history.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar and IDENTITY_OFFICER receive none. Purpose does not grant access. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default. `Wave1PolicyPDP` is unchanged. Consent is not a PDP.

## Purpose of use

`X-Purpose` is request context. It is required, normalized, and catalog-validated. Missing or unknown → 422. It is not a persisted consent record and does not grant access.

## Audit / provenance

Events: `FAMILY_HISTORY_CREATED`, `FAMILY_HISTORY_AMENDED`, `FAMILY_HISTORY_ENTERED_IN_ERROR`. Metadata is relationship/category/status/version/purpose — not finding display, code, note, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=FAMILY_HISTORY`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging redacts `code_display`, `family_history_display`, `family_history_code`, `note`, `note_text`, and `family_history_note`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, relationship, category, finding code/display, recorded time, recorder, provenance.

Until EIE, amend may change occurrence, note, record status, and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked. `app_dml` does not receive DELETE.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a Family History lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row. Concurrent amend versus EIE: final `ENTERED_IN_ERROR`, one `FAMILY_HISTORY_ENTERED_IN_ERROR` (amend audit 0 or 1 depending on winner).

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/family-histories` | `clinical.family_history.create` |
| GET | `/family-histories?patient_identity_id=` | `clinical.family_history.read` |
| GET | `/family-histories/{id}` | `clinical.family_history.read` |
| POST | `/family-histories/{id}/amend` | `clinical.family_history.update` |
| POST | `/family-histories/{id}/entered-in-error` | `clinical.family_history.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0017`. Do not edit `0001`–`0016`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Family History is present. Patient History, VitalSign tables, CarePlan, Diagnosis, FHIR FamilyMemberHistory, AI, RAG, and CDS remain absent. Frozen Adverse Event, Medical Device, Procedure, Immunization, Consent, Allergy, Medication, Laboratory, Observation, and Condition remain intact.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical family-history rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's family history by UUID (org-scoped clinical read until a later PDP wave). Duplicate family-history facts are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. Relative identity, deceased, and age-at-onset are deferred. This gate is not a HIPAA/ISO/SOC 2 certification.
