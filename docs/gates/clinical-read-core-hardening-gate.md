# Clinical Read Core — hardening gate

**Status:** HARDENING COMPLETE  
**Frozen:** NO  
**Date:** 2026-08-26  
**Scope:** Hardening-only pass on the uncommitted Clinical Read Core implementation  
**Baseline:** `product-access-tenancy-foundation-frozen` / `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` / Alembic `20260814_0018`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Clinical Read Core is **not frozen**. No commit, tag, or push.

Authoritative design: `docs/architecture/clinical-read-core-design.md`.  
Implementation record: `docs/architecture/clinical-read-core.md` and `docs/gates/clinical-read-core-implementation-gate.md`.

---

## Verdict

CLINICAL READ CORE = IMPLEMENTED  
CLINICAL READ CORE HARDENING = COMPLETE  
CLINICAL READ CORE = NOT FROZEN  
MIGRATION 0019 = NOT CREATED

No unresolved P0/P1. No design return. No freeze.

---

## Baseline (verified)

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` |
| Tag | Annotated `product-access-tenancy-foundation-frozen` peels to HEAD |
| Parent | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Working tree | Uncommitted Clinical Read Core implementation + this hardening pass |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Not created |
| Frozen clinical domains | Untouched |
| `Wave1PolicyPDP` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `ProductAccessPDP` | Untouched; remains `default_pdp()` |
| Product Access / Tenancy semantics | Untouched |
| `backend/docker-compose.yml` | Untouched |
| Frontend / Patient Mobile | Absent |
| Rate limit | Production `120` req/min unchanged |

Uncommitted Clinical Read Core was not treated as baseline corruption.

---

## Hardening files

| Path | Role |
|---|---|
| `backend/tests/integration/test_clinical_read_core_hardening.py` | Dedicated hardening integration (audience, shell, section spy, cluster/tenant, notes, filters, cursor, audit) |
| `backend/tests/unit/test_clinical_read_core_domain.py` | Expanded unit coverage (cursor extra keys, closed enums, age, DTO omit) |
| `backend/tests/integration/test_clinical_read_core.py` | Existing implementation tests kept; not weakened |
| `backend/app/modules/clinical_read/**` | Contract-defined defect fixes only |

Existing Clinical Read Core tests: **not weakened**.

---

## Production defects found and fixed

Correct behavior was already defined in the approved design. No new architecture.

| Defect | Contract | Fix |
|---|---|---|
| Unknown `status`/`category` returned an empty page | Design: domain-valid enum only; error matrix 422 | `validate_section_filters()` after section `authorize()`, before `_project_section`. Closed frozen domain enums. Notes/laboratory reject `category`. Laboratory `status` enum follows the winning lab read permission. |
| Laboratory order-only readers received `specimens: []` / `results: []` and the repository loaded unauthorized children | Nested layers only if those read permissions exist; do not query then discard; empty list vs omit is the same class of leak as allergy `false` vs omit | `list_lab_children(include_specimens=, include_results=)` skips unauthorized SQL. DTO omits `None` nested keys. Authorized empty remains `[]`. |
| Cursor accepted extra JSON keys / unknown `k` | Malformed / semantically impossible → 422 `invalid_cursor` | Payload must be exactly `{t,k,id}`; `k` must be a `TimelineSourceType` value. |

Closed implementation P3 “empty page for unknown status/category”.

---

## Auth-before-query

Production path for all four GET routes:

authentication (`require_staff_audience`) → `ProductAccessPDP` / `authorize()` (`mpi.identity.read`) → PATIENT_ACCESS reject (before lookup) → canonical identity resolution → org visibility → cluster expansion → optional facility/encounter checks → per-section `authorize()` (section routes) → query.

Section data query (`page_source`) runs only after section authorization and filter validation. Summary buckets query only when the source-domain read permission is present. Timeline skips unauthorized `SOURCE_PERMISSION` entries before `page_source`. Allergy existence is queried only with `clinical.allergy.read`. Laboratory children SQL is skipped when the corresponding lab read is missing.

Spy: unauthorized `GET .../sections/allergies` does **not** execute `page_source` for `allergy`.

No `clinical.chart.read` in permission catalog or module.

---

## Audience / purpose / shell

| Case | Result |
|---|---|
| `php-api` + otherwise authorized | 200 |
| `php-patient` | 401 |
| `php-platform` | 401 |
| missing `aud` | 401 |
| mixed `aud` array | 401 (frozen Product Access contract) |
| staff + `PATIENT_ACCESS` on valid and random UUID | 403 `purpose_principal_mismatch` before lookup; same code; no existence leak |
| missing `mpi.identity.read` | 403 |
| `PLATFORM_ADMIN` staff chart | 403 (PHI deny intact) |
| Hospital A staff + `X-Organization-Id = B` | 403/404 conceal |
| Hospital A staff + org A + patient from B | 404 |
| POST/PUT/PATCH/DELETE on chart | 404/405 |

---

## Section / laboratory / role behavior

Permission-driven only. No role-name special casing in `clinical_read`.

| Actor | Shell | Direct unauthorized section |
|---|---|---|
| Partial (`condition.read` + `medication.read`) | `conditions`, `medications` only; allergy field omitted | allergies 403; allergy SQL not executed |
| Lab order-only | laboratory section as orders; `specimens`/`results` keys omitted | nested child SQL skipped |
| Lab result-only | result DTOs (`laboratory_order_id`, no `ordered_at`) | order/specimen not implied |
| REGISTRAR | `encounters` only | conditions 403 |
| IDENTITY_OFFICER | empty `authorized_sections` (header only) | encounters 403 |
| ORG_ADMIN / AUDITOR | frozen catalog reads preserved (conditions 200) | not tightened |

Unknown slugs (`vitals`, `condition`, `CONDITIONS`, `../notes`, `sql`) → 404. Closed `ChartSection` catalog only.

---

## Canonical identity / cluster / tenant

| Case | Result |
|---|---|
| ACTIVE X | canonical X |
| MERGED A → B, request A or B | 200 canonical B, no redirect |
| RETIRED | 409 (existing implementation tests) |
| unknown / foreign-org identity | 404 same message |
| Cluster members | frozen `list_cluster_identity_ids` = ACTIVE + MERGED_IN, not UNMERGED |
| A → B historical facts | A and B org-A facts on B chart; physical ids unique |
| A → B → C | frozen MPI rejects second-hop merge (409). Not rewritten. Not a Read Core defect. |
| Dedup | physical `id` only; two semantically identical conditions both remain |
| Hospital A vs B on same MPI person | A chart only A facts/notes/MRN; B only B |
| Every fact SQL | `organization_id = current tenant` AND `patient_identity_id IN cluster` |

---

## Facility / header / age / allergy

Org-wide default includes NULL-facility facts. Same-org `facility_id` narrows and excludes NULL and other sites. Foreign facility UUID → 404. Filter never grants access.

Header: no NIK/BPJS. MRNs org-scoped; Hospital B MRN absent from Hospital A header. `age_years` computed UTC, not stored; missing DOB serializes `age_years: null`; birthday/leap/future DOB follow existing arithmetic (no invented clamp).

Allergy with read: documented → `true`; none → `false`. Without allergy read: field **omitted**, not `false`.

---

## Summary / filters / notes / encounter

Each summary bucket gated by source-domain read. Unauthorized bucket omitted and not queried. Caps 10/10/10/5/5/5. Items keep `source_type`/`source_id`. Encounter/facility filters apply. Unknown/foreign encounter → 404.

`status`/`category`: closed per-domain enums → unknown 422. `code`/`code_system` were not in the approved filter list and were not added. `recorded_from` > `recorded_to` is not specified as 422; SQL AND yields empty page (not a silent swap).

Notes: cluster + org; optional encounter filter; list DTO has no `body_text` / narrative. Hospital B notes absent from Hospital A list. Full body remains frozen GET-by-id.

Encounter: own encounter filters; unknown / other-patient / foreign-org → 404. CANCELLED encounter remains readable (frozen Encounter read semantics).

---

## Timeline / cursor / pagination

Timestamp map covers every timeline source; fallback used when primary is null. Order: occurred/effective DESC, source type ASC, source id DESC. Repeated requests stable under a fixed dataset.

Cursor encodes unsigned `{t,k,id}` only (design-permitted). Request authorize + WHERE still bind patient/org/filters. Patient A cursor on Patient B does not return A ids. Facility A cursor reused with facility B filter does not return A/NULL facts. Malformed / extra fields / unknown `k` → 422. No SQL errors in error body.

Pagination: three condition pages, no duplicate physical ids; timeline page 1+2 no duplicate `source_id`. Concurrent insert between pages: no crash, no cross-tenant leak. Exact snapshot consistency is not required (READ COMMITTED). Eventual variation after concurrent writes is expected.

---

## SQL / query / notes index

Section slugs map through closed catalog. Filters parameterized. No string-built SQL, no untrusted identifiers, no wildcard PHI search, no Redis in the module (docstring denial only).

Query shape: one `page_source` per authorized source type (timeline) or one section query + optional batched lab children. No one-query-per-row attribution.

`EXPLAIN` notes (`organization_id` + `patient_identity_id IN cluster`, `authored_at DESC`, limit 51): Bitmap Index Scan on `ix_clinical_notes_patient_identity_id`, org as filter. Cost ~14 at current size. **P3 retained** (no org index). Not a correctness blocker. **No migration 0019.**

`EXPLAIN` conditions: Index Scan `ix_conditions_organization_id`.

---

## Audit / provenance / DTO / logging

Successful shell, summary, timeline emit `CLINICAL_CHART_ACCESSED` (surfaces `shell`/`summary`/`timeline`). Section lists: authorize only; `surface=section` count = 0. Metadata: purpose, canonical id, surface, authorized section names; requested id only when distinct. No NIK/BPJS/MRN/JWT/note body/lab values.

Inherited DENIED-audit rollback with `ForbiddenError` unchanged (**P2**, not redesigned).

Chart/summary/timeline/section reads create zero clinical provenance rows. Provenance count increased only from an extra **write**.

DTOs: explicit schemas, `extra=forbid`. No `provenance_id`, `body_text`, NIK/BPJS, ORM dumps.

Module has no application logging of response DTOs or identities.

Invalid requests: no SQL, table names, stacks, foreign existence, or cluster structure in bodies.

---

## Regression / routes / performance / cache

Frozen clinical command/read APIs through Family History ran in full pytest. Command routes, lifecycle, immutability, concurrency, audit, provenance, and clinical schemas unchanged except additive chart audit on new routes.

Product Access / Tenancy suite passed (PLATFORM_ADMIN PHI deny, facility tenant validation, PatientPrincipal isolation, audiences, binding, MPI, unknown-principal deny).

Approved GET-only routes under `/api/v1/clinical/patients/{id}/chart` (+ `/summary`, `/timeline`, `/sections/{section}`). No POST/PUT/PATCH/DELETE. No `/api/v2`, `/fhir`, `patient-history`.

Pagination limits honored (default 50 / max 100). Summary bounded. Shell small. One async session, sequential queries, READ COMMITTED. Audit insert is the only write side effect. No Redis clinical cache. Rate limit 120 unchanged.

---

## Quality gates

Executed 2026-08-26 against the live local stack.

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass (191 files) |
| `mypy app` | Pass (132 source files) |
| Full pytest | **345 passed** (was 338) |
| Clinical Read Core unit | 12 passed |
| Clinical Read Core implementation integration | 2 passed |
| Clinical Read Core hardening | 5 passed (1 static + 4 DB) |
| Alembic | `current == heads == 20260814_0018` (one head) |
| `/api/v1/health/live` | 200 |
| `/api/v1/health/ready` | 200 (`postgres`, `redis`, `object_storage` ok) |
| Secret scan | No `.env`, private keys, JWTs, provider credentials, database secrets, runtime logs, or runtime volumes in the intended working tree |

---

## P0 / P1 / P2 / P3

### A. New Clinical Read Core findings

| Severity | Item | Disposition |
|---|---|---|
| P0 | None | — |
| P1 | None remaining | Laboratory nested empty-list leak and query-before-permission for lab children **fixed** |
| — | Unknown status/category empty page | **Fixed** to 422 (was implementation P3) |

### B. Inherited findings

| Severity | Item |
|---|---|
| P2 | DENIED-audit rollback with `ForbiddenError` (unchanged; not this module; not redesigned) |
| — | Frozen MPI does not accept A→B→C second-hop merge (409). Read Core uses existing cluster API. |

### C. Docker / image / performance

| Severity | Item |
|---|---|
| P3 | Live Docker `:9100` image lacks Clinical Read Core (and later frozen) routes. `GET /openapi.json`, `GET .../chart`, `POST /clinical/family-histories` → 404. Image **not** rebuilt. |
| P3 | `clinical_notes` has no `organization_id` index. Patient-identity index + org filter is acceptable for MVP. No 0019. |

---

## Docker

Ports remain 9100 / 5433 / 6380 / 9101 / 9002. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. `backend/docker-compose.yml` untouched. Backend container up ~12 days. **P3 DOCKER IMAGE LAG.** Working-tree tests exercise the ASGI app against live Postgres.

---

## Forbidden work (confirmed not started)

HEALTHCARE WEB = NOT IMPLEMENTED  
PATIENT MOBILE = NOT STARTED  
PLATFORM ADMIN WEB = NOT STARTED  
SCHEDULING = NOT STARTED  
NOTIFICATIONS = NOT STARTED  
SUBSCRIPTION = NOT STARTED  
AI = NOT STARTED  

No Wave1PolicyPDP / ProductAccessPDP edits. No materialized chart tables. No Redis chart cache. No patient cross-org access.

NO COMMIT  
NO TAG  
NO PUSH
