# Clinical Chart UI — design approval gate

**Date:** 2026-08-27  
**Kind:** DESIGN APPROVAL — not implementation  
**Verdict:** CLINICAL CHART UI DESIGN = APPROVED FOR IMPLEMENTATION  
**Baseline HEAD:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Parent:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** NOT REQUIRED  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize Clinical Read Core changes, Patient Lookup changes, PDP changes, clinical forms, writes, AI, commit, tag, or push.

Source: `docs/architecture/clinical-chart-ui-design.md`.

---

## 1. Baseline

| Item | Result |
|---|---|
| HEAD | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Tag | `patient-lookup-selection-frozen` |
| Parent | `1c502950011a168dbb139980ef758f2660561255` |
| Branch | `main` == `origin/main` |
| Working tree at inspection | clean; this pass adds design docs only |
| Frozen Patient Lookup / Shell / IAM / Clinical Read / MPI / PDPs | unchanged |
| `clinical.chart.read` | does not exist — not invented |

If this table were materially wrong, this pass would STOP.

---

## 2. Explicit decisions

CLINICAL CHART ROUTE = `/app/clinical/chart`

PATIENT UUID IN URL = NO

SELECTED PATIENT REQUIRED = YES

CHART PURPOSE = Clinical workspace sends `TREATMENT`. Chart purpose is the active workspace mapping, not the lookup-purpose stored on selection. No free-text purpose. No silent reuse of `AUDIT` / `REGISTRATION` / `IDENTITY_RESOLUTION` as chart purpose. Audit-workspace chart deferred.

INITIAL LOAD = (1) require memory-only selected patient for current org else Select Patient gate and **no** Clinical Read calls (2) `GET /chart` shell as gate (3) after shell 200, `GET /chart/summary` (4) render banner + `authorized_sections` nav (5) default view Summary (6) lazy-load opened section (7) timeline only when opened. No 13-way fan-out.

SECTION SOURCE OF TRUTH = Combination: navigation **must** use `ChartShellResponse.authorized_sections`. `effective_permissions` is UX workspace gating only. Direct section GET 403 is handled as UNAUTHORIZED. Backend remains final authority.

SECTION LOADING = LAZY (no speculative clinical-domain prefetch)

CHART FACILITY FILTER = DEFERRED

WORK FACILITY AUTO-FILTER = NO (`X-Facility-Id` is work context only; never copy to `?facility_id=`)

TIMELINE = explicit Load More; opaque cursor; default limit 50 max 100; no client re-sort; no cursor persistence; opening timeline emits frozen backend `CLINICAL_CHART_ACCESSED` `surface=timeline`

NOTE BODY = DEFERRED (section list metadata only; frozen `GET /api/v1/clinical/notes/{note_id}` not in MVP)

PHI CACHE = memory-only TanStack Query; keys include `organizationId` + `patientIdentityId`; `gcTime` ≤ 5 minutes; remove immediately on patient switch / org switch / 401 / logout; no persistQueryClient / Web Storage / IndexedDB / Service Worker; `refetchOnWindowFocus` false for clinical PHI queries in MVP

PATIENT SWITCH = AbortSignal + generation + org id + patient id match + patient-keyed query removal. Late A never renders under B. A→B→A distinguished by generation. Org switch wipes chart PHI before B is active; B context failure does not restore A.

UNAUTHORIZED SECTION = dedicated UNAUTHORIZED / unavailable copy; never “No conditions/medications/allergies”

EMPTY SECTION = AUTHORIZED_EMPTY only when the section is in `authorized_sections` and the authorized 200 page is empty (or allergy header `documented_allergy_exists === false`)

MERGED PATIENT = on shell 200, if canonical id differs from selected id, update selected patient from header and show identity-updated notice; retarget subsequent cache keys to canonical id

RETIRED PATIENT = 409 → safe “no longer available for clinical access”; clear clinical PHI; no lifecycle dump

NEW BACKEND ROUTES = NONE

MIGRATION 0019 = NOT REQUIRED

---

## 3. Additional frozen-aligned decisions

| Topic | Decision |
|---|---|
| Audience | staff `php-api` only; existing client |
| Shell permission | `mpi.identity.read` + org/purpose/visibility; **not** a new `clinical.chart.read` |
| MVP workspace | Clinical only |
| Audit workspace chart | DEFERRED |
| Entry | Select Patient (existing, no auto-nav) then explicit Open Chart |
| Close/Change Patient | wipe PHI then return to Patient Selection; no chart behind modal |
| Allergy safety | header `documented_allergy_exists` tri-state (`true` / `false` / omitted) is authoritative for NKA vs unavailable |
| Vitals | presentation grouping of Observation (`VITAL_SIGNS`); no new domain |
| Laboratory | any of three frozen lab read permissions; nested layers only if authorized |
| Writes / AI | forbidden in this capability |
| Frontend audit | never; backend `CLINICAL_CHART_ACCESSED` only on shell/summary/timeline |
| Unused `patientChartPath` | must **not** be wired as the MVP route |
| OpenAPI | generate from source FastAPI in implementation; not Docker `:9100` |

---

## 4. Exact Clinical Read routes (consumed, not modified)

- `GET /api/v1/clinical/patients/{patient_identity_id}/chart`
- `GET /api/v1/clinical/patients/{patient_identity_id}/chart/summary`
- `GET /api/v1/clinical/patients/{patient_identity_id}/chart/timeline`
- `GET /api/v1/clinical/patients/{patient_identity_id}/chart/sections/{section}`

Section slugs: `encounters`, `notes`, `conditions`, `observations`, `laboratory`, `medications`, `allergies`, `consents`, `immunizations`, `procedures`, `medical-devices`, `adverse-events`, `family-histories`.

---

## 5. P0 / P1 / P2 / P3 (design)

| Severity | Notes |
|---|---|
| P0 | None |
| P1 | Wrong-patient / cross-org / stale A-under-B / A→B→A / unauthorized-as-empty **designed**; must be implemented as specified. No unresolved design P1. |
| P2 | Inherited DENIED-audit rollback — not redesigned; not classified as P3 |
| P3 | Per-principal lookup throttle unused here; F5 re-auth/re-select (intentional memory-only); Docker image lag; inverted date-range empty page; notes org index; summary omit-empty vs omit-unauthorized requires combining shell sections + allergy header (no new route) |

---

## 6. Implementation-only scope (next pass)

When authorized as an implementation pass:

- Frontend Clinical Chart at `/app/clinical/chart`
- Source OpenAPI export/types for Clinical Read DTOs
- Thin fetch wrappers + TanStack Query as designed
- Safety banner, nav, summary, lazy sections, timeline Load More
- Race/wipe/401/logout/org-switch/patient-switch
- Tests for P1 races, unauthorized vs empty, allergy tri-state, no UUID URL, no work-facility auto-filter

Do **not** implement in that pass: clinical forms, writes, note body, chart facility filter, UUID routes, Audit chart, name search, recent patients, AI, backend/PDP/MPI/Alembic changes.

**This design pass does not implement anything.**

---

## 7. Working tree (this pass)

Adds:

- `docs/architecture/clinical-chart-ui-design.md`
- `docs/gates/clinical-chart-ui-design-approval.md`

No production code. No tests. No migration.

**NO COMMIT. NO TAG. NO PUSH.**

---

## 8. Verdict

CLINICAL CHART UI DESIGN = APPROVED FOR IMPLEMENTATION

CLINICAL CHART UI IMPLEMENTATION = NOT STARTED

CLINICAL FORMS = NOT STARTED

MIGRATION 0019 = NOT CREATED
