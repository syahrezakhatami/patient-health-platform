# Wave 2B.4 — Native Immunization

Wave 2B.4 adds **Immunization** as a bounded native clinical fact on the frozen Wave 2B.3c Consent baseline.

It is **not** a FHIR Immunization server. It is **not** a schedule, forecast, inventory, lot-recall, or national-registry subdomain. It is **not** CDS.

## Purpose

Record that a patient received or reported a coded vaccination, with an amendable documented-fact lifecycle.

## Domain boundary

In scope: native `immunizations` table, category `ADMINISTERED` or `REPORTED`, vaccine terminology stub, optional occurrence/route/site/note, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: Procedure, CarePlan, FHIR Immunization, scheduling, dose forecasting, series management, inventory, lot recall, national registry sync, CDS, Consent-as-PDP, AI/RAG.

## Intentional differences from Allergy and Consent

Immunization is a documented vaccination fact, not a grant/refusal and not an allergen record.

- Uses `POST .../amend` for occurrence/route/site/note correction, like Allergy.
- No revoke. `ENTERED_IN_ERROR` is the only terminal status.
- Anonymous writes follow Allergy/Medication: standalone 409; allowed only on a documentable `EMER` encounter.
- Consent remains a persisted fact and is not a PDP for Immunization reads.

Record status follows Allergy: create `ACTIVE`, first successful amend → `AMENDED`, dedicated void → `ENTERED_IN_ERROR`.

## Data model

`immunizations` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `category` | `ADMINISTERED` or `REPORTED` (immutable) |
| `code_*` | vaccine coding (immutable) |
| `occurrence_at` | optional; amendable until EIE |
| `route` | optional `IM`, `SC`, `ORAL`, `INTRANASAL`, `OTHER` (amendable) |
| `site` | optional `LEFT_ARM`, `RIGHT_ARM`, `LEFT_THIGH`, `RIGHT_THIGH`, `OTHER` (amendable) |
| `note_text` | optional; amendable until terminal; never audited |
| `status` | `ACTIVE`, `AMENDED`, `ENTERED_IN_ERROR` |
| `recorded_at` | immutable after insert |

No JSON clinical payload. No lot, manufacturer, series, or schedule columns.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via amend (must change a mutable field). `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route.

Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, `ENTERED_IN_ERROR → anything`.

No generic PUT. No DELETE. A corrected vaccination after EIE is a new row.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind the survivor. New writes with encounter use the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`.

Anonymous identities may **not** receive a standalone Immunization. They may receive an Immunization only on an `EMER` encounter.

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Cross-org encounter `404`. Wrong pair `409`. Immunization does not mutate encounters.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.immunization.create` | Create |
| `clinical.immunization.read` | Read / list by patient |
| `clinical.immunization.update` | Amend |
| `clinical.immunization.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar and IDENTITY_OFFICER receive none. Purpose does not grant access. `clinical.diagnosis.create` and `clinical.procedure.create` remain deny-by-default.

## Purpose of use

`X-Purpose` is request context. It is required and audited. It is not a persisted consent record and does not grant access.

## Audit / provenance

Events: `IMMUNIZATION_CREATED`, `IMMUNIZATION_AMENDED`, `IMMUNIZATION_ENTERED_IN_ERROR`. Metadata is category/status/version/purpose — not vaccine display, note, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=IMMUNIZATION`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging redacts `code_display`, `vaccine_display`, `note`, `note_text`, and `immunization_note`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, vaccine code/display, recorded time, recorder, provenance.

Until EIE, amend may change occurrence, route, site, note, record status, and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked. `app_dml` does not receive DELETE.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not an Immunization lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row. Concurrent amend versus EIE: final `ENTERED_IN_ERROR`, one `IMMUNIZATION_ENTERED_IN_ERROR` (amend audit 0 or 1 depending on winner).

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/immunizations` | `clinical.immunization.create` |
| GET | `/immunizations?patient_identity_id=` | `clinical.immunization.read` |
| GET | `/immunizations/{id}` | `clinical.immunization.read` |
| POST | `/immunizations/{id}/amend` | `clinical.immunization.update` |
| POST | `/immunizations/{id}/entered-in-error` | `clinical.immunization.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0013`. Do not edit `0001`–`0012`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Immunization is present. Procedure, CarePlan, FHIR, AI, RAG, CDS remain absent. Frozen Consent, Allergy, Medication, Laboratory, Observation, and Condition remain intact.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical immunization rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's immunization by UUID (org-scoped clinical read until a later PDP wave). Duplicate immunization facts are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. This gate is not a HIPAA/ISO/SOC 2 certification.
