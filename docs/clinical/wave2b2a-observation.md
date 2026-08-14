# Wave 2B.2a — Native Observation

Wave 2B.2a adds **Observation** as a bounded native clinical measurement/finding on the frozen Wave 2B.1 Condition baseline.

It is **not** a laboratory result domain, not a FHIR Observation resource, and not a terminology server.

## Purpose

Record clinical measurements and findings such as heart rate, blood pressure components, temperature, oxygen saturation, weight, height, and similar observed values.

## Domain boundary

In scope: native `observations` table, typed values, lifecycle, API, authorization, audit, provenance, concurrency, and tests.

Out of scope: laboratory results, lab orders, specimens, panels, medication, allergy, consent, FHIR, AI/RAG, CDS, ICD/SNOMED servers.

## Data model

`observations` references `patient_identities.id`. Optional `encounter_id`. Terminology stub: `system` + `code` + optional `display`.

Value types (exactly one per row):

| Type | Required | Forbidden |
|---|---|---|
| NUMERIC | `value_numeric` + `unit` | text, boolean, coded |
| TEXT | `value_text` | numeric, boolean, coded, unit, range |
| BOOLEAN | `value_boolean` | numeric, text, coded, unit, range |
| CODED | `value_coded.system` + `code` | numeric, text, boolean, unit, range |

Optional numeric reference range. No JSON clinical payload.

Categories: `VITAL_SIGNS`, `EXAM`, `OTHER`.

## Lifecycle

Create is always `FINAL`. There is no draft.

`FINAL → AMENDED` via `POST .../amend` (value/unit/range/`effective_at` only; version increments).

`FINAL|AMENDED → ENTERED_IN_ERROR` via the dedicated void route.

No generic PUT. No DELETE.

## Identity

New writes: ACTIVE allowed; MERGED binds survivor; RETIRED 409; unknown 404; cross-org 404.

Anonymous identities may **not** receive a standalone Observation. They may receive an Observation only on an `EMER` encounter (same Wave 2A emergency rule).

Historical `patient_identity_id` is **not** rewritten after MPI merge.

## Encounter

Optional for ACTIVE patients. If supplied: must exist, same canonical patient, same org, not `CANCELLED`/`ENTERED_IN_ERROR`. Observations do not create or mutate encounters.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.observation.create` | Create |
| `clinical.observation.read` | Read / list by patient |
| `clinical.observation.update` | Amend |
| `clinical.observation.entered_in_error` | Void |

Purpose does not grant access. Registrar + `TREATMENT` is 403. `clinical.laboratory.create` remains deny-by-default.

## Purpose of use

Existing Wave 1.5 catalog plus `TREATMENT`. Required, validated, audited. Not an authorization grant.

## Audit / provenance

Events: `OBSERVATION_CREATED`, `OBSERVATION_AMENDED`, `OBSERVATION_ENTERED_IN_ERROR`. Metadata is category/status/version/purpose — not measured values, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=OBSERVATION`. `provenance_id` FK `ON DELETE RESTRICT`.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, code, value type, recorded time, recorder, provenance.

Until EIE, amend may change value fields, unit, range, `effective_at`, status (`AMENDED`), and version.

After EIE the row is frozen at API, service, and trigger. Hard DELETE is blocked.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not an Observation lock. Concurrent identical amend or double void: one 200, one 409, one matching audit row.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical observations on a merged source are not rewritten onto the survivor. Same-organization clinicians may read another patient's Observation by UUID (org-scoped clinical read until Consent). Duplicate vitals for the same code/time are allowed (no uniqueness). `app_dml` grants remain in `grant_dev_privileges.sql`. This gate is not a HIPAA/ISO/SOC 2 certification.

## Excluded future domains

Laboratory, medication, allergy, consent, FHIR Observation APIs, terminology servers, AI/RAG, CDS.
