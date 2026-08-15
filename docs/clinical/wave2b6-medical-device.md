# Wave 2B.6 — Native Medical Device

Wave 2B.6 adds **Medical Device** as a bounded native clinical fact on the frozen Wave 2B.5 Procedure baseline.

It is **not** a FHIR Device server. It is **not** inventory, asset management, scheduling, recall, Observation, Procedure, Patient History, or Adverse Event.

## Purpose

Record that a patient has, uses, or is associated with a coded medical device, with an amendable documented-fact lifecycle.

## Domain boundary

In scope: native `medical_devices` table, category `DOCUMENTED` or `REPORTED`, device terminology stub, association status, optional occurrence/note, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: UDI/serial/manufacturer/lot/expiry, FK to Procedure, performer/site/reason/outcome, inventory, maintenance, recall, registry, VitalSign tables, Patient History, Adverse Event, CarePlan, FHIR Device, CDS, Consent-as-PDP, AI/RAG.

## Intentional differences from Procedure

Medical Device is a documented patient-device association, not a performed act.

- Category is `DOCUMENTED` | `REPORTED`, not `PERFORMED` | `REPORTED`.
- Amendable `association_status` is `IN_USE` | `NO_LONGER_USED`. That is clinical association, not Medication `STOPPED` and not warehouse retirement.
- Anonymous writes follow Allergy/Medication/Immunization/Procedure: standalone 409; allowed only on a documentable `EMER` encounter.
- Consent remains a persisted fact and is not a PDP for Medical Device reads.

Record status follows Allergy/Immunization/Procedure: create `ACTIVE`, first successful amend → `AMENDED`, dedicated void → `ENTERED_IN_ERROR`.

## Data model

`medical_devices` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `category` | `DOCUMENTED` or `REPORTED` (immutable) |
| `code_*` | device coding (immutable) |
| `association_status` | `IN_USE` or `NO_LONGER_USED` (amendable) |
| `occurrence_at` | optional; amendable until EIE |
| `note_text` | optional; amendable until terminal; never audited |
| `status` | `ACTIVE`, `AMENDED`, `ENTERED_IN_ERROR` |
| `recorded_at` | immutable after insert |

No JSON clinical payload. No UDI, serial, manufacturer, lot, Procedure FK, performer, site, reason, or outcome columns.

## Lifecycle

Create is always `ACTIVE`. Default `association_status` is `IN_USE`. `ACTIVE|AMENDED → AMENDED` via amend (must change a mutable field). `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route.

Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, `ENTERED_IN_ERROR → anything`.

No generic PUT. No DELETE. A corrected association after EIE is a new row.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind the survivor. New writes with encounter use the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`.

Anonymous identities may **not** receive a standalone Medical Device. They may receive a Medical Device only on an `EMER` encounter.

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Cross-org encounter `404`. Wrong pair `409`. Medical Device does not mutate encounters.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.medical_device.create` | Create |
| `clinical.medical_device.read` | Read / list by patient |
| `clinical.medical_device.update` | Amend |
| `clinical.medical_device.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar and IDENTITY_OFFICER receive none. Purpose does not grant access. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default.

## Purpose of use

`X-Purpose` is request context. It is required and audited. It is not a persisted consent record and does not grant access.

## Audit / provenance

Events: `MEDICAL_DEVICE_CREATED`, `MEDICAL_DEVICE_AMENDED`, `MEDICAL_DEVICE_ENTERED_IN_ERROR`. Metadata is category/status/association_status/version/purpose — not device display, note, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=MEDICAL_DEVICE`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging redacts `code_display`, `device_display`, `device_code`, `note`, `note_text`, and `medical_device_note`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, device code/display, recorded time, recorder, provenance.

Until EIE, amend may change association status, occurrence, note, record status, and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked. `app_dml` does not receive DELETE.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a Medical Device lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row. Concurrent amend versus EIE: final `ENTERED_IN_ERROR`, one `MEDICAL_DEVICE_ENTERED_IN_ERROR` (amend audit 0 or 1 depending on winner).

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/medical-devices` | `clinical.medical_device.create` |
| GET | `/medical-devices?patient_identity_id=` | `clinical.medical_device.read` |
| GET | `/medical-devices/{id}` | `clinical.medical_device.read` |
| POST | `/medical-devices/{id}/amend` | `clinical.medical_device.update` |
| POST | `/medical-devices/{id}/entered-in-error` | `clinical.medical_device.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0015`. Do not edit `0001`–`0014`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Medical Device is present. Patient History, Adverse Event, VitalSign tables, CarePlan, FHIR, AI, RAG, CDS remain absent. Frozen Procedure, Immunization, Consent, Allergy, Medication, Laboratory, Observation, and Condition remain intact.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical medical-device rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's medical device by UUID (org-scoped clinical read until a later PDP wave). Duplicate device-association facts are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. UDI, serial, manufacturer, lot, and Procedure FK are deferred. This gate is not a HIPAA/ISO/SOC 2 certification.
