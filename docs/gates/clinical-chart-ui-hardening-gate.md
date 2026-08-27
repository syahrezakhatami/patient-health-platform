# Clinical Chart UI — security / PHI / concurrency hardening gate

**Date:** 2026-08-27  
**Kind:** HARDENING GATE — not freeze  
**Baseline:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Parent:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Alembic:** `current == heads == 20260814_0018` (exactly one head). Migration **0019 not created**.  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, push, or freeze in this pass.

Authoritative contracts: `docs/architecture/clinical-chart-ui-design.md`, `docs/gates/clinical-chart-ui-design-approval.md`, `docs/architecture/clinical-chart-ui-implementation.md`, `docs/gates/clinical-chart-ui-implementation-gate.md`, plus frozen Clinical Read Core / Patient Lookup / Healthcare Web Shell gates.

---

## Verdict

**CLINICAL CHART UI = IMPLEMENTED**

**CLINICAL CHART UI HARDENING = COMPLETE**

**CLINICAL CHART UI = NOT FROZEN**

**MIGRATION 0019 = NOT CREATED**

**CLINICAL FORMS = NOT IMPLEMENTED**

**CLINICAL WRITES = NOT IMPLEMENTED**

**NOTE BODY = NOT IMPLEMENTED**

**CHART FACILITY FILTER = NOT IMPLEMENTED**

**NO COMMIT / NO TAG / NO PUSH**

Frozen backend production code is unchanged. No Clinical Read Core, MPI, Patient Lookup backend, IAM, Product Access, or clinical-domain production edits. No new clinical endpoint. No note-body request.

---

## 1. Baseline

| Item | Value |
|---|---|
| HEAD / `origin/main` / tag `patient-lookup-selection-frozen` | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Working tree | Clinical Chart UI design + implementation + hardening (frontend tests, parsers, wipe, this gate) |
| Frozen backend production | unchanged (`git diff --stat -- backend/app` empty) |
| Alembic | `20260814_0018` one head; no `0019` |

---

## 2. Route surface

Frontend consumes only:

- `GET /api/v1/clinical/patients/{id}/chart`
- `GET /api/v1/clinical/patients/{id}/chart/summary`
- `GET /api/v1/clinical/patients/{id}/chart/timeline`
- `GET /api/v1/clinical/patients/{id}/chart/sections/{section}`

No `GET /api/v1/clinical/notes/{id}`. No `/api/v2`. Frontend route remains `/app/clinical/chart` (no patient UUID, query, or hash).

---

## 3. Selected-patient gate

| Case | Result |
|---|---|
| No selected patient | gate UI; **zero** Clinical Read calls |
| Selected patient, current org | shell then summary |
| Selected patient, stale/foreign org | selection + chart PHI cleared **before** any Clinical Read |
| Cleared during shell load | late shell discarded; QueryCache empty; gate |
| Replaced during shell load | late A discarded under B |

---

## 4. Purpose

Every Clinical Read wrapper sends `X-Purpose: TREATMENT` (`CLINICAL_CHART_PURPOSE`). Lookup purposes `REGISTRATION` / `IDENTITY_RESOLUTION` / `AUDIT` are not reused. No operator purpose picker.

---

## 5. Work facility

Work facility is `X-Facility-Id` only. Chart / summary / timeline / section URLs never receive `?facility_id=`. Chart facility filter is not implemented.

---

## 6. Initial request count

Valid open:

1. **one** chart shell
2. **one** summary only after shell success + parsed header

No section fan-out. No timeline. Load token is keyed by `selectedAt` / selection epoch and assigned in `setTimeout(0)` so StrictMode remount does not double-begin. Tests assert exact `1 + 1` after a settle delay.

Invalid header or shell error: **no** summary/section/timeline.

---

## 7. Chart-access audit request count

Frozen backend (unchanged):

| Surface | `CLINICAL_CHART_ACCESSED` |
|---|---|
| Shell 200 | yes (`surface=shell`) |
| Summary 200 | yes (`surface=summary`) |
| Timeline 200 | yes (`surface=timeline`); Load More is another GET → another row |
| Section list | **none** (`section_extra == 0`) |

**Initial chart open = 2 `CLINICAL_CHART_ACCESSED` rows** (shell + summary), matching frozen Clinical Read Core. Frontend must not duplicate those GETs. Frontend never creates audit events, never calls an audit endpoint, never fabricates `CLINICAL_CHART_ACCESSED`.

