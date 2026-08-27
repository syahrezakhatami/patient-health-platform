# Clinical Chart UI — implementation

**Date:** 2026-08-27  
**Kind:** IMPLEMENTATION — not hardened, not frozen  
**Status:** COMPLETE  
**Baseline HEAD:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Parent:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** not created  

This document is not a HIPAA, ISO 27001, or SOC 2 certification. Clinical forms, clinical writes, note-body viewing, chart facility filter, name search, recent/today patients, scheduling, notifications, Patient Mobile, Platform Admin, pharmacy, subscription, AI, FHIR, `/api/v2`, Clinical Read Core changes, Patient Lookup changes, MPI changes, ProductAccessPDP, Wave1PolicyPDP, commit, tag, and push are out of scope.

Authoritative design: `docs/architecture/clinical-chart-ui-design.md`.  
Approval: `docs/gates/clinical-chart-ui-design-approval.md`.

---

## 1. Frozen baseline

| Item | Value |
|---|---|
| HEAD / `origin/main` / tag `patient-lookup-selection-frozen` | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Parent | `1c502950011a168dbb139980ef758f2660561255` |
| Branch | `main` == `origin/main` |
| Alembic | exactly one head: `20260814_0018` |
| Migration 0019 | **not created** |
| Patient Lookup & Selection | unchanged (frontend now opens chart from selection) |
| Healthcare Web Shell / IAM Shell Context / multi-org | unchanged |
| Clinical Read Core | unchanged (consumed only) |
| MPI / Product Access / ProductAccessPDP / Wave1PolicyPDP | unchanged |
| Frozen clinical domains | unchanged |

Working tree adds Healthcare Web Clinical Chart UI plus this implementation record. No backend production source edits.

---

## 2. Route and selected-patient gate

**Frontend route:** `/app/clinical/chart` (`APP_PATHS.clinicalChart`).

No patient UUID in the path, query, or hash. Frozen helper `patientChartPath` remains unused and is not registered.

**Selected patient required.** Clinical Chart reads `PatientSelectionContext` (memory-only). If none, or if `selectedPatient.organizationId !== selectedOrganization.id`:

- no Clinical Read request is issued
- a patient-selection gate is shown with a link to `/app/patients/select`
- mismatch also clears the selected patient and clinical PHI

---

## 3. Purpose and headers

Chart wrappers always send `X-Purpose: TREATMENT` (`CLINICAL_CHART_PURPOSE`). Lookup purpose is not reused. Purpose is not taken from user input. Audit-workspace chart remains deferred.

`X-Organization-Id` comes from the active shell organization. Work facility may be sent as `X-Facility-Id` only (existing `apiRequest` convention). **`?facility_id=` is never added.** Chart is organization-wide. Chart facility filter is not rendered.

Bearer token is the in-memory access token. No organization id in a request body.

---

## 4. Clinical Read wrappers

Thin typed client: `apps/healthcare-web/src/api/clinical.ts` on the existing `apiRequest` helper.

| Function | Route |
|---|---|
| `fetchChartShell` | `GET /api/v1/clinical/patients/{id}/chart` |
| `fetchChartSummary` | `GET /api/v1/clinical/patients/{id}/chart/summary` |
| `fetchChartTimeline` | `GET /api/v1/clinical/patients/{id}/chart/timeline` |
| `fetchChartSection` | `GET /api/v1/clinical/patients/{id}/chart/sections/{section}` |

No new backend routes. Timeline `limit=50` (backend max 100). Cursor is passed back unchanged when present.

---

## 5. Initial load

1. Valid selected patient for the current org  
2. Chart shell  
3. Summary **only after** shell success  
4. Section navigation from shell `authorized_sections`  
5. Default view: Summary  
6. Section GETs only when that section is opened  
7. Timeline GET only when Timeline is opened  

Shell 401/403/404/409/422/5xx stop fan-out. No 13-section request on open.

---

