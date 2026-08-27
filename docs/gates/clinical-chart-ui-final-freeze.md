# Clinical Chart UI — final freeze

**Date:** 2026-08-27  
**Verdict:** PASS WITH P2  
**P0:** none  
**P1 unresolved:** none  
**P2:** inherited DENIED-audit rollback  
**CLINICAL CHART UI:** FROZEN  
**CLINICAL CHART UI:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement clinical forms, clinical writes, note-body viewing, chart facility filter, name search, recent patients, scheduling, notifications, Patient Mobile, Platform Admin, pharmacy, subscription, AI, ambulance, FHIR, or `/api/v2`. Migration `0019` was not created. Frozen Clinical Read Core, Patient Lookup & Selection, MPI, ProductAccessPDP, Wave1PolicyPDP, IAM Shell Context, Healthcare Web Shell, and frozen clinical-domain production backends were not modified.

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` |
| Published parent SHA | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Published parent tag | annotated `patient-lookup-selection-frozen` → same SHA |
| Parent of that baseline | `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`) |
| Final freeze SHA | annotated tag `clinical-chart-ui-frozen` peel (this publication commit) |
| Final annotated tag | `clinical-chart-ui-frozen` → this publication commit |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration `0019` | **Not created** |
| `docker-compose.yml` | Untouched |
| Clinical Read Core / MPI / Patient Lookup backend / IAM / Product Access / PDPs / frozen clinical domains | Untouched |

Old tags were not moved or rewritten:

- `patient-lookup-selection-frozen`
- `healthcare-web-shell-frozen`
- `iam-shell-context-frozen`
- `product-access-multi-org-context-isolation-frozen`
- `clinical-read-core-frozen`
- `product-access-tenancy-foundation-frozen`
- `wave-2b-clinical-foundation-complete`

Expected lineage:

```
patient-lookup-selection-frozen
007af5c5fffd095124013eba239913c00ceeff6b
        |
        v
