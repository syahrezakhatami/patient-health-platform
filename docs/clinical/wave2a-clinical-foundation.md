# Wave 2A — Clinical foundation

Wave 2A adds the first clinical facts on top of the frozen Wave 1.5 identity baseline.

It is **not** the complete Wave 2 clinical core and not a FHIR implementation.

## In scope

- `Encounter` as the care episode
- Clinical note as the first authored clinical resource
- Draft / final / entered-in-error lifecycle
- Terminology stub (`system` + `code` + optional `display`)
- `CLINICIAN` role and `clinical.*` permissions
- Purpose `TREATMENT` (audit context only)

## Out of scope

Diagnosis, condition, observation, laboratory, medication, allergy, immunization, procedure, care plan, consent, FHIR Encounter/Observation APIs, AI, timeline, and documents.

## Identity binding

Clinical rows store `patient_identity_id` = `patient_identities.id`.

New encounters resolve `MERGED` identities to the canonical survivor. `RETIRED` identities cannot receive clinical records. Anonymous identities may receive emergency encounters. `patient_identity_id` is not rewritten after insert.

## Encounter

Classes: `EMER`, `IMP`, `AMB`, `VR`, `HH`.

Emergency encounters start `IN_PROGRESS`. Other classes start `PLANNED`. Anonymous identities may receive **only** `EMER` encounters.

Allowed status transitions are application-enforced. Coverage / insurance never blocks a write.

## Clinical note

Notes require an encounter. Create as `DRAFT`. Draft body may be updated. Finalize is a status change to `FINAL`. Final content is immutable (application + database trigger). `ENTERED_IN_ERROR` does not delete the row.

There is no generic `PUT /patients/{id}`.

## Authorization

PDP evaluates permission codes. Role names are never inspected.

| Permission | Intent |
|---|---|
| `clinical.encounter.create` | Open an encounter |
| `clinical.encounter.read` | Read / list by patient |
| `clinical.encounter.update_status` | Status transition |
| `clinical.note.create` | Create a draft note |
| `clinical.note.read` | Read a note |
| `clinical.note.update_draft` | Edit draft body |
| `clinical.note.finalize` | Finalize or mark entered-in-error |

Cross-organization reads return `404`. Purpose does not grant access.

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/encounters` | `clinical.encounter.create` |
| GET | `/encounters?patient_identity_id=` | `clinical.encounter.read` |
| GET | `/encounters/{id}` | `clinical.encounter.read` |
| POST | `/encounters/{id}/status` | `clinical.encounter.update_status` |
| POST | `/notes` | `clinical.note.create` |
| GET | `/notes/{id}` | `clinical.note.read` |
| POST | `/notes/{id}` | `clinical.note.update_draft` |
| POST | `/notes/{id}/finalize` | `clinical.note.finalize` |
| POST | `/notes/{id}/entered-in-error` | `clinical.note.finalize` |

List encounters requires `patient_identity_id`. There is no unbounded encounter enumeration.

## Schema

Alembic revision `20260814_0004`. Do not edit `0001`, `0002`, or `0003`.