## 6. Patient safety banner and merged identity

`PatientSafetyBanner` shows display name, DOB, `age_years` from the chart header when present, MRN, sex/gender, anonymous/temporary indicator, active organization, and work facility as a separate field. No NIK/BPJS.

If shell `canonical_patient_identity_id` differs from the requested/selected id, `applyCanonicalChartPatient` updates memory selection to the canonical safe summary and shows a non-alarming identity-updated notice. Selection epoch / `selectedAt` is **not** bumped (does not reload as a new patient). Apply is rejected unless organization, selection epoch, and requested-or-canonical patient still match. A stale Patient A shell cannot canonicalize Patient B.

---

## 7. `authorized_sections` and empty vs unauthorized

Navigation is built from shell `authorized_sections` intersected with the frozen catalog, in catalog presentation order. Unknown slugs are ignored (no PHI in diagnostics). `effective_permissions` only gates the Clinical workspace, not section rows.

Unauthorized (omitted from shell, or later 403) renders **information unavailable**, never “no allergies/medications/conditions”.

Authorized empty is only shown when the section is authorized and a successful 200 page has zero rows (or allergy header `documented_allergy_exists === false`).

Summary omitted keys are **not** treated as clinical absence (`chart.summaryOmitted`). Counts are not fabricated from page length or nav presence.

---

## 8. Allergy tri-state

Header `documented_allergy_exists`:

| Signal | UI |
|---|---|
| `true` | documented allergy exists |
| `false` | authorized no documented allergy |
| omitted / null | do **not** show “No known allergies”; information unavailable |
| allergies not in `authorized_sections` | information unavailable |
| section load failure | error, not empty |

---

## 9. Section catalog

Frozen codes only: `encounters`, `notes`, `conditions`, `observations`, `laboratory`, `medications`, `allergies`, `consents`, `immunizations`, `procedures`, `medical-devices`, `adverse-events`, `family-histories`.

Display labels may differ (`medical-devices` → Medical Devices; `family-histories` → Family History). Codes are not mutated.

Notes: metadata/list only. `body_text` is never rendered. `GET /api/v1/clinical/notes/{id}` is not called. No HTML/rich-text note viewer.

Laboratory: nested `specimens` / `results` rendered only when present. The three-permission model is not collapsed on the frontend.

Observations: vitals grouping is presentation-only where `category === "VITAL_SIGNS"`. No `vital_signs` backend concept.

All domain sections are read-only fact cards. No Add/Edit/Delete/Sign/Order/Prescribe/Verify/Approve. No AI.

---

## 10. Timeline

Server order preserved. Opaque `next_cursor` passed through. Explicit **Load More** (no infinite scroll). Pages merged by `source_type:source_id` without duplicates. 422 cursor → safe pagination error, no retry, no client decode.

---

## 11. Query keys, cache, retry

TanStack Query owns server PHI. `PatientSelectionContext` stays selected-patient summary only.

| Key | Shape |
|---|---|
| chart | `["clinical-chart", organizationId, patientIdentityId]` |
| summary | `["clinical-summary", organizationId, patientIdentityId]` |
| section | `["clinical-section", organizationId, patientIdentityId, section]` |
| timeline | `["clinical-timeline", organizationId, patientIdentityId]` (cursor is infinite-query `pageParam`, not persisted) |

Idle placeholders use `["chart-idle", ...]` so they are not treated as PHI keys.

Policy (`clinicalQueryPolicy`): `staleTime` 30s, `gcTime` 5 minutes, `refetchOnWindowFocus: false`, `refetchOnReconnect: false`. Retry: none for 401/403/404/409/422/429; bounded (`failureCount < 2`) for 5xx/network (`shouldRetryRequest`). Memory only: no localStorage/sessionStorage/IndexedDB/Service Worker/`persistQueryClient`.

---

## 12. Races and wipes

