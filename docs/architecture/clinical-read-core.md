# Clinical Read Core — implementation

**Date:** 2026-08-26  
**Kind:** Implementation (not freeze, not hardening)  
**Status:** IMPLEMENTED  
**Hardening:** NOT STARTED  
**Frozen:** NO  
**Baseline:** `product-access-tenancy-foundation-frozen` / `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716`  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** NOT CREATED  
**Wave1PolicyPDP:** FROZEN — file not edited  
**ProductAccessPDP:** unchanged `default_pdp()`

This document records what was implemented. The authoritative contract remains `docs/architecture/clinical-read-core-design.md`. This pass does not start Healthcare Web, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, or AI.

Companion gate: `docs/gates/clinical-read-core-implementation-gate.md`.

Clinical Read Core is a **read-only** in-process query module. It is not a clinical source of truth, `patient_histories`, a materialized store, FHIR, a Redis clinical cache, a command API, or a CQRS framework.

---

## Baseline

Verified before production-code changes and still true of published `main`:

| Item | Value |
|---|---|
| HEAD | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` |
| Tag | Annotated `product-access-tenancy-foundation-frozen` peels to HEAD |
| Parent | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Branch | `main` == `origin/main` |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Does not exist |
| `Wave1PolicyPDP` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `ProductAccessPDP` | Untouched |
| `docker-compose.yml` | Untouched |
| Production rate limit | `120` req/min (unchanged) |

Working tree after this pass is **uncommitted** (no commit, tag, or push).

---

## Module files

```
backend/app/modules/clinical_read/
  __init__.py
  application/
    schemas.py          # staff read DTOs
    presenters.py       # frozen model → DTO
    services.py         # ClinicalReadService
  domain/
    enums.py            # ChartSection, TimelineSourceType, CLINICAL_CHART_ACCESSED
    catalog.py          # closed section map, permissions, timestamp map
    age.py              # UTC Gregorian age_years
    cursor.py           # opaque cursor encode/decode
    timeline.py         # stable order + k-way page
  infrastructure/
    queries.py          # ClinicalReadQueryRepository
backend/app/api/v1/clinical_read.py
backend/app/api/v1/router.py          # additive include only
```

Frozen command repositories, `Wave1PolicyPDP`, and `ProductAccessPDP` were not rewritten.

---

## Routes

Staff only. Audience `php-api` via `require_staff_audience`. Prefix `/api/v1`.

| Method | Path |
|---|---|
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/summary` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/timeline` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/sections/{section}` |

Not created: `/api/v2`, `/fhir`, `/api/v1/patient/...` staff chart, `/patient-history`. Frozen command APIs are unchanged.

Query `facility_id` is bound as FastAPI `query_facility_id` with `Query(alias="facility_id")` so it does not collide with header `X-Facility-Id`.

---

## Canonical identity

Request identity UUID → MPI lookup → org visibility (provenance org **or** identifier org; no platform-scope bypass) → `RETIRED` 409 → `resolve_canonical_identity` → cluster expansion.

Merged source X→Y: request with X returns canonical Y. No HTTP redirect.

Unknown / cross-org: 404 `"Patient identity not found"` (indistinguishable).

Every response includes `requested_patient_identity_id` and `canonical_patient_identity_id`.

---

## Cluster expansion

`MpiRepository.list_cluster_identity_ids(canonical)`: membership `ACTIVE` + `MERGED_IN`; `UNMERGED` excluded.

All clinical fact queries:

```
organization_id = request organization
AND patient_identity_id IN cluster_ids
```

Historical source rows are not rewritten. Physical-id dedupe only (`_unique` by fact `id`). No semantic merge.

MPI cluster never overrides tenant isolation. Hospital A never receives Hospital B facts for the same canonical person.

---

## Organization / facility

Organization remains the tenant. `X-Organization-Id` required.

Chart default grain: organization-wide.

| Input | Effect |
|---|---|
| `X-Facility-Id` absent | Frozen PDP facility allow-list not applied. Chart still org-wide |
| `X-Facility-Id` present | Frozen Product Access validation. Foreign UUID → 404 conceal. Chart still org-wide |
| Query `facility_id` | Filter only. Not a grant. Foreign / other-org / not-in-actor-allow-list → 404 conceal |

