# Clinical Chart UI — architecture / security design

**Date:** 2026-08-27  
**Kind:** DESIGN ONLY — not implementation  
**Status:** APPROVED FOR IMPLEMENTATION (see companion gate)  
**Baseline HEAD:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Parent:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** not required  

This document is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement Clinical Chart UI, Clinical Read Core frontend calls, clinical forms, writes, name search, recent patients, scheduling, Patient Mobile, Platform Admin, AI, FHIR, `/api/v2`, commit, tag, or push.

Authoritative frozen contracts:

- `docs/gates/patient-lookup-selection-final-freeze.md`
- `docs/gates/healthcare-web-shell-final-freeze.md`
- `docs/gates/iam-shell-context-final-freeze.md`
- `docs/gates/clinical-read-core-final-freeze.md`
- `docs/architecture/healthcare-web-clinical-chart-discovery.md`
- `docs/gates/healthcare-web-clinical-chart-architecture-discovery.md`
- `backend/app/api/v1/clinical_read.py`
- `backend/app/modules/clinical_read/`

Frozen and not reinterpreted: Patient Lookup & Selection, Healthcare Web Shell, IAM Shell Context, Clinical Read Core, MPI, ProductAccessPDP, Wave1PolicyPDP, frozen clinical domains.

---

## 1. Baseline

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Tag | `patient-lookup-selection-frozen` |
| Parent | `1c502950011a168dbb139980ef758f2660561255` |
| Working tree at inspection | clean (this pass adds design docs only) |
| Alembic | exactly one head `20260814_0018` |
| Migration 0019 | **not created / not required** |
| `clinical.chart.read` | **does not exist** — do not invent |

---

## 2. Product boundary

Clinical Chart UI is the first Healthcare Web surface that **renders Clinical Read Core PHI**.

It is **read-only**. It consumes frozen staff GET routes. It does not call frozen per-domain command APIs. It does not add backend routes. It does not create migration `0019`.

**MVP workspace:** Clinical only (`/app/clinical` family). Audit workspace reuse with purpose `AUDIT` is **deferred**. Registration / Identity do not open chart. Patient Mobile is a separate product.

---

## 3. Clinical Read Core inventory (frozen)

Staff audience `php-api` via `require_staff_audience`. Prefix: `/api/v1/clinical/patients`. No POST/PUT/PATCH/DELETE. No `/api/v1/patient` (PatientPrincipal). No `/fhir`. No `/api/v2`.

