# Wave 2B.3b — Native Allergy

Wave 2B.3b adds **Allergy** as a bounded native clinical fact on the frozen Wave 2B.3a Medication baseline.

It is **not** a FHIR AllergyIntolerance server. It is **not** a medication-order, dispense, or administration record. It is **not** Consent.

## Purpose

Record that a patient has a documented allergy or intolerance, with explicit clinical status, verification, optional reaction/severity, and an amendable lifecycle.

## Domain boundary

In scope: native `allergies` table, coded allergen (terminology stub), clinical/verification status, optional criticality/severity/reaction, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: Consent, FHIR AllergyIntolerance, CDS rules, AI/RAG, medication changes, allergy desensitization protocols.

## Intentional differences from Medication

Medication models a therapy course (`ACTIVE → STOPPED`). Allergy models a documented fact that can be corrected.

- Allergy uses `POST .../amend`, not `POST .../stop`.
- Allergy has `clinical_status` (`ACTIVE|INACTIVE`) and `verification_status` (`UNCONFIRMED|CONFIRMED|REFUTED`) in addition to record `status`.
- Allergy category is allergen class (`DRUG|FOOD|ENVIRONMENT|OTHER`), not prescribed vs reported.
- Reaction/severity/criticality replace dose/route.

Record status follows Observation: create `ACTIVE`, first successful amend → `AMENDED`, dedicated void → `ENTERED_IN_ERROR`.

## Data model

`allergies` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `category` | `DRUG`, `FOOD`, `ENVIRONMENT`, or `OTHER` (immutable) |
| `status` | record lifecycle: `ACTIVE`, `AMENDED`, `ENTERED_IN_ERROR` |
| `clinical_status` | `ACTIVE` or `INACTIVE` (amendable) |
| `verification_status` | `UNCONFIRMED`, `CONFIRMED`, or `REFUTED` (amendable) |
| `criticality` | optional `LOW`, `HIGH`, `UNABLE_TO_ASSESS` (amendable) |
| `severity` | optional `MILD`, `MODERATE`, `SEVERE` (amendable) |
| `reaction_*` | optional coded manifestation; system+code together or neither (amendable) |
| `onset_at` | optional; amendable as a clinical correction |
| `recorded_at` | immutable after insert |

No JSON clinical payload. No generic clinical_records table.

## Lifecycle

Create is always record `status=ACTIVE`. Default `clinical_status=ACTIVE` and `verification_status=UNCONFIRMED` unless supplied. There is no draft and no `COMPLETED`.

`ACTIVE|AMENDED → AMENDED` via `POST .../amend`. Amend must change at least one mutable field; otherwise `409`.

`ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route.

Rejected: `ENTERED_IN_ERROR → anything`, `AMENDED → ACTIVE`, no-op amend, double void.

No generic PUT. No DELETE.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes bind the survivor. RETIRED `409`. Unknown `404`. Cross-org `404`.

Anonymous identities may **not** receive a standalone Allergy. They may receive an Allergy only on an `EMER` encounter (same Wave 2A emergency rule).

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: must exist, same canonical patient, same org, not `CANCELLED`/`ENTERED_IN_ERROR`. Allergies do not create or mutate encounters. Wrong patient pair `409`. Cross-org encounter `404`.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.allergy.create` | Create |
| `clinical.allergy.read` | Read / list by patient |
| `clinical.allergy.update` | Amend |
| `clinical.allergy.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar receives none. Purpose does not grant access. Registrar + `TREATMENT` is 403. `clinical.consent.create` and `clinical.diagnosis.create` remain deny-by-default.

## Purpose of use

`X-Purpose` is request context. It is required and audited. It is not a persisted consent record and does not grant access.

## Audit / provenance

Events: `ALLERGY_CREATED`, `ALLERGY_AMENDED`, `ALLERGY_ENTERED_IN_ERROR`. Metadata is category/status/clinical_status/verification_status/version/purpose — not allergen names, reaction details, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=ALLERGY`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging redacts `code_display`, `reaction_display`, `reaction_code`, `reaction_code_system`, `reaction_code_display`, `severity`, and `criticality`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, allergen code/display, recorded time, recorder, provenance.

Until EIE, amend may change clinical/verification status, criticality, severity, reaction, onset, record status, and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked. `app_dml` does not receive DELETE.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not an Allergy lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row. Concurrent amend versus EIE: final `ENTERED_IN_ERROR`, one `ALLERGY_ENTERED_IN_ERROR` (amend audit 0 or 1 depending on winner).

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/allergies` | `clinical.allergy.create` |
| GET | `/allergies?patient_identity_id=` | `clinical.allergy.read` |
| GET | `/allergies/{id}` | `clinical.allergy.read` |
| POST | `/allergies/{id}/amend` | `clinical.allergy.update` |
| POST | `/allergies/{id}/entered-in-error` | `clinical.allergy.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0011`. Do not edit `0001`–`0010`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Allergy is present. Consent, FHIR, AI, RAG, CDS remain absent. Frozen Medication, Laboratory, Observation, and Condition remain intact.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical allergy rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's allergy by UUID (org-scoped clinical read until Consent). Duplicate allergy facts for the same allergen are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. This gate is not a HIPAA/ISO/SOC 2 certification.