`NULL` facility facts: included org-wide; excluded when a facility filter is set.

---

## Chart shell authorization

Required: staff principal, `php-api`, organization membership, valid purpose, `mpi.identity.read`, org-visible identity.

`PATIENT_ACCESS` on these staff routes: 403 `purpose_principal_mismatch` **before** patient lookup.

No `clinical.chart.read` permission.

Unauthorized section keys: **omit** from `authorized_sections`. Direct section URL: **403**. Never serialize then hide.

Role behavior is permission-driven only (no role-name checks, no NURSE):

| Catalog role | Shell | Sections |
|---|---|---|
| CLINICIAN | yes | all clinical sections |
| ORG_ADMIN | yes | all frozen clinical reads (not tightened) |
| AUDITOR | yes | all frozen clinical reads |
| REGISTRAR | yes | `encounters` only |
| IDENTITY_OFFICER | yes | none (header/MPI only) |

---

## Section catalog

Closed `ChartSection` enum. Unknown slug → 404 `"Resource not found"`.

| Slug | Source | Read permission(s) | Primary time | Fallback |
|---|---|---|---|---|
| `encounters` | encounters | `clinical.encounter.read` | `started_at` | — |
| `notes` | clinical_notes | `clinical.note.read` | `authored_at` | — |
| `conditions` | conditions | `clinical.condition.read` | `onset_at` | `recorded_at` |
| `observations` | observations | `clinical.observation.read` | `effective_at` | `recorded_at` |
| `laboratory` | orders + specimens + results | three lab read permissions | order `ordered_at` / specimen `collected_at` / result `effective_at` | result `recorded_at` |
| `medications` | medications | `clinical.medication.read` | `started_at` | `recorded_at` |
| `allergies` | allergies | `clinical.allergy.read` | `onset_at` | `recorded_at` |
| `consents` | consents | `clinical.consent.read` | `period_start` | `recorded_at` |
| `immunizations` | immunizations | `clinical.immunization.read` | `occurrence_at` | `recorded_at` |
| `procedures` | procedures | `clinical.procedure.read` | `occurrence_at` | `recorded_at` |
| `medical-devices` | medical_devices | `clinical.medical_device.read` | `occurrence_at` | `recorded_at` |
| `adverse-events` | adverse_events | `clinical.adverse_event.read` | `occurrence_at` | `recorded_at` |
| `family-histories` | family_histories | `clinical.family_history.read` | `occurrence_at` | `recorded_at` |

Laboratory: section URL allowed if **at least one** of `clinical.laboratory.order.read`, `.specimen.read`, `.result.read` is present. Nested DTO includes only authorized layers. Page of orders when order-read is present; otherwise specimens or results as the top-level collection.

Vitals remain Observation (`?category=VITAL_SIGNS`). Diagnosis remains Condition.

---

## Patient header

Derived at read time from canonical identity + org-scoped MRNs. Not persisted.

Includes: requested/canonical ids, lifecycle, identity kind, display label, given/family name, birth date, `age_years` (UTC Gregorian date, birthday-not-yet adjustment; null if no DOB), administrative sex, org MRN list, optional `selected_encounter` when `encounter_id` is requested and `clinical.encounter.read` is present.

`documented_allergy_exists`: EXISTS of Allergy facts `status != ENTERED_IN_ERROR` and `clinical_status = ACTIVE` in org+cluster. Field **omitted** without `clinical.allergy.read` (not `false`). Presentation of documented facts, not CDS.

Not in header: NIK, BPJS, passport, phone, email, tokens.

---

## Summary

Bounded source-backed pointers only. Caps: conditions/medications/allergies 10; vitals/lab results/procedures 5. Empty and unauthorized buckets omitted. Each item retains `source_type` + `source_id`. No AI. Optional `encounter_id` and query `facility_id` apply.

---

## Clinical notes

Patient-level list: cluster + organization. Optional `encounter_id`. List DTO has **no** `body_text`. Full body remains frozen `GET /api/v1/clinical/notes/{id}`.

---

## Encounter filtering

