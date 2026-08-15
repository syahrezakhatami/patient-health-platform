# Wave 2B.7 — Native Adverse Event

Wave 2B.7 adds **Adverse Event** as a bounded native clinical fact on the frozen Wave 2B.6 Medical Device baseline.

It is **not** a FHIR AdverseEvent server. It is **not** a pharmacovigilance platform, incident-management system, Patient History aggregate, Vital Signs table, CarePlan, Diagnosis, or AI/RAG/CDS.

## Purpose

Record one documented coded adverse event for a patient, with an amendable documented-fact lifecycle and an optional pointer to at most one related Medication, Medical Device, or Procedure.

## Domain boundary

In scope: native `adverse_events` table, category `DOCUMENTED` or `REPORTED`, event terminology stub, severity `MILD` | `MODERATE` | `SEVERE`, optional related-fact FKs, optional occurrence/note, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: causality, outcome, `LIFE_THREATENING`, pharmacovigilance, incident/notification/reporting/regulatory workflow, Patient History, Vital Signs table, FHIR mapping, AI/RAG/CDS, CarePlan, scheduling, inventory.

## Intentional differences from Medical Device / Procedure

Adverse Event is a documented harm/reaction fact, not a device association and not a performed act.

- Category is documentation source: `DOCUMENTED` | `REPORTED`. It is not MEDICATION / DEVICE / PROCEDURE.
- Required `severity` is `MILD` | `MODERATE` | `SEVERE`. `LIFE_THREATENING` is deferred.
- Optional related FKs: at most one of `medication_id`, `medical_device_id`, `procedure_id`. Zero is allowed. Related ids are immutable after create. Adverse Event never mutates the referenced row.
- Amendable fields are `occurrence_at`, `severity`, and `note_text` (plus record status/version). Severity is amendable because seriousness may be corrected after initial documentation (Allergy analog). Category, code, and related FKs stay frozen.
- Anonymous writes follow Allergy/Medication/Immunization/Procedure/Medical Device: standalone 409; allowed only on a documentable `EMER` encounter.
- Consent remains a persisted fact and is not a PDP for Adverse Event reads.

Record status follows Allergy/Immunization/Procedure/Medical Device: create `ACTIVE`, first successful amend → `AMENDED`, dedicated void → `ENTERED_IN_ERROR`.

## Data model

`adverse_events` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `category` | `DOCUMENTED` or `REPORTED` (immutable) |
| `code_*` | event coding (immutable) |
| `severity` | `MILD`, `MODERATE`, or `SEVERE` (amendable until EIE) |
| `medication_id` / `medical_device_id` / `procedure_id` | optional; at most one; immutable |
| `occurrence_at` | optional; amendable until EIE |
| `note_text` | optional; amendable until terminal; never audited |
| `status` | `ACTIVE`, `AMENDED`, `ENTERED_IN_ERROR` |
| `recorded_at` | immutable after insert |

No JSON clinical payload. No causality, outcome, seriousness-criteria, or extra related-fact types.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via amend (must change a mutable field). `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route. EIE does not increment version.

Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, `ENTERED_IN_ERROR → anything`.

No generic PUT. No DELETE. A corrected fact after EIE is a new row.

## Related facts

Valid: none, or exactly one of medication / medical device / procedure.

At create, a supplied related id must exist, same organization, same canonical patient, and not `ENTERED_IN_ERROR`. Missing/cross-org related id → 404. Wrong patient or EIE related fact → 409. Later EIE of the related row does not change the Adverse Event.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind the survivor. New writes with encounter use the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`.

Anonymous identities may **not** receive a standalone Adverse Event. They may receive an Adverse Event only on an `EMER` encounter.

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Cross-org encounter `404`. Wrong pair `409`. Adverse Event does not mutate encounters.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.adverse_event.create` | Create |
| `clinical.adverse_event.read` | Read / list by patient |
| `clinical.adverse_event.update` | Amend |
| `clinical.adverse_event.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar and IDENTITY_OFFICER receive none. Purpose does not grant access. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default. `Wave1PolicyPDP` is unchanged.

## Purpose of use

`X-Purpose` is request context. It is required, normalized, and catalog-validated. Missing or unknown → 422. It is not a persisted consent record and does not grant access.

## Audit / provenance

Events: `ADVERSE_EVENT_CREATED`, `ADVERSE_EVENT_AMENDED`, `ADVERSE_EVENT_ENTERED_IN_ERROR`. Metadata is category/severity/status/version/purpose — not event display, note, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=ADVERSE_EVENT`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging redacts `code_display`, `adverse_event_display`, `adverse_event_code`, `note`, `note_text`, `adverse_event_note`, and `severity`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, event code/display, related FKs, recorded time, recorder, provenance.

Until EIE, amend may change severity, occurrence, note, record status, and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked. `app_dml` does not receive DELETE.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not an Adverse Event lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row. Concurrent amend versus EIE: final `ENTERED_IN_ERROR`, one `ADVERSE_EVENT_ENTERED_IN_ERROR` (amend audit 0 or 1 depending on winner).

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/adverse-events` | `clinical.adverse_event.create` |
| GET | `/adverse-events?patient_identity_id=` | `clinical.adverse_event.read` |
| GET | `/adverse-events/{id}` | `clinical.adverse_event.read` |
| POST | `/adverse-events/{id}/amend` | `clinical.adverse_event.update` |
| POST | `/adverse-events/{id}/entered-in-error` | `clinical.adverse_event.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0016`. Do not edit `0001`–`0015`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Adverse Event is present. Patient History, VitalSign tables, CarePlan, FHIR, AI, RAG, CDS, pharmacovigilance, and incident management remain absent. Frozen Medical Device, Procedure, Immunization, Consent, Allergy, Medication, Laboratory, Observation, and Condition remain intact.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical adverse-event rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's adverse event by UUID (org-scoped clinical read until a later PDP wave). Duplicate adverse-event facts are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. Causality, outcome, and `LIFE_THREATENING` are deferred. This gate is not a HIPAA/ISO/SOC 2 certification.
