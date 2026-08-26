# Clinical Read Core — final freeze

**Date:** 2026-08-26  
**Verdict:** PASS WITH P2  
**P0:** none  
**P1 unresolved:** none  
**CLINICAL READ CORE:** FROZEN  
**CLINICAL READ CORE:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not start Healthcare Web, Patient Mobile, Platform Admin Web, IAM membership/facility shell UI APIs, in-progress encounter roster, scheduling, notifications, pharmacy, subscription, entitlement, billing, AI, FHIR, export/PDF, or patient cross-org access.

Authoritative contracts (not reinterpreted):

- `docs/architecture/healthcare-web-clinical-chart-discovery.md`
- `docs/gates/healthcare-web-clinical-chart-architecture-discovery.md`
- `docs/architecture/clinical-read-core-design.md`
- `docs/gates/clinical-read-core-design-approval.md`
- `docs/architecture/clinical-read-core.md`
- `docs/gates/clinical-read-core-implementation-gate.md`
- `docs/gates/clinical-read-core-hardening-gate.md`

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` (at freeze) |
| Published parent SHA | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` |
| Parent tag | annotated `product-access-tenancy-foundation-frozen` → same SHA |
| Parent of that baseline | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` (`wave-2b-clinical-foundation-complete`) |
| Family History freeze (unchanged) | `wave-2b8-family-history-frozen` → `9a56c0893f8638c1a66d854ca61f137a6177ebf4` |
| Final freeze SHA | this publication commit (`git rev-parse clinical-read-core-frozen^{}`) |
| Final annotated tag | `clinical-read-core-frozen` → this publication commit |
| Parent of freeze | `product-access-tenancy-foundation-frozen` |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration `0019` | **Not created** |
| `backend/docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched vs parent; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `ProductAccessPDP` | Untouched; remains `default_pdp()` |

Old tags were not moved or rewritten.

Expected lineage:

```
product-access-tenancy-foundation-frozen
        |
        v
clinical-read-core-frozen
```

---

## B. Scope

Staff read-only Clinical Read Core only:

- in-process `clinical_read` query module over frozen clinical tables
- staff `php-api` GET chart shell / summary / timeline / section
- canonical MPI resolution + cluster expansion + organization-scoped SQL
- existing ProductAccessPDP permissions (no `clinical.chart.read`)
- additive `CLINICAL_CHART_ACCESSED` audit on approved surfaces
- discovery, design, implementation, hardening, and this freeze documentation

No frontend. No Patient Mobile. No Platform Admin Web. No scheduling, subscription, AI, pharmacy, emergency, or ambulance. No materialized chart tables. No Redis clinical cache. No `patient_histories`. No `clinical_timeline` table.

---

## C. Module / routes

Module: `backend/app/modules/clinical_read/` (service, query repository, staff DTOs, catalog, cursor, timeline, age).

HTTP (additive): `backend/app/api/v1/clinical_read.py`, included from `backend/app/api/v1/router.py` after frozen `clinical_router`. Staff / `php-api` only (`require_staff_audience`).

