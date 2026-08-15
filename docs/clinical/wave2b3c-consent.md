# Wave 2B.3c — Native Consent

Wave 2B.3c adds **Consent** as a bounded native clinical fact on the frozen Wave 2B.3b Allergy baseline.

It is **not** a FHIR Consent server. It is **not** RBAC, `X-Purpose`, a JWT scope, or a policy decision point. It does **not** change how Condition, Observation, Laboratory, Medication, or Allergy are authorized.

## Purpose

Record that a patient permitted or refused a defined category and scope of health-information or care use for an organization, optionally tied to an encounter.

## Domain boundary

In scope: native `consents` table, category/scope/decision/source, optional coded type, optional period and note, lifecycle (amend / revoke / entered-in-error), API, authorization, audit, provenance, concurrency, and tests.

Out of scope: FHIR Consent, PDP enforcement on other clinical reads, break-glass, patient portal, representative PII, AI/RAG/CDS, stored `EXPIRED` status, new Purpose enum values.

## Intentional differences from Allergy and Medication

Consent is a grant or refusal that can be corrected, withdrawn, or voided.

- Uses `POST .../amend` for period/note correction and `POST .../revoke` for withdrawal.
- `REVOKED` and `ENTERED_IN_ERROR` are both terminal. A revoked row cannot be entered in error.
- Anonymous identities are always rejected, including on an EMER encounter. Emergency implied consent is not stored.
- `is_effective` is computed at read time from `ACTIVE`/`AMENDED` plus the optional period. There is no stored `EXPIRED` status.

## Data model

`consents` references `patient_identities.id`. Optional `encounter_id`. Optional terminology stub: `system` + `code` + optional `display`.

| Column | Role |
|---|---|
| `category` | `TREATMENT`, `DISCLOSURE`, `PRIVACY`, or `OTHER` (immutable) |
| `scope` | `ORGANIZATION` or `ENCOUNTER` (immutable) |
| `decision` | `PERMIT` or `DENY` (immutable) |
| `source` | `PATIENT`, `REPRESENTATIVE`, or `CLINICIAN_DOCUMENTED` (immutable; no representative name) |
| `status` | `ACTIVE`, `AMENDED`, `REVOKED`, `ENTERED_IN_ERROR` |
| `period_start` / `period_end` | optional; amendable until terminal |
| `note_text` | optional; amendable until terminal; never audited |
| `revoked_at` | set once on revoke |
| `recorded_at` | immutable after insert |

No JSON clinical payload. Duplicate ACTIVE facts are allowed.

## Lifecycle

Create is always `ACTIVE`. `ACTIVE|AMENDED → AMENDED` via amend (must change a mutable field). `ACTIVE|AMENDED → REVOKED` via revoke. `ACTIVE|AMENDED → ENTERED_IN_ERROR` via the dedicated void route.

Rejected: no-op amend, double revoke, double EIE, `REVOKED → anything`, `ENTERED_IN_ERROR → anything`, `AMENDED → ACTIVE`.

No generic PUT. No DELETE.

## Identity

Canonical FK: `patient_identities.id`. ACTIVE allowed. MERGED new writes without an encounter bind the survivor. A new write with an encounter uses `encounter.patient_identity_id`. RETIRED `409`. Unknown/cross-org `404`. Anonymous writes `409` even with EMER. Historical `patient_identity_id` is not rewritten after MPI merge.

## Encounter

Optional. If supplied: must exist, same canonical patient, same org, not `CANCELLED`/`ENTERED_IN_ERROR`. Consent does not create or mutate encounters. Wrong pair `409`. Cross-org encounter `404`.

## Authorization

| Permission | Intent |
|---|---|
| `clinical.consent.create` | Create |
| `clinical.consent.read` | Read / list by patient |
| `clinical.consent.update` | Amend |
| `clinical.consent.revoke` | Revoke |
| `clinical.consent.entered_in_error` | Void |

CLINICIAN and PLATFORM_ADMIN receive the full set. ORG_ADMIN and AUDITOR receive read only. Registrar and IDENTITY_OFFICER receive none. Purpose does not grant access. Registrar + `TREATMENT` is 403.

`Wave1PolicyPDP` is unchanged. Consent records are not evaluated as authorization.

## Purpose of use

`X-Purpose` is request context. It is required and audited. It is not the Consent `decision` and does not grant access.

## Audit / provenance

Events: `CONSENT_CREATED`, `CONSENT_AMENDED`, `CONSENT_REVOKED`, `CONSENT_ENTERED_IN_ERROR`. Metadata is category/scope/decision/status/version/purpose — not note text, code display, NIK, or tokens.

Provenance reuses insert-only `clinical_provenances` with `subject_type=CONSENT`. `provenance_id` FK `ON DELETE RESTRICT`.

Logging already redacts `note_text` and `code_display`. `consent_note` is also redacted.

## Immutability

Always immutable after insert: patient, encounter, org, facility, category, scope, decision, code/display, source, recorded time, recorder, provenance.

Until revoke or EIE, amend may change period, note, record status, and version. Revoke sets `REVOKED`, `revoked_at`, and increments version. After a terminal status the row is frozen.

## Concurrency

Mutations use PostgreSQL `SELECT FOR UPDATE`. Redis is not a Consent lock. Concurrent identical amend, revoke, or EIE: one 200, one 409, one matching audit row. Concurrent amend versus revoke ends `REVOKED`. Concurrent revoke versus EIE ends with exactly one terminal status and one terminal audit.

## API

All routes remain under `/api/v1/clinical/`. There is no `/api/v2/` and no FHIR route.

| Method | Path | Permission |
|---|---|---|
| POST | `/consents` | `clinical.consent.create` |
| GET | `/consents?patient_identity_id=` | `clinical.consent.read` |
| GET | `/consents/{id}` | `clinical.consent.read` |
| POST | `/consents/{id}/amend` | `clinical.consent.update` |
| POST | `/consents/{id}/revoke` | `clinical.consent.revoke` |
| POST | `/consents/{id}/entered-in-error` | `clinical.consent.entered_in_error` |

List requires `patient_identity_id`. DELETE returns 405.

## Schema

Alembic revision `20260814_0012`. Do not edit `0001`–`0011`.

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `gsai-minio` is untouched.

## Clinical boundary

Consent is present as a persisted native fact. FHIR, AI, RAG, CDS, break-glass, and patient portal remain absent. Frozen Allergy, Medication, Laboratory, Observation, and Condition remain intact. Consent is not a PDP.

## Known limitations

Denial-audit rows still roll back with `ForbiddenError` (Wave 1 session). Historical consent rows on a merged source are not rewritten onto the survivor. Same-organization clinicians may still read another patient's clinical UUID (org-scoped read; Consent is not enforced on those paths yet). Duplicate consent facts are allowed. `app_dml` grants remain in `grant_dev_privileges.sql`. `provenance_id` is nullable with a real `ON DELETE RESTRICT` FK; the service always sets it. This gate is not a HIPAA/ISO/SOC 2 certification.
