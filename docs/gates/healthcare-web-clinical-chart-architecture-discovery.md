# Healthcare Web and clinical chart — architecture discovery gate

**Date:** 2026-08-26  
**Kind:** Architecture discovery only  
**Verdict:** DISCOVERY COMPLETE — NOT IMPLEMENTATION APPROVAL  
**WAVE 2B CLINICAL FOUNDATION:** FROZEN (unchanged)  
**PRODUCT ACCESS & TENANCY:** FROZEN (unchanged)  
**HEALTHCARE WEB:** NOT IMPLEMENTED  
**CLINICAL CHART READ MODEL:** NOT IMPLEMENTED  
**MIGRATION 0019:** NOT CREATED  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize production code, a web application, migration `0019`, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, AI, subscription, commit, tag, or push.

Source: `docs/architecture/healthcare-web-clinical-chart-discovery.md`.  
Companion canvas (review-only, outside git): [healthcare-web-clinical-chart-discovery.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/healthcare-web-clinical-chart-discovery.canvas.tsx)

---

## 1. Verified baseline

If this table were materially wrong, this pass would STOP.

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` |
| Tag | Annotated `product-access-tenancy-foundation-frozen` → same SHA |
| Parent | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` (`wave-2b-clinical-foundation-complete`) |
| Family History freeze | `wave-2b8-family-history-frozen` → `9a56c0893f8638c1a66d854ca61f137a6177ebf4` (unchanged) |
| Working tree at inspection | CLEAN; this pass adds discovery docs only |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Does not exist |
| `docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| ProductAccessPDP | Authoritative `default_pdp()` |

---

## 2. Decisions (discovery, not implementation approval)

| # | Topic | Discovery decision |
|---|---|---|
| 1 | Clients | Three clients; this pass is **Healthcare Web only** |
| 2 | App shape | **One** Healthcare Web for hospitals and clinics. No Doctor/Nurse/Hospital/Clinic separate apps |
| 3 | Backend | Keep FastAPI modular monolith. No Healthcare Web backend |
| 4 | Workspace | Permission-derived navigation. Workspace ≠ PDP role |
| 5 | Chart SoT | Project frozen facts only. No `patient_histories` / VitalSign / Diagnosis tables |
| 6 | Read architecture | **Query module in-process** (`clinical_read` illustrative). Not browser fan-out. Not a single-permission mega-chart |
| 7 | Commands | Existing `/api/v1/clinical/*` mutations. No `/web/...` duplicates |
| 8 | Staff API prefix | Chart reads under `/api/v1/clinical/patients/...` (illustrative). Not `/api/v1/patient` (PatientPrincipal) |
| 9 | Versioning | `/api/v1` only. No `/api/v2`. No `/fhir` |
| 10 | Cluster | Chart of canonical Y includes org-scoped facts whose `patient_identity_id` is in the MPI cluster |
| 11 | Tenant | `organization_id` remains the boundary |
| 12 | Facility | Frozen Product Access rules; chart grain is org-wide by default |
| 13 | Lookup | Exact identifier **READY**. Name directory **FORBIDDEN**. Scheduling **DEFERRED**. Encounter ≠ appointment |
| 14 | ORG_ADMIN | Catalog already grants all clinical **reads**. Documented; tightening is a later design |
| 15 | Registrar | Encounter + MPI only |
| 16 | Nurse | **No role.** Separate permission design required |
| 17 | Authz for aggregation | Shell + **per-section** permission |
| 18 | Patient reuse | Shared query engine; distinct PDP and DTO |
| 19 | i18n | ID+EN MVP; ZH later; codes never translated |
| 20 | Frontend | Vite + React + TypeScript SPA |
| 21 | Repo | Same git repo; later `apps/healthcare-web`. Do not split now |
| 22 | AI | Additive. Chart must work with AI unavailable |
| 23 | First build | Clinical Read Core **before** (or blocking) a longitudinal chart UI |

---

## 3. Backend readiness (as frozen)

**Ready to consume:** staff JWT `php-api`; `GET /iam/users/me`; org-scoped clinical commands and per-patient domain lists; MPI lookup/get/match; purpose catalog; ProductAccessPDP; facility tenant check on `authorize()`.

**Not sufficient alone for a truthful longitudinal chart:** current `list_*` APIs bind to **canonical identity id only**, so merged-source rows are omitted (inherited P2). No HTTP list for notes-by-patient (repository lists notes by encounter). No HTTP facility list. No membership org/facility payload on `/users/me`. No refresh-token API. No org-wide “today’s encounters” index.

---

## 4. P0 / P1 / P2 / P3

- **P0 / P1:** none unresolved on the frozen baseline. None introduced (no production code).
- **P2:** DENIED audit rollback — does not block MVP. Historical `patient_identity_id` non-rewrite — **does** block using current list endpoints as the chart engine; address in `clinical_read`, do not rewrite history.
- **P3:** grants outside Alembic; nullable provenance; Docker image lag; independent org/facility FKs — none block this architecture if SQL filters `organization_id`.

---

## 5. Separate design approvals required before code

1. Clinical Read Core (API names, pagination, cluster SQL, per-section auth, audit of chart open)
2. Healthcare Web shell (auth session UX, org/facility picker APIs)
3. Nurse permission bundle (if nursing UI is in scope)
4. Optional ORG_ADMIN chart tightening
5. Optional “today’s in-progress encounters” index (still not scheduling)

**Not** this pass: scheduling, notifications, pharmacy, AI, Patient Mobile, Platform Admin Web, export/PDF, ZH terminology service.

---

## 6. Working tree

This pass adds:

- `docs/architecture/healthcare-web-clinical-chart-discovery.md`
- `docs/gates/healthcare-web-clinical-chart-architecture-discovery.md`

No production code. No tests. No migration. **NO COMMIT. NO TAG. NO PUSH.**

---

## 7. Verdict

HEALTHCARE WEB & CLINICAL CHART ARCHITECTURE DISCOVERY = COMPLETE  

HEALTHCARE WEB = NOT IMPLEMENTED  
CLINICAL CHART READ MODEL = NOT IMPLEMENTED  
MIGRATION 0019 = NOT CREATED
