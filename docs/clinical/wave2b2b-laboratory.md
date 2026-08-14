# Wave 2B.2b — Native Laboratory

Wave 2B.2b adds **Laboratory** as a bounded native clinical domain on the frozen Wave 2B.2a Observation baseline.

It is **not** a FHIR DiagnosticReport / ServiceRequest / Specimen / Observation resource, and not a terminology server.

## Purpose

Record laboratory orders, collected specimens, and typed laboratory results as three explicit relational facts.

## Domain boundary

In scope: native `laboratory_orders`, `laboratory_specimens`, and `laboratory_results`; typed result values; lifecycles; APIs; authorization; audit; provenance; concurrency; tests.

Out of scope: medication, allergy, consent, FHIR, AI/RAG, CDS, ICD/SNOMED/LOINC servers, panels as a separate aggregate, and Wave 2B.3.

## Data model

All three tables reference `patient_identities.id`. Optional `encounter_id` on the order; specimen and result inherit patient and encounter from the order. Terminology stub: `system` + `code` + optional `display`.

Result value types (exactly one per row):

| Type | Required | Forbidden |
|---|---|---|
| NUMERIC | `value_numeric` + `unit` | text, boolean, coded |
| TEXT | `value_text` | numeric, boolean, coded, unit, range |
| BOOLEAN | `value_boolean` | numeric, text, coded, unit, range |
| CODED | `value_coded.system` + `code` | numeric, text, boolean, unit, range |

Optional numeric reference range. Optional interpretation: `NORMAL`, `ABNORMAL`, `CRITICAL`. No JSON clinical payload.

Specimen types: `BLOOD`, `URINE`, `SWAB`, `OTHER`.

## Lifecycle

### Order

Create is always `REGISTERED`.

`REGISTERED → IN_PROGRESS` automatically when the first specimen is collected.

`REGISTERED → CANCELLED` via `POST .../orders/{id}/cancel`. Cancel is not allowed after `IN_PROGRESS`.

`REGISTERED|IN_PROGRESS → ENTERED_IN_ERROR` via the dedicated void route.

There is no `COMPLETED` order state.

### Specimen

Create is always `COLLECTED`.

`COLLECTED → REJECTED` via `POST .../specimens/{id}/reject`.

`COLLECTED → ENTERED_IN_ERROR` via the dedicated void route.

Rejected and entered-in-error specimens cannot receive results.

### Result

Create is always `FINAL`. There is no draft.

`FINAL → AMENDED` via `POST .../amend` (value/unit/range/`effective_at`/interpretation; value type is immutable; version increments).

`FINAL|AMENDED → ENTERED_IN_ERROR` via the dedicated void route.

No generic PUT. No DELETE. No generic status mutation endpoint.

Terminal states are immutable.

## Identity

New writes: ACTIVE allowed; MERGED binds survivor; RETIRED 409; unknown 404; cross-org 404.

Anonymous identities may **not** receive a standalone laboratory order. They may receive an order only on an `EMER` encounter (same Wave 2A emergency rule). Specimen and result inherit that binding from the order.

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients on the order. If supplied: must exist, same canonical patient, same org, not `CANCELLED`/`ENTERED_IN_ERROR`. Wrong patient/encounter is 409. Cross-org encounter is 404. Laboratory resources do not create or mutate encounters.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.laboratory.order.create` | Create order |
| `clinical.laboratory.order.read` | Read / list orders |
| `clinical.laboratory.order.update` | Cancel a REGISTERED order |
| `clinical.laboratory.order.entered_in_error` | Void order |
| `clinical.laboratory.specimen.create` | Collect specimen |
| `clinical.laboratory.specimen.read` | Read / list specimens |
| `clinical.laboratory.specimen.update` | Reject specimen |
| `clinical.laboratory.specimen.entered_in_error` | Void specimen |
| `clinical.laboratory.result.create` | Create result |
| `clinical.laboratory.result.read` | Read / list results |
| `clinical.laboratory.result.update` | Amend result |
| `clinical.laboratory.result.entered_in_error` | Void result |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar receives none. Purpose does not grant access. Registrar + `TREATMENT` is 403. `clinical.laboratory.create` and `clinical.medication.create` remain deny-by-default.

## Purpose of use

Existing Wave 1.5 catalog plus `TREATMENT`. Required, validated, audited. Not an authorization grant.

## Audit / provenance

Events: `LAB_ORDER_CREATED`, `LAB_ORDER_IN_PROGRESS`, `LAB_ORDER_CANCELLED`, `LAB_ORDER_ENTERED_IN_ERROR`, `LAB_SPECIMEN_COLLECTED`, `LAB_SPECIMEN_REJECTED`, `LAB_SPECIMEN_ENTERED_IN_ERROR`, `LAB_RESULT_CREATED`, `LAB_RESULT_AMENDED`, `LAB_RESULT_ENTERED_IN_ERROR`.

Metadata is status/type/purpose/version — not measured values, NIK, BPJS, secrets, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type` `LABORATORY_ORDER`, `LABORATORY_SPECIMEN`, or `LABORATORY_RESULT`. `provenance_id` FK `ON DELETE RESTRICT`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, codes, recorded/collected/ordered time, recorder, provenance, result value type.

Until a terminal state, allowed mutations are the documented status transitions plus result amend fields.

After a terminal state the row is frozen at API, service, and trigger. Hard DELETE is blocked.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a laboratory lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row. Concurrent amend versus entered-in-error ends `ENTERED_IN_ERROR`.

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/`.

Expected errors: 401 unauthenticated, 403 unauthorized, 404 unknown/cross-org, 409 conflict/invalid transition/identity, 422 validation/purpose, 405 DELETE.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical laboratory rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's laboratory record by UUID (org-scoped clinical read until Consent). Duplicate orders/results for the same code/time are allowed (no uniqueness). Result amend/EIE does not re-validate parent order/specimen terminal state; each resource has an independent lifecycle. `app_dml` grants remain in `grant_dev_privileges.sql`. This gate is not a HIPAA/ISO/SOC 2 certification.

## Excluded future domains

Medication, allergy, consent, FHIR laboratory APIs, terminology servers, AI/RAG, CDS.
