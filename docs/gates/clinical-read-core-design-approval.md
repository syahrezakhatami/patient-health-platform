# Clinical Read Core — design approval gate

**Date:** 2026-08-26  
**Kind:** Design approval only  
**Verdict:** CLINICAL READ CORE = APPROVED FOR DESIGN ONLY  
**WAVE 2B CLINICAL FOUNDATION:** FROZEN (unchanged)  
**PRODUCT ACCESS & TENANCY:** FROZEN (unchanged)  
**IMPLEMENTATION:** NOT STARTED  
**MIGRATION 0019:** NOT CREATED  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize production routes, a web application, Patient Mobile, scheduling, notifications, pharmacy, AI, subscription, commit, tag, or push.

Source: `docs/architecture/clinical-read-core-design.md`.  
Discovery input: `docs/architecture/healthcare-web-clinical-chart-discovery.md`.  
Companion canvas (review-only, outside git): [clinical-read-core-design.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/clinical-read-core-design.canvas.tsx)

---

## 1. Verified baseline

If this table were materially wrong, this pass would STOP.

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` |
| Tag | Annotated `product-access-tenancy-foundation-frozen` peels to HEAD |
| Parent | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Working tree besides this design | Healthcare Web / Clinical Chart discovery docs only |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Does not exist |
| `clinical_read` production module | Does not exist |
| Frontend / Healthcare Web | Does not exist |
| `docker-compose.yml` | Untouched |
| `wave1_pdp.py` | SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| ProductAccessPDP | Authoritative; **no adapter required** |

---

## 2. Contract summary

| Topic | Approved decision |
|---|---|
| Module | In-process `clinical_read`; not a second SoT |
| Identity | Any org-visible UUID → canonicalize → return Y |
| Cluster | `ACTIVE` + `MERGED_IN` ∩ `organization_id` |
| Facility | Org-wide default; optional query filter |
| Shell | `mpi.identity.read` + visibility; no mega-permission |
| Sections | Existing domain reads; omit vs 403 as specified |
| Notes | Patient + encounter list in read core; body via existing GET |
| API | Four GETs under `/api/v1/clinical/patients/{id}/chart` |
| Pagination | Cursor, 50/100 |
| Audit | `CLINICAL_CHART_ACCESSED` on shell/summary/timeline |
| Provenance | None on read |
| Cache | None |
| Migration | **Not required** |
| PDP | Unchanged |

---

## 3. P0 / P1 / P2 / P3

- **P0 / P1:** none. No production code.
- **P2 historical identity non-rewrite:** addressed **in the design** by cluster `IN` queries; not by rewriting rows. Still inherited for frozen command lists.
- **P2 DENIED audit rollback:** unchanged; section filtering avoids calling `authorize()` for expected misses on the shell.
- **P3:** none block this design.

---

## 4. Separate designs (not this module)

- Healthcare Web shell / IAM membership / facility list HTTP
- In-progress encounters index (not appointments)
- Nurse role/permissions
- Optional ORG_ADMIN chart tightening
- Patient Mobile presenter
- Materialized projections, FHIR, scheduling, pharmacy, AI

---

## 5. Working tree

This pass adds:

- `docs/architecture/clinical-read-core-design.md`
- `docs/gates/clinical-read-core-design-approval.md`
- link from the Healthcare Web discovery doc

No production code. No tests. No migration. **NO COMMIT. NO TAG. NO PUSH.**

---

## 6. Verdict

CLINICAL READ CORE = APPROVED FOR DESIGN ONLY  

IMPLEMENTATION = NOT STARTED  
MIGRATION 0019 = NOT CREATED  
HEALTHCARE WEB = NOT IMPLEMENTED