Retries: 401/403/404/409/422/429 are not retried. 5xx/network: `failureCount < 2` → **max 3 attempts**. A 5xx shell that reaches the backend three times would be three frozen audit attempts if those attempts succeed; MVP does not change backend audit design. Abort is not retried (`AbortError` / `DOMException`).

---

## 8. PatientHeaderDTO OpenAPI opacity (P3, mitigated)

Frozen `@model_serializer` still collapses OpenAPI `PatientHeaderDTO` to an empty object (`additionalProperties: true`). Backend serializer was **not** patched.

**SOURCE runtime JSON** (always present unless noted):

| Key | Type | Notes |
|---|---|---|
| `requested_patient_identity_id` | UUID string | required |
| `canonical_patient_identity_id` | UUID string | required; must match envelope |
| `lifecycle_status` | string | required |
| `identity_kind` | string | required (`PERSON` / `STANDARD` / `ANONYMOUS` / `TEMPORARY`, …) |
| `display_label` | string | required |
| `given_name` | string or null | required key |
| `family_name` | string or null | required key |
| `birth_date` | string or null | required key |
| `age_years` | integer or null | **always present**, even when null |
| `administrative_sex` | string or null | required key |
| `mrn` | string[] | required |
| `documented_allergy_exists` | boolean | **omitted** when null (unauthorized / unknown) |
| `selected_encounter` | object | **omitted** when null; UI does not consume it |

Frontend uses generated OpenAPI for surrounding chart DTOs and `parseChartHeader` for this opaque header.

---

## 9. Runtime header parser and contract tests

`parseChartHeader` / `readChartHeader` fail closed (`null`, diagnostic `HEADER_CONTRACT_FAILURE = "chart_header_invalid"`). No raw payload in thrown errors, UI, or console.

Invalid/missing critical shape or envelope/header UUID mismatch: global shell error, **no** partial banner, **no** summary fan-out.

Dedicated tests: `src/chart/header.test.ts` (rename, wrong primitive, non-boolean allergy, envelope mismatch, hostile payload without PHI in the failure signal).

---

## 10. `authorized_sections`

Nav is `authorized_sections ∩` frozen catalog, catalog order. Broad `effective_permissions` do **not** reconstruct omitted sections. Unknown slug `future-clinical-domain` is ignored: no crash, no automatic GET, no authorized content, no PHI log.

---

## 11. Unauthorized vs empty / allergy / summary omit

| Signal | UI |
|---|---|
| Section omitted or 403 | information unavailable — never “No allergies/conditions/medications/labs” |
| Authorized + `200` + `items: []` | “No documented records in this section.” |
| Summary key omitted | “This overview does not include this list…” — **not** clinical absence |
| Allergy `true` | documented allergy exists |
| Allergy `false` (authorized) | no documented allergy records |
| Allergy omitted/null or unauthorized | unavailable |
| Summary error | error, not empty |
| Allergy section error | error, not empty |

Missing summary fields are never used alone to claim “No X”. Empty copy is “documented records in this section”, not universal absence.

---

## 12. Canonical merge and loop

`applyCanonicalChartPatient` updates memory selection to Y only when organization, selection epoch, and requested-or-canonical patient still match. `selectedAt` / epoch are **not** bumped → no reload loop.

Expected bounded transition: **1 shell (X) + 1 summary (Y)**. Late A/A2 after B is selected never replaces B, never shows identity-updated for B, never changes B query keys.

---

## 13. Coordinator lifecycle

`TenantLoadCoordinator` (`clinicalChartCoordinator`):

| Operation | Generation | AbortSignal | Meaning |
|---|---|---|---|
| `begin()` | `+= 1` | new controller (previous aborted) | new load token |
| `abort()` | unchanged | aborted, controller nulled | cancel in-flight **without** invalidating `isCurrent` |
| `abortAndInvalidate()` | `+= 1` | aborted | Close/select/org/logout; in-flight `isCurrent` fails |
| `isCurrent(g)` | — | — | `g === generation` |

Chart page:

