# Clinical Chart UI — implementation gate

**Date:** 2026-08-27  
**Kind:** IMPLEMENTATION GATE — not hardening, not freeze  
**Baseline:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Parent:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Alembic:** `20260814_0018` (one head). Migration **0019 not created**.  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, or push in this pass.

Implementation: `docs/architecture/clinical-chart-ui-implementation.md`.  
Design: `docs/architecture/clinical-chart-ui-design.md`.  
Approval: `docs/gates/clinical-chart-ui-design-approval.md`.

---

## Verdict

**CLINICAL CHART UI = IMPLEMENTED**

**CLINICAL CHART UI HARDENING = NOT STARTED**

**CLINICAL CHART UI = NOT FROZEN**

**MIGRATION 0019 = NOT CREATED**

**CLINICAL FORMS = NOT IMPLEMENTED**

**CLINICAL WRITES = NOT IMPLEMENTED**

**NOTE BODY = NOT IMPLEMENTED**

**CHART FACILITY FILTER = NOT IMPLEMENTED**

**NO COMMIT / NO TAG / NO PUSH**

---

## Contract

| Item | Value |
|---|---|
| Frontend route | `/app/clinical/chart` (no patient UUID) |
| Selected patient | Memory-only; required; org-bound |
| Purpose | `X-Purpose: TREATMENT` |
| Organization | `X-Organization-Id` from shell |
| Work facility | `X-Facility-Id` only; never `?facility_id=` |
| Clinical Read | Frozen GET chart / summary / timeline / sections/{section} |
| Nav source | `authorized_sections` |
| Default view | Summary after shell 200 |
| Sections | Lazy; frozen catalog only |
| Notes | Metadata/list only |
| Timeline | Opaque cursor; Load More; limit 50 |
| PHI cache | Memory TanStack Query; `gcTime` ≤ 5 min; no focus refetch |

---

## Tests

Frontend: `apps/healthcare-web/src/chart/clinical-chart.test.tsx` (entry, purpose, banner, sections, allergy tri-state, races, cache wipes, timeline, merged, retired, notes, XSS, request count, catalog).

Full frontend suite: **119 passed** (previous frozen baseline **91**).

Backend: **442 passed**. ruff check / ruff format --check / mypy app: pass. No frozen Clinical Read / Lookup / MPI / PDP / shell regressions.

---

## Quality gates

| Check | Result |
|---|---|
| `npm ci` | run (0 production vulnerabilities reported by that audit) |
| lint (`oxlint --deny-warnings`) | 0 errors, 0 warnings |
| typecheck | pass |
| tests | **119 passed** |
| production build | pass |
| `npm audit --omit=dev` | 0 vulnerabilities |
| OpenAPI `--check` (source FastAPI, not `:9100`) | pass |
| backend ruff / mypy | pass |
| backend pytest | **442 passed** |
| Alembic | `current == heads == 20260814_0018` |
| health live / ready | 200; postgres, redis, object_storage ok |
| secret / PHI scan | synthetic fixtures only; no JWT/OIDC secrets in this pass |

---

## P0 / P1 / P2 / P3

| Severity | Notes |
|---|---|
| P0 | None |
| P1 | A-under-B, org-under-org, unauthorized-as-empty, work-facility silent filter, stale canonical overwrite, PHI in Web Storage — **tested and blocked by this implementation** |
| P2 | Inherited **DENIED-audit rollback** (unchanged, not downgraded). PHI wipe on close/logout/401/org switch implemented. Allergy omitted is not “no allergies”. Note body not exposed. No section prefetch. No clinical console PHI. |
| P3 | F5 re-select (memory-only selection); Docker `:9100` Clinical Read 404 (image lag, not rebuilt); inverted date-range frozen backend behavior; notes org-index performance debt; OpenAPI `PatientHeaderDTO` serializer opacity (UI wrapper); summary omit-empty handled in UI |

No unresolved implementation P0. Do not downgrade tenant/PHI issues; none found remaining.

---

## Docker

Known image lag remains. `GET /api/v1/clinical/patients/{id}/chart` on `:9100` returned **404**. Health still 200. Image **not** rebuilt. Source OpenAPI is authoritative.

---

## Out of scope (confirmed)

Clinical forms, writes, note body, chart facility filter, name search, recent patients, scheduling, notifications, Patient Mobile, Platform Admin, pharmacy, subscription, AI, ambulance, FHIR, `/api/v2`, migration 0019, backend production edits, hardening gate, freeze, commit, tag, push.
