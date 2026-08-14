# Wave 2B.1 — Diagnosis / Condition

Wave 2B.1 adds **Condition** as the first coded clinical fact on the frozen Wave 2A foundation.

It is **not** a FHIR Condition server, not a terminology server, and not the rest of Wave 2B.

## In scope

- Condition as a native clinical record (`conditions`)
- Categories: `PROBLEM_LIST_ITEM`, `ENCOUNTER_DIAGNOSIS`
- Terminology stub for the diagnosis code (`system` + `code` + optional `display`)
- Clinical status and verification status
- `ENTERED_IN_ERROR` immutability (API + service + database trigger)
- Identity binding to `patient_identities.id`
- CLINICIAN permissions `clinical.condition.*`

## Out of scope

Observation, laboratory, medication, allergy, immunization, procedure, care plan, consent, FHIR Condition APIs, ICD/SNOMED servers, AI/RAG, clinical decision support.

## Identity

New conditions resolve `MERGED` identities to the canonical survivor. `RETIRED` identities are rejected. Unknown identities return `404`. Cross-organization reads return `404`.

Anonymous identities may receive **encounter diagnosis on an EMER encounter only**. Problem-list conditions are not allowed on anonymous identities.

Immutable after insert (API has no mutation path; the database trigger rejects SQL bypass):

- `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`
- category, code/system/display
- `onset_at`, `abatement_at`, `recorded_at`, `recorder_id`, `provenance_id`

Mutable until `ENTERED_IN_ERROR`, via dedicated endpoints only: `clinical_status` and `verification_status`. `updated_at` may change as row metadata. There is no API to edit onset, abatement, recorded time, facility, or provenance after create. Supply onset/abatement at create if known; later resolution is a status change, not a period rewrite.

Merge does not rewrite historical condition rows. `provenance_id` references `clinical_provenances.id` (`ON DELETE RESTRICT`). Encounter and note `provenance_id` columns remain Wave 2A (no FK).

## Lifecycle

Clinical status:

`ACTIVE | RECURRENCE | RELAPSE | INACTIVE | REMISSION | RESOLVED`

Verification status:

`UNCONFIRMED | PROVISIONAL | DIFFERENTIAL | CONFIRMED | REFUTED | ENTERED_IN_ERROR`

Create defaults: `ACTIVE` + `CONFIRMED`. Create cannot start as `ENTERED_IN_ERROR`.

`ENCOUNTER_DIAGNOSIS` requires an encounter that is not `CANCELLED` or `ENTERED_IN_ERROR`. Code cannot be edited; void with entered-in-error and record a new condition.

Hard DELETE is blocked. There is no DELETE API.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.condition.create` | Create a condition |
| `clinical.condition.read` | Read / list by patient |
| `clinical.condition.update` | Change clinical or verification status |
| `clinical.condition.entered_in_error` | Void a condition |

`clinical.diagnosis.create` remains unknown and deny-by-default. Purpose does not grant access. TREATMENT is audit context only.

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/conditions` | `clinical.condition.create` |
| GET | `/conditions?patient_identity_id=` | `clinical.condition.read` |
| GET | `/conditions/{id}` | `clinical.condition.read` |
| POST | `/conditions/{id}/status` | `clinical.condition.update` |
| POST | `/conditions/{id}/entered-in-error` | `clinical.condition.entered_in_error` |

List requires `patient_identity_id`. There is no unbounded condition enumeration.

## Schema

Alembic revision `20260814_0006`. Do not edit `0001`–`0005`.