| Method | Path | Response | Audit |
|---|---|---|---|
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart` | `ChartShellResponse` | `CLINICAL_CHART_ACCESSED` `surface=shell` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/summary` | `ClinicalSummaryResponse` (`exclude_none`) | `CLINICAL_CHART_ACCESSED` `surface=summary` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/timeline` | `TimelinePageResponse` | `CLINICAL_CHART_ACCESSED` `surface=timeline` |
| GET | `/api/v1/clinical/patients/{patient_identity_id}/chart/sections/{section}` | `SectionPageResponse` | **none** (no extra chart-open audit) |

Shared request context (all four):

- `Authorization` bearer staff JWT, audience `php-api`
- `X-Organization-Id` required (membership + `Principal.for_organization`)
- `X-Facility-Id` optional **work context** (Product Access / audit attribution). **Not** a chart data filter.
- `X-Purpose` required catalog purpose. Staff `PATIENT_ACCESS` → 403 `purpose_principal_mismatch` before identity lookup.
- Optional query `encounter_id`
- Optional query `facility_id` (`query_facility_id` alias) — **chart facility filter**, distinct from `X-Facility-Id`

Path UUID is a request key. Backend canonicalizes. UUID in the API path is not a grant.

| Case | Result |
|---|---|
| ACTIVE X | 200 canonical X |
| MERGED X → Y (request X or Y) | 200 canonical Y |
| RETIRED | 409 `identity_not_usable` |
| unknown / cross-org | 404 same message |
| missing/invalid purpose | 422 |
| unauthorized section (direct) | 403 after shell authorize |
| unknown section slug | 404 |
| unknown status/category filter | 422 |
| invalid cursor / limit | 422 |
| foreign query `facility_id` | 404 conceal |

Shell authorization: `mpi.identity.read` + membership + purpose + org-visible identity. **No `clinical.chart.read`.** Then per-section `authorize()` for section GET.

Provenance: chart reads create **zero** `clinical_provenances`.

Pagination: default `limit=50`, max `100`. Cursor opaque unsigned `{t,k,id}`. Frontend must not decode or reconstruct.

Facility default: **organization-wide**. NULL-facility facts remain visible. Query `facility_id` narrows same-org only. Facility filter never grants access.

---

## 4. Exact section catalog

From `ChartSection` / `SECTION_PERMISSIONS`. Do not invent frontend slugs.

| Section code | Domain | Required read permission(s) | Summary bucket | Timeline sources | List DTO | Status filter enum | Category filter |
|---|---|---|---|---|---|---|---|
| `encounters` | Encounter | `clinical.encounter.read` | no | `encounter` | `EncounterReadDTO` | `EncounterStatus` | `EncounterClass` |
| `notes` | Clinical note | `clinical.note.read` | no | `note` | `NoteListDTO` (**no body**) | `ClinicalRecordStatus` | **none** (422 if sent) |
| `conditions` | Condition | `clinical.condition.read` | `active_conditions` (limit 10) | `condition` | `ConditionReadDTO` | `ConditionClinicalStatus` | `ConditionCategory` |
| `observations` | Observation | `clinical.observation.read` | `recent_vitals` (limit 5, VITAL_SIGNS presentation) | `observation` | `ObservationReadDTO` | `ObservationStatus` | `ObservationCategory` |
| `laboratory` | Lab order/specimen/result | **any** of `clinical.laboratory.order.read`, `.specimen.read`, `.result.read` | `recent_lab_results` only if **result.read** (limit 5) | matching source types by permission | `LaboratoryOrderReadDTO` and/or specimen/result DTOs | depends on held layer | **none** |
| `medications` | Medication | `clinical.medication.read` | `active_medications` (limit 10) | `medication` | `MedicationReadDTO` | `MedicationStatus` | `MedicationCategory` |
| `allergies` | Allergy | `clinical.allergy.read` | `active_allergies` (limit 10) | `allergy` | `AllergyReadDTO` | `AllergyStatus` | `AllergyCategory` |
| `consents` | Consent | `clinical.consent.read` | no | `consent` | `ConsentReadDTO` | `ConsentStatus` | `ConsentCategory` |
| `immunizations` | Immunization | `clinical.immunization.read` | no | `immunization` | `ImmunizationReadDTO` | `ImmunizationStatus` | `ImmunizationCategory` |
| `procedures` | Procedure | `clinical.procedure.read` | `recent_procedures` (limit 5) | `procedure` | `ProcedureReadDTO` | `ProcedureStatus` | `ProcedureCategory` |
| `medical-devices` | Medical device | `clinical.medical_device.read` | no | `medical_device` | `MedicalDeviceReadDTO` | `MedicalDeviceStatus` | `MedicalDeviceCategory` |
| `adverse-events` | Adverse event | `clinical.adverse_event.read` | no | `adverse_event` | `AdverseEventReadDTO` | `AdverseEventStatus` | `AdverseEventCategory` |
| `family-histories` | Family history | `clinical.family_history.read` | no | `family_history` | `FamilyHistoryReadDTO` | `FamilyHistoryStatus` | `FamilyHistoryCategory` |

**Laboratory special authorization (frozen):**

- Section appears in `authorized_sections` if the actor holds **any** of the three lab read permissions.
- Direct GET `authorize()` uses the first matching permission in order: order → specimen → result; if none, `clinical.laboratory.order.read` (then 403).
- Order-only: nested `specimens` / `results` keys **omitted**, those tables not queried.
- Specimen-only / result-only: page that layer, not a fabricated full order graph.

**Notes list:** `NoteListDTO` has id, encounter, org, facility, type, record_status, version, authored_at, finalized_at, author_id, patient_identity_id. **No `body_text`.** Full body remains frozen `GET /api/v1/clinical/notes/{note_id}` (`ClinicalNoteResponse.body_text`) — **deferred** from Chart MVP.

**Date fields:** section/timeline accept `recorded_from` / `recorded_to`. Frozen P3: inverted range returns **empty page**, not 422. Frontend should prevent obviously inverted dates for UX; backend unchanged.

**Facility fields:** facts carry `facility_id` (nullable) as metadata. Chart query `facility_id` is optional filter. MVP does **not** expose it.

---

## 5. Chart shell vs summary ownership

| Concern | Owner |
|---|---|
| Patient header (name, DOB, `age_years`, sex, org MRNs, lifecycle, identity kind, requested vs canonical ids) | **GET `/chart`** `header` |
| `documented_allergy_exists` tri-state | **GET `/chart`** header: `true` / `false` if `clinical.allergy.read`; **omitted** if unauthorized |
| `authorized_sections` | **GET `/chart`** |
| Selected encounter (only if `encounter_id` query + encounter.read) | **GET `/chart`** header optional |
| Bounded clinical pointers (conditions, medications, allergies, vitals, labs, procedures) | **GET `/chart/summary`** |
| High-level “no data” for a summary bucket | Summary key present with items, **or** key omitted. Combine with `authorized_sections` — see §12 |

Do not duplicate header from summary. Summary has no patient banner fields.

Summary buckets are **omitted** when unauthorized **or** when the bounded query returns no rows (`if rows:` then set). Frontend **must not** treat a missing summary key as “no known allergies/conditions” by itself. Use:

1. `authorized_sections` for whether the domain is available
2. header `documented_allergy_exists` for allergy safety signal
3. summary items only as pointers when present

No AI, no inferred diagnosis, no medication advice. Present frozen codes/status/occurred_at only.

---

## 6. Frontend route decision

**Recommended MVP route:** `/app/clinical/chart`

**Patient UUID in URL: NO.**

Existing unused helper `patientChartPath` → `/app/clinical/patients/{uuid}` remains a frozen shell **privacy helper**, not an implemented route. Chart MVP **must not** register or navigate to that path.

| Option | Verdict |
|---|---|
| A. `/app/clinical/chart` + memory-only selected patient | **MVP** |
| B. `/app/clinical/patients/{uuid}` | Rejected for MVP |

Rationale (security bias consistent with Patient Lookup freeze and memory-only OIDC):

- Deep linking a UUID is not authority; backend still authorizes. Copied URLs + shared workstations + browser history would retain a patient identifier after logout/F5.
- Selected patient is already memory-only and tenant-bound. F5 already requires re-auth / re-select. Chart must match that contract.
- UUID in history is PHI-adjacent metadata even without name/MRN.
- API still uses `{patient_identity_id}` in the **HTTPS path to the backend**, which is not the SPA route and is not written to `history`.

No patient name, MRN, NIK, BPJS, diagnosis, medication, or note text in SPA URL, query, or hash. Section id in URL (e.g. `?section=conditions`) is allowed **only** as a closed catalog slug, not as clinical content. MVP preference: keep section in React state, not in the URL, to avoid implying a shareable chart deep link. If a section query is added later, slugs only.

**Precondition:** valid memory-only selected patient for the **current organization**. If absent: do **not** call Clinical Read. Render Clinical workspace empty/gate with **Select Patient** (same frozen `PatientLookupPanel` / `/app/patients/select`). Do not auto-redirect in a loop. Do not render clinical PHI placeholders.

---

## 7. Selected-patient contract and chart entry

Frozen `SelectedPatientSummary` (memory, tenant-bound): canonical id, org id, display name/label, DOB, sex, org MRN, kind, lifecycle, `selectedAt`. No NIK/BPJS, raw lookup input, or full lookup response.

**Entry UX (no extra auto-select):**

1. User is in Clinical workspace (or uses `/app/patients/select` with Clinical/`TREATMENT` workflow).
2. Explicit lookup confirmation → **Select Patient** (existing).
3. Banner shows selected patient.
4. Explicit **Open Chart** (Clinical workspace / banner when Clinical is available) → `/app/clinical/chart`.

Do **not** navigate to chart automatically on Select Patient (frozen lookup: no automatic chart navigation).

**Change / Close Patient:**

1. Explicit Close/Change Patient.
2. Wipe selected patient + all clinical PHI caches + section/timeline/note-detail state + in-flight requests.
3. Navigate to Patient Selection (`/app/patients/select` or Clinical lookup panel).
4. Do **not** leave old chart visible behind a lookup modal.

**Purpose vs selection:**

Chart `X-Purpose` is determined by the **active Clinical workspace**, not by the purpose used at lookup.

| Workspace opening chart | Purpose |
|---|---|
| Clinical | `TREATMENT` |

Do not silently reuse `AUDIT` / `REGISTRATION` / `IDENTITY_RESOLUTION` from a prior lookup as the chart purpose. A registrar who selected a patient under `REGISTRATION` and later opens Clinical Chart (if they can open Clinical) sends `TREATMENT`. No free-text purpose. No purpose escalation.

**Audit workspace:** MVP chart is **not** mounted there. Reuse with `AUDIT` is a deferred design. UI nav mapping is not authorization.

---

## 8. Patient safety banner and tenant context

Persistent while chart is open (and while a patient is selected in Clinical):

| Field | Source |
|---|---|
| Display name | selected patient, refreshed from chart `header` when loaded |
| DOB | header / selection |
| Age | `header.age_years` (computed server-side; null stays unknown) |
| MRN | org-scoped list from header when loaded; else selection MRN |
| Sex/gender | `administrative_sex` |
| Anonymous / temporary | `identity_kind` |
| Active organization | shell org chip (already frozen) — **must remain visible** |
| Work facility | shell facility chip, **labeled as work context**, not as chart filter |

Do not show NIK/BPJS. Do not put UUID in the banner unless needed for support and then not as the primary identity.

User must not confuse **patient** vs **tenant** vs **work facility**. Treat as clinical safety.

After shell load, if `canonical_patient_identity_id` differs from selected id, apply merge behavior (§16).

---

## 9. Work facility vs chart data

**Frozen distinction remains:**

`X-Facility-Id` = work context / Product Access / audit attribution.

Clinical Read default grain = **organization-wide**.

**Do not** copy `workFacilityId` into `?facility_id=`. The existing `clinicalBoundary` comment is now a Chart UI rule.

**Chart facility filter MVP: DEFERRED.** No UI control. No silent coupling. Longitudinal record is org-wide.

Encounter filter (`encounter_id`): **deferred** for first MVP (optional later, explicit, not work-facility-derived). Encounters section is a longitudinal list, not a schedule, and does not redefine org-wide chart scope.

---

## 10. Purpose (Clinical Chart)

Catalog (unchanged): `REGISTRATION`, `IDENTITY_RESOLUTION`, `EMERGENCY`, `CARE_COORDINATION`, `ADMINISTRATION`, `PATIENT_ACCESS`, `AUDIT`, `SYSTEM_OPERATION`, `TREATMENT`.

Staff chart rejects `PATIENT_ACCESS`.

MVP Clinical Chart always sends **`TREATMENT`**. Backend remains the authority if the purpose/principal pair is invalid.

---

## 11. Initial load strategy

Do **not** fan out 13 section requests at chart open.

Bounded sequence:

1. Selected patient exists for current org; else stop (Select Patient gate).
2. `GET /chart` (shell) — gate. On 401/403/404/409/422/5xx: **do not** load summary/sections/timeline.
3. `GET /chart/summary` in parallel **only after** shell request is dispatched with the same generation/patient/org **or** sequentially after shell 200. Prefer **after shell 200** so a failed gate does not also emit summary audit.
4. Render banner from header + `authorized_sections` navigation.
5. Default view: **Summary**.
6. Lazy-load a section only when opened.
7. Timeline only when Timeline is opened.

MVP: **no speculative prefetch** of other domains.

Expected audits for a normal open: `shell` then `summary`. Opening Timeline adds `timeline`. Opening sections adds **no** extra `CLINICAL_CHART_ACCESSED`.

Frontend **never** fabricates `CLINICAL_CHART_ACCESSED`. No audit API.

---

## 12. Section availability (source of truth)

**Recommend combination with backend as final authority:**

1. **Authoritative navigation list:** `ChartShellResponse.authorized_sections` (omits unauthorized keys). Frontend must not show a section merely because `effective_permissions` contains a matching code.
2. **UX hint only:** `effective_permissions` may hide Clinical workspace entirely (frozen PermissionGate). That is not section authorization.
3. **Direct URL/manual section request:** still call API; handle 403 as `UNAUTHORIZED` for that section. Hidden nav is UX only.

If shell omits `allergies`, do not render “No known allergies.”

---

## 13. Empty vs unauthorized vs error

Every section and summary bucket has explicit states:

| State | Meaning | Example copy (conceptual) |
|---|---|---|
| LOADING | in flight | Loading… |
| LOADED_WITH_DATA | authorized page with items | render facts |
| AUTHORIZED_EMPTY | 200, authorized, `items=[]` / no summary rows **and** section is in `authorized_sections` | No conditions documented in this record |
| UNAUTHORIZED | omitted from shell **or** 403 on direct GET | Allergy information unavailable |
| ERROR | 5xx/network/422 after authorize | Could not load this section |

**Allergy safety (critical):**

| Signal | UI |
|---|---|
| header `documented_allergy_exists === true` | allergy alert / documented allergies exist |
| header `documented_allergy_exists === false` | authorized empty for documented **active** non-EIE allergies — **not** the same as missing permission |
| header field **omitted** | **Allergy information unavailable** — never “No known allergies” |
| summary `active_allergies` present | list pointers; do not invent “NKA” |
| section 403 / omitted | UNAUTHORIZED |

Never collapse UNAUTHORIZED, ERROR, and AUTHORIZED_EMPTY into one “No allergies” state.

Same rule for conditions, medications, and every other domain.

**Counts:** display only server-provided lists. Do not fabricate totals from first-page length. Summary limits are not census counts.

---

## 14. Lazy loading, query keys, PHI cache

Thin wrappers around generated OpenAPI types (implementation will extend source OpenAPI export to include Clinical Read schemas). TanStack Query owns server state. React Context does **not** store chart PHI beyond frozen selected-patient summary.

Conceptual keys (no NIK/MRN/BPJS):

```
["clinical-chart", organizationId, patientIdentityId]
["clinical-summary", organizationId, patientIdentityId]
["clinical-section", organizationId, patientIdentityId, section, filterFingerprint]
["clinical-timeline", organizationId, patientIdentityId, cursorToken or "root", filterFingerprint]
```

Patient UUID in memory keys is acceptable. Cursor strings may appear in keys as opaque tokens; they must not be persisted.

**Memory-only.** No `persistQueryClient`, sessionStorage, localStorage, IndexedDB, Service Worker, or offline cache for chart PHI.

Override shell defaults for clinical queries:

| Option | Chart queries |
|---|---|
| `staleTime` | 30s (shell/summary); 30s sections/timeline |
| `gcTime` | 5 minutes **or less**; immediately removed on patient/org/401/logout |
| `refetchOnWindowFocus` | **false** for sections and timeline; shell/summary **false** in MVP (avoid extra `CLINICAL_CHART_ACCESSED`). Manual Refresh allowed. |
| `refetchOnReconnect` | false for PHI queries |
| `retry` | do not retry 401/403/404/409/422/429. Bounded retry (existing `shouldRetryRequest`) for 5xx/network only |

**Eviction:**

- Patient switch: `removeQueries` all `clinical-*` for previous patient **immediately**; abort in-flight.
- Org switch / 401 / logout: clear **all** clinical queries + selected patient (extend existing wipe).
- Inactive sections: rely on `gcTime`; do not keep every visited section forever across many patients (patient switch already drops them).

Last-refreshed may be shown as “Loaded at local time” without implying a backend freshness SLA. **No polling** in MVP.

---

## 15. Patient-switch and generation races (P1)

Reuse the lookup safety pattern:

**AbortSignal + generation/request identity + organization id + patient identity match + patient-keyed queries.**

Coordinator (conceptual `clinicalChartCoordinator`) distinct from tenant `abort()` (tenant abort stays signal-only per frozen shell). Chart coordinator may `abortAndInvalidate` on patient/org change.

| Scenario | Required outcome |
|---|---|
| A pending, select B, A returns last | no A name/DOB/MRN/UUID/chart/summary/section/timeline under B |
| A → B → A | first-A must not overwrite second-A merely because UUID matches; generation distinguishes selections |
| Org A chart pending, switch org B | abort+clear A PHI **before** B context is active |
| Org B context load fails | **do not** restore A chart |
| 401 / logout | wipe all chart PHI; back cannot restore |

Selected-patient store remains the only patient pointer. Chart components read current selection + generation before commit to React state.

---

## 16. Merge, retired, unknown

**Merge while chart open:** Clinical Read returns 200 with `canonical_patient_identity_id` possibly ≠ requested id.

MVP: after a **safe** shell 200 whose org and generation match:

1. If canonical id differs, update selected-patient id/header fields from `header` (still no NIK/BPJS).
2. Show non-blocking **identity updated** notice (merged source resolved to current record).
3. Retarget subsequent queries to canonical id (or keep requesting original — backend canonicalizes either; prefer canonical in keys after notice to avoid duplicate caches).

Do not keep displaying a merged source as if it were independently selectable. Do not rewrite MPI. Do not rewrite historical facts.

**RETIRED:** 409 → safe message: patient record is no longer available for clinical access. Clear section/summary/timeline PHI. Do not dump lifecycle internals.

**Unknown / cross-org:** 404 → same unavailable/not-found copy. Do **not** distinguish unknown UUID vs foreign tenant.

---

## 17. Errors, retry, revocation

**Chart shell is the gate.** Shell failure → no section/timeline/summary load (if summary not yet sent).

| Status | Chart UX |
|---|---|
| 401 | existing session expiry wipe (include clinical queries) |
| 403 | forbidden / no chart access |
| 404 | unavailable (conceal) |
| 409 | retired / unusable identity |
| 422 | generic validation; no raw identifier/cursor dump |
| 429 | generic rate limit |
| 5xx / network | retry bounded; generic error; chart not usable |

**Partial section failure:** Laboratory error must not unmount Conditions. `ClinicalSectionBoundary` per section. Shell/banner remain if already authorized.

**Permission revocation:** next shell refetch omits section; 403 on open section. Remove nav item, clear that section’s cache, do not keep showing stale authorized PHI. Backend is authority. MVP has no aggressive focus refetch; user Refresh / re-open chart / org context reload (existing membership refresh) should re-fetch shell.

---

## 18. Timeline

Frozen DTO: `source_type`, `source_id`, `occurred_at`, `organization_id`, `facility_id`, `canonical_patient_identity_id`, `source_patient_identity_id`, optional code fields, `status`, `encounter_id`.

Order (server): timestamp DESC, `source_type` ASC, `source_id` DESC. Frontend **must not** re-sort clinically.

Cursor: opaque. Never decode. Never persist. Patient A cursor must not be sent for patient B (keys + coordinator prevent this).

Default limit 50, max 100.

Filters supported: `encounter_id`, `facility_id`, `recorded_from`, `recorded_to`, `cursor`, `limit`. MVP: **no** facility/encounter filter UI. Optional date range later; prevent inverted dates in UI.

**Pagination UX: explicit Load More** (not infinite scroll) for safety and accessibility.

Duplicate prevention: append by `source_type` + `source_id`; ignore overlapping page ids. No client chronology rewrite.

Presentation: date, domain/event type, code_display/status, facility/encounter ids as context **from DTO only**. No AI summary, no diagnostic scoring.

Opening timeline emits `CLINICAL_CHART_ACCESSED` `surface=timeline`. Load More is another GET → another audit. Acceptable frozen behavior; do not add a frontend audit. Avoid refetch-on-focus to limit repeats.

---

## 19. Domain presentation rules (read-only)

- **Condition:** show frozen clinical/verification status. Do not infer “active diagnosis” beyond those fields. No AI diagnosis.
- **Medication:** exact returned facts. No recommendation, dosing advice, or reminders.
- **Allergy:** high-safety states per §13.
- **Observation / vitals:** vitals remain Observation. UI may group `recent_vitals` / `category=VITAL_SIGNS` as a **presentation** label only. No `vital_signs` backend domain.
- **Laboratory:** match three-permission model; do not assume nested specimens/results.
- **Procedures, immunizations, devices, consents, adverse events, family history:** exact catalog; no interpretation or risk scores.
- **Encounters:** longitudinal list. Work facility does not redefine historical scope.
- **Notes:** metadata list only in MVP.

**No write controls** in this capability: no Add/Edit/Sign/Order.

**No AI.**

---

## 20. Filters (MVP)

Use only frozen query params. Do not invent client-only filters that imply completeness.

MVP: **no** status/category/date/facility/encounter filter UI except what is required to render the default org-wide first page.

Later, if added: closed enums only; inverted dates blocked in UI; chart facility visually separate from work facility.

---

## 21. Component architecture (conceptual — do not implement here)

- `ClinicalChartPage` — route gate, coordinator, shell query
- `PatientSafetyBanner` — extends/replaces selected banner while chart open
- `ChartNavigation` — `authorized_sections` + Summary + Timeline
- `ClinicalSummary`
- `ClinicalSectionBoundary`
- `TimelineView` / `TimelineItem` / `LoadMoreButton`
- `SectionEmptyState` / `SectionForbiddenState` / `SectionErrorState`
- Domain presenters: `ConditionsSection`, `AllergiesSection`, `LaboratorySection`, …

Avoid a single giant chart file. Desktop-first, usable tablet. Not Patient Mobile.

---

## 22. Accessibility and privacy

Keyboard: section nav, Load More, Close Patient, Refresh. Landmarks: banner, nav, main. Announce loading/errors via `aria-live` **status strings**, not raw PHI. Focus section heading on switch. No color-only status.

Logging: never `console` patient header, conditions, meds, labs, notes, timeline, API bodies, or patient UUID unless a future debug flag is explicitly designed off by default. Chart implementation must not log PHI.

CSP: frozen shell posture. No `unsafe-eval`, third-party clinical scripts, analytics, or session replay.

No Service Worker. No offline chart.

---

## 23. Threat model

| Threat | Mitigation |
|---|---|
| Wrong patient chart | Confirmation already required; persistent banner; no auto-open |
| Cross-org PHI | Org in query keys; wipe before B active; backend org SQL |
| Stale A under B | Abort + generation + patient match + keyed cache remove |
| A→B→A UUID collision | Generation per selection, not UUID equality alone |
| Work facility silently filtering/attributing chart | Never send `?facility_id=` from work facility; label chips separately |
| Unauthorized section as “empty” | `authorized_sections` + 403 state + allergy header tri-state |
| Note body leakage | Deferred; list has no body; no note text in URL |
| PHI persistence | Memory-only Query; no SW/IDB/localStorage |
| Browser-back PHI | Memory selection; generic route; 401/logout clear |
| Permission revocation | Shell omit + 403; clear section cache |
| Merged identity confusion | Canonical from shell + notice + retarget keys |
| Retired access | 409 safe copy; clear PHI |
| Cursor tampering | Opaque pass-through; 422; never decode; never reuse across patients |
| Cache cross-patient bleed | Keys include org+patient; remove on switch |
| Oversized fan-out | Shell+summary only; lazy sections |
| Console/log PHI | Prohibition; no debug dumps |
| UUID in history | Generic `/app/clinical/chart` |
| Frontend audit spoof | No audit client |

---

## 24. Backend gap analysis

**NO NEW BACKEND ROUTES REQUIRED.**

Frozen Clinical Read Core is sufficient for first Chart UI.

Documented mappings, not blockers:

- Summary omits empty buckets the same way as unauthorized keys → combine with `authorized_sections` and allergy header tri-state.
- Inverted `recorded_from`/`recorded_to` empty page (P3, unchanged).
- `clinical_notes` org index P3 (unchanged).
- Inherited DENIED-audit rollback P2 (unchanged).
- Docker `:9100` lag may 404 Clinical Read until image catch-up (P3). Source API remains authority.

**MIGRATION 0019 = NOT REQUIRED.**

---

## 25. MVP scope vs deferred

**MVP (read-only):**

- `/app/clinical/chart` with selected-patient gate
- Patient safety banner + org/work-facility chips
- Chart shell + summary
- Navigation from `authorized_sections`
- Lazy section pages for **all frozen catalog sections the shell returns**
- Timeline with Load More
- Patient/org/401 races and wipes
- Open Chart / Close Patient
- No writes, no AI, no UUID route, no chart facility filter, no note body

**Deferred:**

- Clinical write forms
- Chart facility filter
- Encounter filter as chart grain
- Full note body (`GET /notes/{id}`)
- Audit-workspace chart (`AUDIT`)
- Advanced tables, saved filters, print/PDF/export
- Recent patients / favorites
- AI
- Patient sharing / offline
- Infinite timeline scroll
- Speculative prefetch
- `patientChartPath` UUID routing
- Nursing-specific workspace
- ORG_ADMIN chart tightening

---

## 26. Implementation-only follow-on (not this pass)

When implementation starts, expected work is frontend-only plus generated OpenAPI types from **source** FastAPI (extend healthcare-web export allowlist for Clinical Read paths/schemas). Do not modify Clinical Read Core, Patient Lookup, MPI, PDPs, or Alembic.