Reuse `TenantLoadCoordinator` (`AbortSignal` + generation) plus selection epoch, org id, patient id, and patient-keyed queries. In-flight fetches merge coordinator abort with TanStack Query abort (`mergeAbortSignals` / `AbortSignal.any`).

Patient A → B: abort A, bump generation, remove A PHI, reset section/timeline/view, load B. Late A must not paint under B. A → B → A uses `selectedAt` / epoch, not UUID alone.

Org switch: selected patient cleared first (`clearPatientAndChartFilter`); `removeTenantScopedQueries` removes clinical queries. Org B context failure does not restore A.

401 / logout: `clearSensitiveClientState` clears the query client, selected patient, and tenant storage. Chart observers switch off clinical keys when tenant-bound selection is gone and then `clearClinicalQueries`.

Close / Change Patient: wipe PHI, clear selection, go to `/app/patients/select`. Authenticated org/facility remains.

409 RETIRED: shell-level unavailable copy; no section PHI kept on screen. 404: generic not available (unknown / foreign / concealed not distinguished).

Section errors are local. Shell failure is global. Summary failure leaves shell/banner when the shell succeeded.

---

## 13. XSS, URL privacy, logging, accessibility

Clinical strings go through React text. No `dangerouslySetInnerHTML` / `innerHTML` / `document.write` / `eval` / `new Function` in app source. Synthetic HTML in names and codes renders as text.

No clinical text, UUID, MRN, NIK, BPJS, or names in the chart route. No PHI in console logging. Browser back cannot restore PHI after logout/401/org switch/Close Patient because authority is memory query cache only. No BroadcastChannel / Web Storage sharing of chart or selected patient.

Accessibility: chart nav, banner landmark/label, semantic headings, loading/error `role="status"` / `role="alert"`, Load More button, focus the content region when the view changes, visible status text (not color-only). Desktop-first; reasonable tablet width. Not Patient Mobile.

---

## 14. OpenAPI

Types generated from **source FastAPI** (`export_iam_openapi.py` / `generate_iam_types.py`), not Docker `:9100`. `--check` passes.

`PatientHeaderDTO` in OpenAPI is an empty object because of the frozen custom serializer. Frontend `readChartHeader` reads the frozen JSON keys. Backend was not patched.

`ClinicalNoteResponse` is not exported in the Healthcare Web subset (avoids note-body use).

---

## 15. Tests and gates

Frontend: `apps/healthcare-web/src/chart/clinical-chart.test.tsx` plus catalog/policy tests. Frozen frontend baseline was **91** tests; this pass is **119** passed.

Covered: no-patient no API; shell then summary; TREATMENT; no `facility_id`; banner; `authorized_sections`; unauthorized vs empty; allergy true/false/omitted; lazy sections; notes metadata-only; timeline Load More / opaque cursor / 422; 409/404; merged identity; A→B; A→B→A; late A section; org switch failure; Close Patient; 401; logout; XSS; storage; request-count bound; unknown section ignore.

Backend: **442 passed** (published baseline). ruff / mypy clean. No production backend edits.

Health: `/api/v1/health/live` 200, `/api/v1/health/ready` 200 (`postgres`, `redis`, `object_storage` ok).

Docker `:9100` Clinical Read chart returns **404** (inherited P3 image lag). Image was not rebuilt. Source OpenAPI is authoritative.

---

## 16. Deviations from design

| Topic | Handling |
|---|---|
| `PatientHeaderDTO` OpenAPI empty object | Presentation wrapper over frozen JSON keys; backend untouched |
| Timeline key omits cursor token | Infinite query `pageParam`; cursor not persisted |
| Unknown `authorized_sections` slug | Ignore; no PHI diagnostic log |
| Load token assigned in `setTimeout(0)` | Satisfies oxlint `set-state-in-effect`; coordinator + epoch still apply |
| Summary omit-empty | UI shows “not included in this overview”, not authorized empty |

No missing backend/policy decision required a backend patch. Implementation is not blocked.
