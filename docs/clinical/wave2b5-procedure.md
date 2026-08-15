# Wave 2B.5 — Native Procedure

Wave 2B.5 adds **Procedure** as a bounded native clinical fact on the frozen Wave 2B.4 Immunization baseline.

It is **not** a FHIR Procedure server. It is **not** an order, schedule, CarePlan, inventory, or CDS subdomain.

## Purpose

Record that a coded procedure was performed or reported as performed, with an amendable documented-fact lifecycle.

## Domain boundary

In scope: native `procedures` table, category `PERFORMED` or `REPORTED`, procedure terminology stub, optional occurrence/note, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: ordered/planned procedure, performer aggregate, body site, reason/outcome, CarePlan, FHIR Procedure, scheduling, inventory, registry, CDS, Consent-as-PDP, AI/RAG.

## Intentional differences from Immunization

Procedure is a documented act, not a vaccination.

- No route or site columns (deferred; no procedure anatomy catalog).
- Category is `PERFORMED` | `REPORTED`, not `ADMINISTERED` | `REPORTED`.
- Anonymous writes follow Allergy/Medication/Immunization: standalone 409; allowed only on a documentable `EMER` encounter.
- Consent remains a persisted fact and is not a PDP for Procedure reads.

Record status follows Allergy/Immunization: create `ACTIVE`, first successful amend → `AMENDED`, dedicated void → `ENTERED_IN_ERROR`.

## Data model

`procedures` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `category` | `PERFORMED` or `REPORTED` (immutable) |
| `code_*` | procedure coding (immutable) |
| `occurrence_at` | optional; amendable until EIE |
| `note_text` | optional; amendable until terminal; never audited |
| `status` | `ACTIVE`, `AMENDED`, `ENTERED_IN_ERROR` |
| `recorded_at` | immutable after insert |

No JSON clinical payload. No performer, site, reason, outcome, lot, or schedule columns.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via amend (must change a mutable field). `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route.

Rejected: no-op amend, double EIE, `AMENDED → ACTIVE`, `ENTERED_IN_ERROR → anything`.

No generic PUT. No DELETE. A corrected procedure after EIE is a new row.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without encounter bind the survivor. New writes with encounter use the frozen same-patient check. RETIRED `409`. Unknown/cross-org `404`.

Anonymous identities may **not** receive a standalone Procedure. They may receive a Procedure only on an `EMER` encounter.

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: same patient, same org, documentable. CANCELLED and ENTERED_IN_ERROR encounters rejected. Cross-org encounter `404`. Wrong pair `409`. Procedure does not mutate encounters.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.procedure.create` | Create |
| `clinical.procedure.read` | Read / list by patient |
| `clinical.procedure.update` | Amend |
| `clinical.procedure.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar and IDENTITY_OFFICER receive none. Purpose does not grant access. `clinical.diagnosis.create` and `clinical.care_plan.create` remain deny-by-default.

## Purpose of use

`X-Purpose` is request context. It is required and audited. It is not a persisted consent record and does not grant access.

## Audit / provenance

Events: `PROCEDURE_CREATED`, `PROCEDURE_AMENDED`, `PROCEDURE_ENTERED_IN_ERROR`. Metadata is category/status/version/purpose — not procedure display, note, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=PROCEDURE`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging redacts `code_display`, `procedure_display`, `procedure_code`, `note`, `note_text`, and `procedure_note`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, procedure code/display, recorded time, recorder, provenance.

Until EIE, amend may change occurrence, note, record status, and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked. `app_dml` does not receive DELETE.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a Procedure lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row. Concurrent amend versus EIE: final `ENTERED_IN_ERROR`, one `PROCEDURE_ENTERED_IN_ERROR` (amend audit 0 or 1 depending on winner).

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/procedures` | `clinical.procedure.create` |
| GET | `/procedures?patient_identity_id=` | `clinical.procedure.read` |
| GET | `/procedures/{id}` | `clinical.procedure.read` |
| POST | `/procedures/{id}/amend` | `clinical.procedure.update` |
| POST | `/procedures/{id}/entered-in-error` | `clinical.procedure.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0014`. Do not edit `0001`–`0013`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Procedure is present. CarePlan, FHIR, AI, RAG, CDS remain absent. Frozen Immunization, Consent, Allergy, Medication, Laboratory, Observation, and Condition remain intact.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical procedure rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's procedure by UUID (org-scoped clinical read until a later PDP wave). Duplicate procedure facts are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. Performer, site, reason, and outcome are deferred. This gate is not a HIPAA/ISO/SOC 2 certification.
