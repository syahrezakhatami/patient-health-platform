# Wave 2B.3a — Native Medication

Wave 2B.3a adds **Medication** as a bounded native clinical fact on the frozen Wave 2B.2b Laboratory baseline.

It is **not** a FHIR MedicationRequest, MedicationAdministration, MedicationDispense, or MedicationStatement server. It is **not** a pharmacy inventory, catalog, or administration subdomain.

## Purpose

Record that a patient is prescribed or reported to be taking a coded medication, with an explicit lifecycle.

## Domain boundary

In scope: native `medications` table, coded drug (terminology stub), optional structured dose/route, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: medication administration, dispense, request/order chain, inventory, allergy, consent, FHIR, AI/RAG, CDS, national drug catalog servers.

Prescribed ≠ reported is modeled as `category`. Administration and dispense are not implied by this record.

## Data model

`medications` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `category` | `PRESCRIBED` or `REPORTED` |
| `status` | `ACTIVE`, `STOPPED`, `ENTERED_IN_ERROR` |
| `dose_numeric` + `dose_unit` | both present or both null |
| `route` | optional: `ORAL`, `IV`, `IM`, `SC`, `TOPICAL`, `INHALED`, `OTHER` |
| `started_at` | optional; immutable after insert |
| `stopped_at` | set only by stop; immutable once set |

No JSON clinical payload. No generic clinical_records table.

## Lifecycle

Create is always `ACTIVE`. There is no draft and no `COMPLETED`.

`ACTIVE → STOPPED` via `POST .../stop` (`stopped_at` set, version increments).

`ACTIVE|STOPPED → ENTERED_IN_ERROR` via the dedicated void route.

Stopped medications cannot restart. Record a new medication if therapy resumes.

No-op stop of an already stopped medication is `409`. Entered-in-error is terminal.

No generic PUT. No DELETE.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown `404`. Cross-org `404`.

Anonymous identities may **not** receive a standalone Medication. They may receive a Medication only on an `EMER` encounter (same Wave 2A emergency rule).

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: must exist, same canonical patient, same org, not `CANCELLED`/`ENTERED_IN_ERROR`. Medications do not create or mutate encounters. Wrong patient pair `409`. Cross-org encounter `404`.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.medication.create` | Create |
| `clinical.medication.read` | Read / list by patient |
| `clinical.medication.update` | Stop |
| `clinical.medication.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar receives none. Purpose does not grant access. Registrar + `TREATMENT` is 403. `clinical.allergy.create` and `clinical.diagnosis.create` remain deny-by-default.

## Purpose of use

`X-Purpose` is request context. It is required and audited. It is not a persisted consent record and does not grant access.

## Audit / provenance

Events: `MEDICATION_CREATED`, `MEDICATION_STOPPED`, `MEDICATION_ENTERED_IN_ERROR`. Metadata is category/status/version/purpose — not drug names, doses, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=MEDICATION`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging redacts `dose_numeric`, `dose_unit`, `dose`, and `code_display`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, code, dose, route, started time, recorded time, recorder, provenance.

Until EIE, stop may set status `STOPPED`, `stopped_at`, and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked. `app_dml` does not receive DELETE.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a Medication lock. Concurrent identical stop or double void: one 200, one 409, one matching audit row.

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/medications` | `clinical.medication.create` |
| GET | `/medications?patient_identity_id=` | `clinical.medication.read` |
| GET | `/medications/{id}` | `clinical.medication.read` |
| POST | `/medications/{id}/stop` | `clinical.medication.update` |
| POST | `/medications/{id}/entered-in-error` | `clinical.medication.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0010`. Do not edit `0001`–`0009`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Medication is present. Allergy, consent, FHIR, AI, RAG, CDS remain absent.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical medication rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's medication by UUID (org-scoped clinical read until Consent). Duplicate medication facts for the same code/time are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. This gate is not a HIPAA/ISO/SOC 2 certification.