| Method | Path |
|---|---|
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/summary` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/timeline` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/sections/{section}` |

No POST/PUT/PATCH/DELETE. No `/api/v2`. No `/fhir`. No staff chart under `/api/v1/patient`. No `patient-history` routes.

Read-only except approved audit writes. Does not create or mutate clinical source rows, MPI rows, clinical provenance, patient history tables, projection tables, or cache state.

Query `facility_id` is a FastAPI alias (`query_facility_id`) so it does not collide with `X-Facility-Id`.

---

## D. Canonical identity / cluster / tenant

Accept any org-visible identity UUID. Canonicalize. Return survivor id. No redirect.

| Case | Result |
|---|---|
| ACTIVE X | canonical X |
| MERGED X → Y, request X or Y | 200 canonical Y |
| RETIRED | 409 |
| unknown / cross-org | 404, same message |

Cluster: frozen `list_cluster_identity_ids` = **ACTIVE + MERGED_IN**, not UNMERGED. Frozen MPI rejecting A→B→C second-hop merge with 409 is expected and was not redesigned.

Every clinical fact query: `patient_identity_id IN cluster` **AND** `organization_id = effective organization`. No historical source-row rewrite. Physical fact-id dedupe only (no semantic merge).

Cross-org: same canonical person with Organization A and B facts → A chart returns A facts/notes/MRNs only; B chart returns B only. Verified in hardening integration tests.

---

## E. Facility

Default chart is organization-wide. NULL-facility facts remain visible when otherwise authorized. Same-org `facility_id` query filter narrows. Foreign facility → deny/conceal (404). Facility filter never grants access. Frozen Product Access facility semantics carried forward (unlisted explicit actor facility deny/conceal).

---

## F. Authorization

Path: authentication → ProductAccessPDP `authorize()` → chart shell (`mpi.identity.read` + membership + purpose + org-visible patient) → canonical resolution → per-section `authorize()` → query.

`php-api` only. `php-patient` / `php-platform` / missing `aud` / mixed `aud` → deny. Staff + `PATIENT_ACCESS` → 403 `purpose_principal_mismatch` before identity lookup (valid and random UUID).

No `clinical.chart.read`. Shell omits unauthorized section keys. Direct unauthorized section → 403. Unauthorized section SQL does not run (spy-verified). Laboratory retains three distinct read permissions; order-only omits nested specimens/results and does not query those tables.

REGISTRAR: header + encounters only. IDENTITY_OFFICER: header only. ORG_ADMIN / AUDITOR: frozen catalog reads preserved (not tightened). Permission-driven; no role-name special casing.

---

## G. Header / allergy / summary / notes / encounter

Header: canonical id, display name, DOB, computed `age_years` (not persisted; null remains explicit null), organization-scoped MRNs, other approved fields. No routine NIK/BPJS. No foreign-org MRNs.

Allergy: with `clinical.allergy.read`, documented → `true`, none → `false`. Without that permission the field is **omitted**, not `false`.

Summary: bounded; per-bucket source-domain permission; `source_type`/`source_id` retained; encounter and facility filters honored; unknown encounter 404; unauthorized buckets omitted and not queried; no AI/inference; no full history.

Notes: cluster-aware, organization-scoped, optionally encounter-filtered. List DTO has no `body_text` / full narrative. Cross-org notes excluded. Full body remains frozen GET-by-id.

Encounter filter: own patient encounter works; unknown / other-patient same-org / cross-org → 404. Encounter remains a care episode, not an appointment. CANCELLED remains readable (frozen Encounter read semantics).

---

## H. Filters / timeline / cursor / pagination

Unknown closed-domain `status` or `category` → **422**. Section slugs: closed catalog only; unknown slug 404. `code`/`code_system` text search was not in the approved filter list and was not added.

`recorded_from` > `recorded_to` → empty page (SQL AND; not swapped). 422 was not required by the approved contract. Retained as **P3 API semantics / validation consistency**.

Timeline: projection only; no table. Timestamp map from design; fallback when primary is null. Stable order: occurred/effective timestamp DESC, source_type ASC, source_id DESC.

Cursor: opaque unsigned `{t,k,id}` with known `k`. Extra keys / malformed / unknown `k` → 422. Patient A cursor on Patient B does not leak A ids. Facility A cursor reused with facility B filter does not return A/NULL facts. Cursor does not expand authorization.

Pagination: multi-page timeline and conditions — no duplicate physical facts under a stable dataset. Concurrent insert under READ COMMITTED: no crash, no cross-tenant leak; snapshot consistency not required.

SQL: parameterized filters; no table-name interpolation from slugs; no arbitrary user-controlled sort identifiers; no raw untrusted SQL.

---

## I. Audit / provenance / query

`CLINICAL_CHART_ACCESSED` on successful shell, summary, and timeline. Section requests do not emit extra chart-open audit. Metadata: purpose, canonical id, surface, authorized section names (requested id only when distinct). No NIK, BPJS, MRN, note body, lab values, medication payload, JWT, Authorization header, or full chart payload.

Reads create **zero** clinical provenance rows.

Query: one `page_source` per authorized source type (or one section + batched lab children). Summary bounded. Timeline and sections paginated. No whole-chart memory load. No Redis clinical cache. Production rate limit remains **120** req/min.

`clinical_notes` has no `organization_id` index. `EXPLAIN` uses `ix_clinical_notes_patient_identity_id` with org as filter. MVP-acceptable. **P3.** No migration 0019.

---

## J. Hardening defects fixed (before freeze)

| Defect | Fix |
|---|---|
| Unknown status/category empty page | Closed-enum 422 after section authorize |
| Lab order-only empty nested arrays + child SQL | Skip unauthorized lab-child queries; omit keys |
| Cursor extra keys / unknown `k` | Exact `{t,k,id}`; 422 `invalid_cursor` |

---

## K. Regression and quality gates

Frozen clinical command/read APIs through Family History: unchanged (lifecycle, immutability, concurrency, audit, provenance, command schemas). Clinical Read Core is additive.

Product Access & Tenancy: PLATFORM_ADMIN PHI deny, audience isolation, PatientPrincipal, patient account immutability, tenant/facility isolation, MPI collision, unknown-principal deny — preserved.

Executed 2026-08-26 against the live local stack.

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass (191 files) |
| `mypy app` | Pass (132 source files) |
| Full pytest | **345 passed** |
| Clinical Read Core unit | 12 passed |
| Clinical Read Core implementation integration | 2 passed |
| Clinical Read Core hardening | 5 passed |
| Alembic | `current == heads == 20260814_0018` |
| `/api/v1/health/live` | 200 |
| `/api/v1/health/ready` | 200 (`postgres`, `redis`, `object_storage` ok) |
| Secret scan | No `.env`, private keys, JWTs, credentials, DB secrets, runtime logs, or runtime volumes in the intended commit set |

---

## L. P0 / P1 / P2 / P3

| Severity | Class | Item |
|---|---|---|
| P0 | — | None |
| P1 unresolved | — | None |
| P2 | Inherited | DENIED-audit rollback with `ForbiddenError` (unchanged; not this module) |
| P3 | Docker | Live `:9100` image lacks Clinical Read Core routes (`GET .../chart` and `/openapi.json` 404). Not rebuilt. |
| P3 | Performance | `clinical_notes` missing organization composite/index; patient-identity index is MVP-acceptable |
| P3 | API semantics | `recorded_from` > `recorded_to` returns empty page rather than 422 |

---

## M. Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `backend/docker-compose.yml` untouched. **P3 DOCKER IMAGE LAG.** Source freeze is not blocked by known image lag. Working-tree tests exercise the ASGI app against live Postgres.

---

## N. Exact files included

Production:

- `backend/app/api/v1/router.py` (additive include only)
- `backend/app/api/v1/clinical_read.py`
- `backend/app/modules/clinical_read/` (module tree)

Tests:

- `backend/tests/unit/test_clinical_read_core_domain.py`
- `backend/tests/integration/test_clinical_read_core.py`
- `backend/tests/integration/test_clinical_read_core_hardening.py`

Docs:

- `docs/architecture/healthcare-web-clinical-chart-discovery.md`
- `docs/gates/healthcare-web-clinical-chart-architecture-discovery.md`
- `docs/architecture/clinical-read-core-design.md`
- `docs/gates/clinical-read-core-design-approval.md`
- `docs/architecture/clinical-read-core.md`
- `docs/gates/clinical-read-core-implementation-gate.md`
- `docs/gates/clinical-read-core-hardening-gate.md`
- `docs/gates/clinical-read-core-final-freeze.md` (this file)

---

## O. Push verification

Recorded after `git push origin main` and `git push origin clinical-read-core-frozen` (no force).

Expected: `HEAD == origin/main`; working tree clean; `clinical-read-core-frozen` peels to HEAD; Alembic still `20260814_0018`; `product-access-tenancy-foundation-frozen`, `wave-2b-clinical-foundation-complete`, and `wave-2b8-family-history-frozen` unchanged.

---

## Forbidden work (confirmed not started)

HEALTHCARE WEB = NOT IMPLEMENTED  
PATIENT MOBILE = NOT STARTED  
PLATFORM ADMIN WEB = NOT STARTED  
SCHEDULING = NOT STARTED  
NOTIFICATIONS = NOT STARTED  
SUBSCRIPTION = NOT STARTED  
AI = NOT STARTED