1. Selection `selectedAt` changes → `setTimeout(0)` → `begin()` → load token `{generation, signal, epoch, patientId, orgId}`.
2. Token is **committed** when `load.epoch === getSelectionEpoch()` and org still matches (`loadCommitted`). Canonical merge does not change epoch/`selectedAt`, so it does not begin a new generation.
3. Shell/summary `enabled` only when `loadCommitted`. Section/timeline mount only when `loadCommitted`.
4. Idle query keys `["chart-idle", "shell"|"summary"]` are not PHI keys. Clearing idle cache / `abort()` must **not** bump generation of a committed load. `abortAndInvalidate` is reserved for identity/session teardown.
5. `queryFn` also aborts if generation, epoch, or selected patient no longer match.

---

## 14. AbortSignal composition

`mergeAbortSignals(tanstack, coordinator)` uses `AbortSignal.any` (Node 20). Fallback adds `{ once: true }` listeners. Either source aborts the fetch. Tests cover both paths and `once` cleanup.

---

## 15. Patient races

| Race | Result |
|---|---|
| A → B (shell+summary+section pending) | none of A in DOM, QueryCache, selection, or B section |
| A → B → A / close A then reselect A | first-A session cannot populate second-A (`selectedAt` / epoch) |
| Late A section / summary | not under B |
| Late A timeline page 2 | not in B pages |
| Idle-cache cleanup | current generation remains `isCurrent`; Conditions still fetch |

---

## 16. Timeline

- Cursor is opaque: passed through `URLSearchParams`; not JSON-parsed, base64-decoded, or used to derive dates/types.
- 422 (tampered cursor): safe pagination error; already-loaded rows kept; no automatic retry; other sections kept.
- Load More is serialized (`loadMoreLock` at click time); double-click → one cursor GET.
- Duplicate `source_type:source_id` across overlapping pages: one card; no client re-sort.

---

## 17. Full QueryCache wipe

`clearClinicalQueries` cancels and **removes** clinical keys immediately. `gcTime` 5 minutes is only for normal inactive cache, not Close Patient.

| Event | QueryCache | Selection | DOM |
|---|---|---|---|
| Change/Close Patient | zero `isClinicalQueryKey` entries | `null` | gate / select |
| Org switch | previous-org clinical PHI gone before B is active; B context failure does not restore A | `null` | no A chart |
| 401 | clinical entries removed | `null` | session-expired; no chart |
| Logout | patient cleared **before** `QueryClient.clear()`, then clinical keys removed again; unmount cleanup wipes if selection is already null | `null` | sign-in; Back cannot restore memory PHI |

Logout/401 previously risked recreating PHI queries while observers were still enabled. Hardening reorders `clearSensitiveClientState` and adds unmount/`!tenantBound` wipe plus `queryFn` selected-patient abort.

---

## 18. Query keys, placeholders, refetch

Keys: `["clinical-*", organizationId, patientIdentityId, section?]`. May contain UUIDs and opaque cursor as `pageParam` only. Must not contain MRN, NIK, BPJS, name, DOB, or clinical text.

`placeholderData: undefined`. No `keepPreviousData`. No previous-patient PHI as placeholder.

`refetchOnWindowFocus: false` and `refetchOnReconnect: false` on clinical queries (explicit; not library default). Window focus does not re-issue shell/summary/section/timeline. IAM shell context keeps its frozen policy.

No `prefetchQuery` / `ensureQueryData` in chart source.

---

## 19. Permission revocation and errors

Later shell without Conditions: nav hidden, Conditions cache removed, view returns to Summary.

Stale nav + section 403: that section PHI removed, information unavailable, shell refetch. Not empty.

Summary 403: shell/banner kept; summary unavailable; other nav not inferred unauthorized.

| Shell | Downstream | UI |
|---|---|---|
| 403 | none | global inaccessible |
| 404 | none | generic unavailable (no tenant-oracle) |
| 409 | none | retired; Change Patient; no sections |
| 422 | none | safe validation; no raw request object |
| 5xx | none until retry budget | bounded 3 attempts |

UI uses `ApiError` classification only (`userFacingMessage`). Production does not stringify fetch config/URL/body.

---

## 20. Catalog, notes, laboratory, observations

All frozen sections mapped. Notes: list/metadata only; `body_text` hidden; no HTML renderer; no note-by-id. Laboratory: nested `specimens`/`results` only if present; omitted nested layers are not “no laboratory data”. Observations: `category === "VITAL_SIGNS"` is presentation grouping only; non-vitals remain; no double-count.

