# Clinical Read Core — implementation gate

**Status:** IMPLEMENTED  
**Hardening:** NOT STARTED  
**Frozen:** NO  
**Date:** 2026-08-26  
**Scope:** Staff read-only Clinical Read Core only  
**Baseline:** `product-access-tenancy-foundation-frozen` / `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` / Alembic `20260814_0018`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Clinical Read Core is **not frozen**. Hardening has **not** started. No commit, tag, or push.

Source implementation: `docs/architecture/clinical-read-core.md`.  
Authoritative design: `docs/architecture/clinical-read-core-design.md`.

---

## Verdict

CLINICAL READ CORE = IMPLEMENTED  
CLINICAL READ CORE HARDENING = NOT STARTED  
CLINICAL READ CORE = NOT FROZEN  
MIGRATION 0019 = NOT CREATED

---

## In scope

In-process `clinical_read` query module: staff chart shell, summary, timeline, and section reads over frozen clinical tables via `ProductAccessPDP` + canonical MPI cluster expansion + organization-scoped SQL.

## Out of scope

Healthcare Web frontend, Patient Mobile, Platform Admin Web, IAM membership/facility shell UI APIs, in-progress encounter roster, scheduling, appointments, queue, notifications, pharmacy, prescription, dispense, medication reminder, subscription, entitlement, billing, AI, FHIR, `/api/v2`, materialized chart tables, Redis chart cache, NURSE role, ORG_ADMIN tightening, migration 0019, hardening, freeze, commit, tag, push.

---

## Baseline

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` |
| Tag | Annotated `product-access-tenancy-foundation-frozen` peels to HEAD |
| Parent | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Not created |
| `Wave1PolicyPDP` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `ProductAccessPDP` | Untouched; remains `default_pdp()` |
| `docker-compose.yml` | Untouched |
| Rate limit | Production `120` req/min unchanged |

---

## Module / routes

Module: `backend/app/modules/clinical_read/` (service, query repository, staff DTOs, catalog, cursor, timeline, age, audit action string).

HTTP (additive): `backend/app/api/v1/clinical_read.py`, included from `backend/app/api/v1/router.py` after frozen `clinical_router`.

| Method | Path |
|---|---|
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/summary` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/timeline` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/sections/{section}` |

Staff / `php-api` only.

---

## Canonical identity / cluster / tenant

Accept any org-visible identity UUID. Canonicalize. Return survivor id. No redirect. RETIRED 409. Unknown and cross-org 404 with the same message.

Cluster: `ACTIVE` + `MERGED_IN`. Facts: `patient_identity_id IN cluster AND organization_id = request org`. Cross-org cluster facts excluded. Physical id dedupe only.

Facility: org-wide default; query `facility_id` is a filter; foreign facility concealed per Product Access.

---

## Authorization

Shell: `mpi.identity.read` + visibility. No `clinical.chart.read`. `PATIENT_ACCESS` 403 before lookup.

Per-section: existing frozen read permissions, including three distinct laboratory reads. Shell omits unauthorized keys. Direct section 403.

REGISTRAR: header + encounters only. IDENTITY_OFFICER: header only. ORG_ADMIN / AUDITOR: existing frozen reads preserved.

Purpose: existing catalog. Missing/unknown 422. Purpose is not a grant.

---

## Header / summary / notes / encounter / timeline / pagination

Header: approved staff fields; `age_years` computed UTC; `documented_allergy_exists` omitted without allergy read; no NIK/BPJS.

Summary: bounded source pointers with `source_type`/`source_id`; caps 10/10/10/5/5/5; encounter and facility filters apply.

Notes: patient-level cluster+org list; no `body_text`; full body via frozen GET by id.

Encounter: optional filter; unknown/other-patient/other-org 404.

Timeline: projection; timestamp map from design; order `occurred_at DESC`, `source_type ASC`, `source_id DESC`.

Cursor: opaque base64 JSON `{t,k,id}`; default 50 / max 100; malformed 422.

---

## Audit / provenance

`CLINICAL_CHART_ACCESSED` on successful shell, summary, timeline. Sections: authorize only. Safe metadata only. No clinical provenance rows on reads. Inherited DENIED-audit rollback unchanged.

---

## Tests

Unit: `backend/tests/unit/test_clinical_read_core_domain.py` — catalog, permissions, age, cursor, timestamp map, timeline order, DTO omission, physical dedupe.

Integration: `backend/tests/integration/test_clinical_read_core.py` — ACTIVE/MERGED cluster, historical+current facts, Hospital A vs B exclusion, physical-id uniqueness, org isolation, facility conceal/filter, purpose, shell and per-section auth, registrar/officer/clinician/org-admin/auditor, notes without body, encounter filter, unknown encounter, timeline and section pagination, summary bounds, chart audit, no provenance, unknown/retired, patient and platform audience deny.

Frozen clinical suite and Product Access / Tenancy tests ran as part of full pytest (additive module; command routes unchanged).

No dedicated hardening test file.

---

## Quality gates

Executed 2026-08-26 against the live local stack.

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass (190 files) |
| `mypy app` | Pass (132 source files) |
| Full pytest | **338 passed** |
| Clinical Read Core unit | 10 passed |
| Clinical Read Core integration | 2 passed |
| Alembic | `current == heads == 20260814_0018` (one head) |
| `/api/v1/health/live` | 200 |
| `/api/v1/health/ready` | 200 (`postgres`, `redis`, `object_storage` ok) |
| Secret scan | No `.env`, private keys, JWTs, provider credentials, database secrets, runtime logs, or runtime volumes in the intended working tree |
| `EXPLAIN` conditions | Index Scan `ix_conditions_organization_id` |
| `EXPLAIN` clinical_notes | Index Scan `ix_clinical_notes_patient_identity_id` (org as filter; no org index) |

---

## P0 / P1 / P2 / P3

| Severity | Item |
|---|---|
| P0 | None |
| P1 | None |
| P2 | Inherited DENIED-audit rollback with `ForbiddenError` (unchanged; not this module) |
| P3 | Live Docker `:9100` image lacks Clinical Read Core routes (OpenAPI has no `/clinical/patients` paths). Not rebuilt. |
| P3 | `clinical_notes` has no `organization_id` index (design-approved; existing patient-identity index used) |
| P3 | Unknown `status`/`category` query values return an empty page rather than 422 |

---

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `docker-compose.yml` untouched. Image lag is P3, not a source implementation failure.

---

## Contract deviations

- Unit basename is `test_clinical_read_core_domain.py` so pytest can collect it beside `test_clinical_read_core.py`.
- Query `facility_id` is a FastAPI alias (`query_facility_id`) to avoid colliding with `X-Facility-Id`.
- Unknown `status`/`category` are equality filters, not 422.

No schema or policy redesign. No migration 0019. Authorization was not weakened. Frozen clinical semantics were not changed.

---

## Forbidden work (confirmed not started)

HEALTHCARE WEB = NOT IMPLEMENTED  
PATIENT MOBILE = NOT STARTED  
PLATFORM ADMIN WEB = NOT STARTED  
SCHEDULING = NOT STARTED  
NOTIFICATIONS = NOT STARTED  
SUBSCRIPTION = NOT STARTED  
AI = NOT STARTED  

NO COMMIT  
NO TAG  
NO PUSH