Longitudinal default. Optional `encounter_id` on shell, summary, timeline, and sections. Unknown / other-patient / other-org encounter → 404 `"Encounter not found"`. Facts with `encounter_id IS NULL` drop out of the encounter-scoped view. Encounter is not an appointment.

---

## Timeline

Projection only. No table. Per-domain authorized queries, then k-way merge.

Item fields: `source_type`, `source_id`, `occurred_at`, `organization_id`, `facility_id`, `canonical_patient_identity_id`, `source_patient_identity_id`, optional code/status/`encounter_id`. No note body, lab values, or medication payload.

Order: `occurred_at DESC`, `source_type ASC`, `source_id DESC`.

Entered-in-error facts remain on timeline/section lists; summary and allergy indicator exclude them.

---

## Pagination / cursor

Opaque URL-safe base64 of JSON `{"id":"<uuid>","k":"<source_type>","t":"<iso8601>"}` (sorted keys, no PHI). Unsigned. Tampering cannot widen authorization.

Default page size 50, max 100, min 1. Malformed cursor → 422 `invalid_cursor`. `has_more` + `next_cursor`.

Approved filters: `encounter_id`, `status`, `category`, `recorded_from`/`recorded_to` on the section timestamp, query `facility_id`. No PHI text search.

Unknown `status`/`category` values are applied as equality filters (empty page) rather than 422. Cursor and limit remain 422.

---

## Audit

Module enum string `CLINICAL_CHART_ACCESSED` on `AuditEvent.action`. No catalog table, no migration.

Emitted on successful shell, summary, and timeline. Direct section GET: authorize only, no extra chart audit.

Safe metadata: `purpose`, `canonical_patient_identity_id`, `requested_patient_identity_id` if different, `surface` (`shell`\|`summary`\|`timeline`), `authorized_sections` (comma-separated slugs the **actor** can access). `resource_type` `ClinicalChart`. `resource_id` / `patient_id` = canonical identity. Optional header facility on the audit row.

Never logged: NIK, BPJS, MRN, note body, lab values, medication payload, JWT, tokens, full chart.

Inherited DENIED-audit rollback: unchanged.

---

## Provenance

Chart reads insert **zero** `clinical_provenances` rows.

---

## DTO strategy

Dedicated Pydantic read projections (`ClinicalReadModel`, `extra="forbid"`). Healthcare Web is not bound to frozen command schemas. No ORM dump. No UI color/icon/css fields.

---

## Query / session / cache

One request-scoped async SQLAlchemy session. Sequential section queries. READ COMMITTED. No `asyncio.gather` on the same session. No Redis clinical cache. No snapshot / repeatable-read.

N+1: bounded pages; laboratory children loaded in bulk by order id for the current page.

---

## Indexes / migration

Existing single-column indexes used. Representative `EXPLAIN`:

- `conditions`: Index Scan on `ix_conditions_organization_id`, filter `patient_identity_id`
- `clinical_notes`: Index Scan on `ix_clinical_notes_patient_identity_id`, filter `organization_id` (no org index; design-approved non-blocking)

No speculative composites. No migration 0019.

---

## Tests

Unit: `backend/tests/unit/test_clinical_read_core_domain.py` (unique basename required by pytest).

Integration: `backend/tests/integration/test_clinical_read_core.py`.

No dedicated hardening file.

---

## Quality gates

Recorded in the companion implementation gate. Full pytest **338 passed**. `ruff check` / `ruff format --check` / `mypy app` (132 files) passed.

---

## Docker

Live `:9100` image does not expose Clinical Read Core routes (OpenAPI has no `/clinical/patients` paths). Classified **P3 Docker image lag**. Image was not rebuilt.

Health: `GET /api/v1/health/live` 200; `GET /api/v1/health/ready` 200 (`postgres`, `redis`, `object_storage` ok).

---

## Contract notes

- Unit file is `test_clinical_read_core_domain.py` rather than a second `test_clinical_read_core.py` (pytest module-name clash).
- Query `facility_id` uses a FastAPI alias to avoid colliding with `X-Facility-Id`.
- Unknown `status`/`category` → empty page, not 422.
- Timeline uses per-domain queries + k-way merge (allowed by design).