clinical-chart-ui-frozen
(this publication commit)
```

---

## B. Frozen frontend route and Clinical Read surface

**Frontend route:** `/app/clinical/chart` (`APP_PATHS.clinicalChart`).

No patient UUID, name, MRN, NIK, BPJS, or clinical text in path, query, or hash. Frozen helper `patientChartPath` remains unused and is not registered.

**Consumed Clinical Read routes (GET only):**

| Route | Audit |
|---|---|
| `/api/v1/clinical/patients/{id}/chart` | `CLINICAL_CHART_ACCESSED` `surface=shell` |
| `/api/v1/clinical/patients/{id}/chart/summary` | `CLINICAL_CHART_ACCESSED` `surface=summary` |
| `/api/v1/clinical/patients/{id}/chart/timeline` | `CLINICAL_CHART_ACCESSED` `surface=timeline` (each successful page) |
| `/api/v1/clinical/patients/{id}/chart/sections/{section}` | **none** |

No note-body endpoint. No new backend route. No `/api/v2`. No FHIR.

---

## C. Selected-patient gate, purpose, work facility

Selected patient is memory-only (`PatientSelectionContext` / `selectionStore`).

| Case | Result |
|---|---|
| No selected patient | gate; **zero** Clinical Read requests |
| Org mismatch / stale org id | clear selected patient + chart PHI **before** any Clinical Read |
| Valid current-org patient | chart load allowed |

Every Clinical Read wrapper sends `X-Purpose: TREATMENT`. Lookup purposes `REGISTRATION` / `IDENTITY_RESOLUTION` / `AUDIT` are not reused. No purpose picker.

Work facility is `X-Facility-Id` only. Chart / summary / timeline / section URLs never receive `?facility_id=`. Longitudinal chart is organization-wide. Chart facility filter remains deferred.

---

## D. Initial request sequence and audit count

Valid open: **1 shell** → shell 200 + parsed header → **1 summary**. No section. No timeline. No duplicate shell/summary.

Frozen backend audit (unchanged):

- Initial open (one successful shell + one successful summary) = **2 `CLINICAL_CHART_ACCESSED`**
- Timeline: one event per successful page GET
- Sections: **zero** extra `CLINICAL_CHART_ACCESSED`

Frontend never fabricates audit events or calls an audit API.

---

## E. PatientHeaderDTO opacity, runtime parser, banner

OpenAPI `PatientHeaderDTO` remains an empty object because of the frozen omit-null serializer. Backend was not patched. **P3, mitigated.**

Mitigation:

- SOURCE runtime JSON shape documented in the hardening gate
- fail-closed `parseChartHeader` / `readChartHeader`
- dedicated contract tests (`header.test.ts`)
- invalid critical shape → safe shell error, no summary, no partial/misbound banner
- parser failures do not dump PHI

**PatientSafetyBanner** uses: display name, DOB, `age_years`, MRN, sex/gender, anonymous/temporary indicator, active organization, work facility as a separate field. No NIK/BPJS. Banner follows current canonical patient and current selection epoch.

---

## F. authorized_sections, catalog, empty vs unauthorized

Navigation is `authorized_sections ∩` frozen catalog. `effective_permissions` do not reconstruct Clinical Read authorization.

Unknown server section (e.g. `future-clinical-domain`): ignore; no arbitrary GET; no crash.

**Exact catalog:** `encounters`, `notes`, `conditions`, `observations`, `laboratory`, `medications`, `allergies`, `consents`, `immunizations`, `procedures`, `medical-devices`, `adverse-events`, `family-histories`.

Unauthorized (omitted or 403) = information unavailable. Never “No allergies/medications/conditions/labs”.

Authorized + 200 + zero records = approved empty wording (“No documented records in this section.”), distinct from unauthorized/error/loading.

Allergy tri-state: authorized `true` / authorized `false` / omitted-or-null / unauthorized / summary failure / section failure remain distinct. Omitted/null does not infer no allergy.

Summary omitted lists: “This overview does not include this list…” — missing buckets never prove clinical absence. No client-side diagnosis, risk, severity inference, medication advice, or AI summary.

---

## G. Lazy loading, query keys, PHI cache

Initial: shell + summary only. Open Conditions → conditions only. Open Allergies → allergies only. Open Timeline → timeline only. No prefetch / hover prefetch / load-all.

Query keys may contain organization UUID, patient UUID, section code. Forbidden: MRN, NIK, BPJS, name, DOB, clinical text. Timeline cursor is infinite-query `pageParam`, not persisted.

Clinical server state is **memory-only** TanStack Query. No localStorage / sessionStorage / IndexedDB / Service Worker / Cache API / `persistQueryClient` / BroadcastChannel PHI sync. Inactive `gcTime` ≤ 5 minutes. Close Patient / org switch / 401 / logout **remove** clinical queries immediately.

---

## H. Races, coordinator, AbortSignal, timeline

`TenantLoadCoordinator`:

| Call | Effect |
|---|---|
| `begin()` | generation += 1; new AbortController (previous aborted) |
| `abort()` | cancel signal only |
| `abortAndInvalidate()` | cancel + generation += 1 |

Load token is deferred after `selectedAt` / epoch change. `loadCommitted` only when `load.epoch === getSelectionEpoch()`. Idle-cache cleanup must not invalidate a committed generation.

Fetch signal = TanStack cancellation `AbortSignal.any` coordinator cancellation. Fallback listeners use `{ once: true }`.

Canonical merge X→Y: update selection only when org, epoch, and requested-patient context match. Identity-updated notice. No re-request loop (1 shell + 1 summary). Stale A/A2 after B is selected cannot change B.

A→B, A→B→A, close-then-reselect-A, late section/summary/timeline: only the current session is visible or cached.

Timeline: opaque cursor, `limit=50`, explicit Load More, server order, no infinite scroll, no cursor decode. Rapid Load More is serialized. Duplicate `source_type:source_id` shown once. 422 keeps loaded rows, safe pagination error, no retry.

---

## I. Wipes, revocation, errors, retry

Close / Change Patient: wipe clinical QueryCache, abort, `selectedPatient = null`, then selection flow. Org switch: clear patient, abort, remove old-org clinical queries before B is active. Org-switch B failure does not restore A. 401 and logout: selection cleared first, clinical cache removed, chart DOM gone, Back cannot restore memory PHI.

Permission revocation / section 403: nav updated, section PHI removed, view moves to Summary/unavailable.

Shell 403 = global unavailable. 404 = generic concealed unavailable. 409 = clear PHI, retired/unavailable. 422 = safe validation. 5xx/network = bounded retry. No downstream GETs after shell failure. Summary failure keeps valid shell/banner and section nav. Section errors stay local.

No retry: 401, 403, 404, 409, 422, 429, AbortError. 5xx/network: `failureCount < 2` → **max 3 attempts**. Clinical `refetchOnWindowFocus = false`, `refetchOnReconnect = false`.

---

## J. Notes, laboratory, observations, writes

Notes: metadata/list only. No note-body GET, note-by-id, HTML renderer, or `dangerouslySetInnerHTML`. Laboratory uses returned nested payload only. Observations: `VITAL_SIGNS` is presentation grouping only; non-vitals remain; no duplicate records; no `vital_signs` domain.

Empty-state wording does not claim universal clinical absence beyond returned records.

No Add / Edit / Delete / Sign / Order / Prescribe / Approve / Verify clinical actions. Read-only.

---

## K. Privacy, XSS, a11y, performance

No chart/header/section/timeline objects in `console.*`. Production UI uses safe `ApiError` classification only (no raw fetch URL/headers/body/config).

XSS sinks (`dangerouslySetInnerHTML`, `innerHTML`, `document.write`, `eval`, `new Function`) are absent from app source. Hostile clinical strings render as text.

Route `/app/clinical/chart`. After Close Patient / org switch / 401 / logout, Back cannot restore usable chart PHI. No multi-tab selected-patient/chart sharing.

Keyboard: Summary, section nav, Change Patient, Load More; content region focused on view change; loading/error `role="status"` / `alert`; status text not color-only.

Opening chart does not fan out 13 section calls. No auto-fetch-all pages.

Production `sourcemap: false`; no `.map` files.

---

## L. Quality gates (this publication)

| Check | Result |
|---|---|
| `npm ci` | run |
| lint (`oxlint --deny-warnings`) | 0 errors, 0 warnings |
| typecheck | pass |
| tests | **167 passed** |
| production build | pass |
| `npm audit --omit=dev` | 0 vulnerabilities (critical/high/moderate/low) |
| OpenAPI `--check` (source FastAPI, not `:9100`) | pass; `PatientHeaderDTO` remains opaque |
| backend ruff check / format --check / mypy app | pass |
| backend pytest | **442 passed** |
| Alembic | `current == heads == 20260814_0018`; no `0019` |
| health `:9100` | live 200 `alive`; ready 200 postgres/redis/object_storage `ok` |
| secret / PHI scan | synthetic fixtures only; no JWT/OIDC secrets/private keys/DB passwords in this pass |

---

## M. P0 / P1 / P2 / P3

| Severity | Notes |
|---|---|
| P0 | none |
| P1 unresolved | none |
| P2 | inherited **DENIED-audit rollback** (unchanged, not downgraded) |
| P3 | F5 re-select (memory-only selection); Docker `:9100` Clinical Read **404** (image lag, not rebuilt); inverted date-range frozen backend behavior; notes organization-index performance debt; PatientHeaderDTO OpenAPI opacity, mitigated by fail-closed parser + contract tests |

---

## N. Docker

Known inherited P3: `GET /api/v1/clinical/patients/{id}/chart` on `:9100` returned **404**. Health on `:9100` is 200. Image was **not** rebuilt. Source FastAPI is authoritative for this freeze. Do not use stale Docker OpenAPI.

---

## O. Exact files included

Design / gates:

- `docs/architecture/clinical-chart-ui-design.md`
- `docs/architecture/clinical-chart-ui-implementation.md`
- `docs/gates/clinical-chart-ui-design-approval.md`
- `docs/gates/clinical-chart-ui-implementation-gate.md`
- `docs/gates/clinical-chart-ui-hardening-gate.md`
- `docs/gates/clinical-chart-ui-final-freeze.md`

Chart UI and tests:

- `apps/healthcare-web/src/chart/**`
- `apps/healthcare-web/src/api/clinical.ts`
- `apps/healthcare-web/src/tenant/generation.test.ts`

Wiring / generated OpenAPI for frozen Clinical Read source:

- `apps/healthcare-web/openapi/iam-shell.json`
- `apps/healthcare-web/scripts/export_iam_openapi.py`
- `apps/healthcare-web/src/api/generated/iam-shell.ts`
- `apps/healthcare-web/src/api/errors.ts`
- `apps/healthcare-web/src/api/queryClient.ts`
- `apps/healthcare-web/src/auth/sessionLifecycle.ts`
- `apps/healthcare-web/src/AppRoutes.tsx`
- `apps/healthcare-web/src/components/AppShell.tsx`
- `apps/healthcare-web/src/i18n/locales/en.json`
- `apps/healthcare-web/src/i18n/locales/id.json`
- `apps/healthcare-web/src/pages/WorkspacePages.tsx`
- `apps/healthcare-web/src/patient/PatientLookupPanel.tsx` (select wipes chart; Open Chart entry)
- `apps/healthcare-web/src/patient/PatientSelectionProvider.tsx` (clear wipes chart)
- `apps/healthcare-web/src/patient/SelectedPatientBanner.tsx` (Open Chart)
- `apps/healthcare-web/src/patient/selectionStore.ts` (epoch + canonical apply)
- `apps/healthcare-web/src/routing/paths.ts`
- `apps/healthcare-web/src/security/security.test.ts`
- `apps/healthcare-web/src/styles/shell.css`
- `apps/healthcare-web/src/tenant/clinicalBoundary.ts` (abort clinical coordinator)
- `apps/healthcare-web/src/tenant/generation.ts` (`mergeAbortSignals`)

No `backend/app` production files. No migration `0019`.

---

## P. Push verification

After publication:

- `HEAD == origin/main`
- working tree clean
- annotated `clinical-chart-ui-frozen` points to HEAD
- Alembic `current == heads == 20260814_0018`
- old freeze tags unchanged
- no force push

---

## Out of scope (confirmed)

Clinical forms, clinical writes, note body, chart facility filter, recent patients, name search, scheduling, notifications, Patient Mobile, Platform Admin, pharmacy, subscription, AI, FHIR, `/api/v2`, migration 0019, backend production edits.