No frontend diagnosis/risk/recommendation/medication-action/causality derivation.

---

## 21. PHI logging, URL, history, tabs, storage, XSS, a11y

No `console.*` of chart objects in app source. No Web Storage / IndexedDB / Cache API / Service Worker / cookie of selected patient or chart PHI. Org/facility UUIDs remain sessionStorage (frozen shell). No BroadcastChannel patient sync.

After Close / org switch / logout / 401, authority is memory-only; Back cannot restore usable chart PHI.

XSS: React text for name/condition/medication/allergy/lab/note metadata; no `dangerouslySetInnerHTML` / `innerHTML` / `eval`.

A11y: labeled banner/nav, `role="status"`/`alert`, Load More / Change Patient buttons, content region focused on section change, status text not color-only.

Large section: render one backend page; no automatic full walk. Fan-out: initial shell+summary; Conditions only; Allergies only; Timeline only.

Production `sourcemap: false`; no `.map` in `dist/`.

---

## 22. Quality gates

| Check | Result |
|---|---|
| `npm ci` | run |
| lint (`oxlint --deny-warnings`) | 0 errors, 0 warnings |
| typecheck | pass |
| tests | **167 passed** (previous implementation **119**; frozen lookup baseline **91**) |
| production build | pass |
| `npm audit --omit=dev` | **0** vulnerabilities (critical/high/moderate/low) |
| OpenAPI `--check` (source FastAPI, not `:9100`) | pass; `PatientHeaderDTO` remains empty-object opacity |
| backend ruff check / format --check / mypy app | pass |
| backend pytest | **442 passed** |
| Alembic | `current == heads == 20260814_0018`; no `0019` |
| health | `:9100` live **200** `alive`; ready **200** postgres/redis/object_storage `ok` |
| secret / PHI scan | synthetic fixtures only (`Ada Lovelace`, `MRN-A-0001`, fake UUIDs); no credentials |

---

## 23. P0 / P1 / P2 / P3

| Severity | Notes |
|---|---|
| P0 | None |
| P1 | A-under-B, org-under-org, unauthorized-as-empty, stale canonical overwrite, Close/logout leftover QueryCache, work-facility silent filter — **tested and blocked**. Logout wipe ordering + unmount cleanup added in this pass. |
| P2 | Inherited **DENIED-audit rollback** (unchanged, not downgraded). Allergy omission is not “no allergy”. Duplicate audit-producing GETs blocked by exact request counts. No note body. No raw clinical console dump. Revocation drops stale section PHI. |
| P3 | F5 re-select (memory-only selection); Docker `:9100` Clinical Read chart **404** (image lag, **not** rebuilt); inverted date-range frozen backend; notes org-index debt; **PatientHeaderDTO OpenAPI opacity** — mitigated by runtime parser + contract tests |

Do not downgrade PHI safety issues. None remain open as P0/P1.

---

## 24. Docker

Known image lag remains. `GET /api/v1/clinical/patients/{id}/chart` on `:9100` returned **404**. Health on `:9100` is 200. Image **not** rebuilt. Source FastAPI OpenAPI is authoritative. Do not use stale Docker OpenAPI.

---

## 25. Defects found and fixed in this pass

- Fail-closed `parseChartHeader` (OpenAPI cannot protect the DTO).
- `loadCommitted` / epoch gate so the `setTimeout(0)` gap cannot reuse a previous load.
- Timeline 422 keeps loaded rows; Load More serialized at click time.
- Section 403 → unavailable + cache drop + shell refresh; revocation returns to Summary without cancelling the navigation timeout.
- Logout/401: clear selected patient before `QueryClient.clear()`; abort AbortError without retry; unmount/`!tenantBound` QueryCache wipe so observers cannot recreate PHI.
- Dedicated hardening tests (header contract, races, wipes, fan-out, cursor, XSS, a11y, catalog facts, AbortSignal).

---

## Out of scope (confirmed)

Clinical forms, writes, note body, chart facility filter, name search, recent patients, scheduling, notifications, Patient Mobile, Platform Admin, pharmacy, subscription, AI, ambulance, FHIR, `/api/v2`, migration 0019, backend production edits, freeze, commit, tag, push.
