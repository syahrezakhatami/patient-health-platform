# Patient lookup and selection — final freeze

**Date:** 2026-08-27  
**Verdict:** PASS WITH P2  
**P0:** none  
**P1 unresolved:** none  
**P2:** inherited DENIED-audit rollback  
**PATIENT LOOKUP BACKEND:** FROZEN  
**PATIENT SELECTION UI:** FROZEN  
**PATIENT LOOKUP & SELECTION:** FROZEN  
**PATIENT LOOKUP & SELECTION:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement Clinical Chart UI, Clinical Read Core frontend calls, clinical forms, name search, recent patients, scheduling, Patient Mobile, Platform Admin, pharmacy, subscription, FHIR, `/api/v2`, or AI. Migration `0019` was not created. Frozen `POST /api/v1/mpi/identities/lookup`, MPI merge/matching semantics, ProductAccessPDP, Wave1PolicyPDP, Clinical Read Core, IAM Shell Context, and Healthcare Web Shell security contract were not modified.

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` (at freeze) |
| Published parent SHA | `1c502950011a168dbb139980ef758f2660561255` |
| Published parent tag | annotated `healthcare-web-shell-frozen` → same SHA |
| Parent of that baseline | `ca675b5a41782732995a4021fb85af7b9b29d5b5` (`iam-shell-context-frozen`) |
| Final freeze SHA | annotated tag `patient-lookup-selection-frozen` peel (this publication commit) |
| Final annotated tag | `patient-lookup-selection-frozen` → this publication commit |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration `0019` | **Not created** |
| `backend/docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `product_access_pdp.py` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical Read Core / IAM Shell Context Backend / frozen MPI identity lookup | Untouched except additive patient-lookup route |

Old tags were not moved or rewritten:

- `healthcare-web-shell-frozen`
- `iam-shell-context-frozen`
- `product-access-multi-org-context-isolation-frozen`
- `clinical-read-core-frozen`
- `product-access-tenancy-foundation-frozen`

Expected lineage:

```
healthcare-web-shell-frozen
1c502950011a168dbb139980ef758f2660561255
        |
        v
patient-lookup-selection-frozen
(this publication commit)
```

---

## B. Frozen route and DTOs

**Staff lookup route (this freeze):** `POST /api/v1/mpi/patients/lookup`

**Frozen identity lookup (unchanged):** `POST /api/v1/mpi/identities/lookup`

No additional patient search endpoints. No GET identifier search. No name search. No recent-patient list.

**Request** (`PatientLookupRequest`, `extra = forbid`):

```json
{ "lookup_type": "MRN | NIK | BPJS | PATIENT_IDENTITY_ID", "lookup_value": "string" }
```

Forbidden in body: `organization_id`, `identifier_organization_id`, `tenant_id`, `facility_id`, `purpose`, `role`, `permission`. Organization authority comes exclusively from validated `X-Organization-Id` + membership + `Principal.for_organization`. Extra fields → 422.

**Response** (`PatientLookupResponse`): `outcome`, `truncated`, `results[]`.

Approved result fields only: canonical `patient_identity_id`, `requested_patient_identity_id` when distinct, `lifecycle_status`, `identity_kind`, `display_name`, `display_label`, `birth_date`, `administrative_sex`, organization MRN, `masked_identifier` (NIK/BPJS confirmation only), `identifier_verification`, `resolved_from_merged`, `review_required`, `selectable`.

Not returned: full identifier array, raw NIK/BPJS, phone, email, address, merge graph, match scores, clinical facts, audit internals, provenance internals, submitted `lookup_value`.

---

## C. Audience, authorization, purpose

**Audience:** staff `php-api` only via existing MPI `require_staff_audience`.

| Token | Result |
|---|---|
| `php-api` (otherwise authorized) | permitted |
| `php-patient` | 401 |
| `php-platform` | 401 |
| missing / wrong / mixed `aud` | reject |
| malformed JWT | reject |

No `PatientPrincipal` access.

**Permission:** existing `mpi.identity.read`. No role-name checks.

**Path:** authenticated staff → `X-Organization-Id` → `Principal.for_organization` → Product Access → lookup service. No bypass.

**Purpose:** required valid `X-Purpose` from the existing catalog. Purpose is context, not authority.

Approved staff lookup purposes: `TREATMENT`, `REGISTRATION`, `IDENTITY_RESOLUTION`, `AUDIT`.

| Combination | Result |
|---|---|
| valid purpose + missing `mpi.identity.read` | denied |
| permission + invalid/missing purpose | denied |
| `PATIENT_ACCESS` | 403 `purpose_principal_mismatch` |

**Facility:** work facility is attribution, not a visibility predicate. Same current-org identity is returned with facility A1, A2, or omitted.

---

## D. Lookup types, exact match, indexes

MVP types: `MRN`, `NIK`, `BPJS`, `PATIENT_IDENTITY_ID`.

No name, passport, phone, email, prefix, wildcard, contains, autocomplete, or fuzzy search.

Exact match after frozen `normalize_identifier` only. Prefix, suffix, substring, `%`, `_`, and regex-looking input do not match and do not activate LIKE/regex.

| Lookup | Index / access path |
|---|---|
| NIK / BPJS | unique `uq_patient_identifiers_global_active` `(identifier_system, normalized_value)` WHERE org IS NULL |
| MRN | org-scoped `ix_patient_identifiers_organization_id` + equality on type/normalized value; `uq_patient_identifiers_org_active` uniqueness |
| UUID | PK `patient_identities.id` |

Bounded `LIMIT 6`. Existing schema sufficient. No sequential full patient-directory scan. **No migration 0019.**

---

## E. Tenant isolation, canonicalization, merge walker

**MRN:** Hospital A MRN X returns only A’s patient. Hospital B MRN X returns only B’s patient. No global MRN uniqueness assumption.

**NIK / BPJS:** foreign identifier under the current org → `200` `outcome=none` `results=[]`. No foreign patient/organization metadata. No existence oracle. Known-local identifier returns the minimal local result only.

**Canonicalization order:**

1. exact candidate
2. current-org visibility (`_is_org_visible`; no platform bypass)
3. frozen merge walker canonicalization
4. canonical survivor visibility re-check
5. minimal response

No foreign canonical survivor hop.

**Merged identity:** visible merged source X → return canonical survivor Y. X is not selectable. Historical clinical records are not rewritten.

**Merge walker:** `MAX_SURVIVOR_HOPS = 8` plus cycle detection is **defensive corruption handling**. Patient Lookup does **not** introduce official support for arbitrary multi-hop merge chains beyond frozen MPI semantics. Frozen MPI merge creation remains authoritative (merge *target* must be ACTIVE; sequential A→B then B→C can persist because B was ACTIVE when merged into C). Lookup only walks what frozen MPI already persisted.

**Cross-org merge matrix:** foreign X → local Y, local X → foreign Y, foreign X → foreign Y, local X → local Y. Only a legitimately visible canonical patient may be returned. No hop oracle.

**RETIRED:** identifier-based lookup → `200 none []`. Direct `PATIENT_IDENTITY_ID` → `409`. No full identifier leakage. Not selectable.

**ANONYMOUS:** exact supported UUID lookup returns the safe temporary/anonymous summary only. No invented MRN/NIK/BPJS. Frontend marks anonymous state.

**Unverified NIK/BPJS:** `review_required`. Must not become a confirmed selectable patient. No Select Patient action. No implicit MPI matching/merge.

**Ambiguity:** max 5 returned, deterministic `ORDER BY patient_identity_id, id`, truncated indicator. No auto-select. No first-result-wins. No pagination into a patient directory.

---

## F. Masking, 422 privacy, logging, audit

NIK/BPJS confirmation uses frozen `mask_identifier`. Malformed/short values cannot render the full sensitive identifier.

Raw `lookup_value` is not reflected in success, 409, 422, 429, 5xx, audit, logs, or frontend errors. FastAPI validation handler `del exc` so Pydantic `input` is not echoed. Re-run of malformed NIK/BPJS/MRN requests: **no raw identifier in 422 bodies**.

Application redaction keys include `lookup_value`, `identifier_value`, `bpjs`, `nik`, `mrn`. Full `PatientLookupRequest` / `PatientLookupResponse` are not logged. No PHI `console.*` on the frontend.

**Audit event:** `PATIENT_LOOKUP_ACCESSED` for authorized executed lookup, including zero-result. Metadata: `lookup_type`, `outcome`, `result_count`, `truncated`, purpose. Canonical `patient_id` only for outcome `one`. No raw MRN/NIK/BPJS, lookup value, patient name, DOB, or response payload. No `CLINICAL_CHART_ACCESSED`. Zero-result rows have null `patient_id` (security monitoring without retaining the PHI search term).

Successful lookup audit persists in the same request session. **Inherited DENIED-audit rollback remains P2.** Not redesigned here.

---

## G. Read-only, provenance, rate limit

Lookup does not mutate patient identities, identifiers, clusters, matches, merge operations, verification state, or clinical data. Only expected state write: audit event.

Lookup creates **0** `clinical_provenances`.

Global IP limiter remains active. Lookup is not exempt (only `/health/live`). 429 body is generic (`Too many requests`) with no identifier echo. Per-principal/org lookup throttle remains **P3 DEFERRED**. No new throttle policy invented in this freeze.

---

## H. Frontend route, purpose, mutation PHI, selection

**Route:** `/app/patients/select`. Approved workspace-embedded panel reuse on Registration / Clinical / Identity / Audit. Admin has no panel. No patient identifiers or UUID in the URL.

Every embedded lookup uses the same `PatientLookupPanel` / `lookupPatients` service, permission checks, purpose mapping, race protection, confirmation, PHI clearing, and storage policy. No duplicate weaker implementation.

**Generic `/app/patients/select`:** does **not** silently assume `REGISTRATION` or `TREATMENT`. When multiple approved workspace purposes apply, the user selects an approved workspace they can already open. No arbitrary purpose text entry. No purpose escalation. Single-workspace roles remain locked to that mapping.

| Workspace | `X-Purpose` |
|---|---|
| Registration | `REGISTRATION` |
| Clinical | `TREATMENT` |
| Identity | `IDENTITY_RESOLUTION` |
| Audit | `AUDIT` |

Lookup is explicit `useMutation`: `mutationKey: ["patient-lookup"]` (no raw identifier), `retry: false`, `gcTime: 0`, no refetch-on-focus, no persistent lookup cache. `clearPatientLookupMutations` on org switch / tenant reset / 401 / logout.

**Selected patient:** memory-only, tenant-bound. Fields: canonical id, org id, display name/label, DOB, sex, org MRN, kind, lifecycle, `selectedAt`. No NIK/BPJS, raw lookup input, all identifiers, or full lookup response.

Not stored in `localStorage`, `sessionStorage`, IndexedDB, URL, Service Worker, or persistent TanStack cache. No `BroadcastChannel` sharing. New tab does not inherit patient PHI through application persistence.

**Confirmation:** one deterministic result still requires explicit confirmation. No automatic selection. No automatic chart navigation.

**Wrong-patient prevention:** confirmation presents name, DOB, MRN, sex/gender, and active organization. Anonymous state is clearly indicated. NIK/BPJS are not shown unless the lookup type itself was NIK/BPJS (masked confirmation only).

---

## I. Races, wipe, XSS, URL/history, accessibility

**Same-org race:** Lookup A pending, B submitted, B finishes, A finishes last → final result remains B. Old A state is discarded/cleared, not only visually hidden.

**Cross-org PHI race (P1):** Hospital A lookup pending, switch to Hospital B, A response arrives last → no A name, DOB, MRN, UUID, result object, or selected patient becomes active/rendered under B.

**A → B → A generation:** old first-A request must not overwrite a newer second-A request merely because both share organization id A. Lookup coordinator generation distinguishes them.

**Abort:** lookup `AbortSignal` reaches `fetch`. Generation guard is the second defense. Tenant coordinator `abort()` remains signal-only (frozen shell activation). Lookup uses `abortAndInvalidate()` only.

**Org switch wipe:** clear A patient PHI immediately before B becomes active. If B context load fails, A PHI is not restored.

**401 / logout wipe:** raw lookup input, results, ambiguous results, selected patient, and mutation error are removed. Browser back cannot restore usable patient state.

**Permission revocation:** org/context without `mpi.identity.read` hides lookup UI and clears stale selected patient.

**XSS:** no `dangerouslySetInnerHTML`, `innerHTML`, `document.write`, `eval(`, or `new Function` in application sinks. Synthetic malicious patient names remain escaped React text.

**URL / history:** no patient UUID, MRN, NIK, BPJS, or name in lookup URL, query, hash, or history payload. No lookup identifiers in the OIDC return path (`/app/patients/select` is a safe return path; identifiers are not placed there).

**Accessibility:** keyboard lookup, type selector, submit, result focus, confirm, review-required, ambiguous, error announcement (`aria-live` status strings, not raw identifiers), and anonymous indicator. No mouse-only workflow.

---

## J. OpenAPI, quality gates, health, secrets

OpenAPI generated from **source FastAPI application** (backend venv Python). **Not** stale Docker `:9100`. `export_iam_openapi.py --check` and `generate_iam_types.py --check`: **ok**. `PatientLookupRequest` / `PatientLookupResponse` have no frontend drift.

| Gate | Result |
|---|---|
| `npm ci` | 132 packages |
| oxlint `--deny-warnings` | **0 errors, 0 warnings** |
| typecheck | pass |
| frontend tests | **91 passed**, 20 files (hardening baseline 91) |
| production build | pass; no `.map` |
| `npm audit --omit=dev` | 0 vulnerabilities |
| OpenAPI `--check` from source | ok |
| pytest | **442 passed** (hardening baseline 442) |
| ruff check / format | pass |
| mypy app | pass (135 files) |
| Alembic | `current == heads == 20260814_0018`; no 0019 |
| health live | 200 |
| health ready | 200 postgres/redis/object_storage `ok` |
| secret / PHI scan | synthetic fixtures only (`1234567890123456` used to prove masking); no JWT, refresh token, OIDC secret, private key, DB password, or credentials in this commit |

---

## K. P0 / P1 / P2 / P3

| Severity | Count | Notes |
|---|---|---|
| P0 | 0 | |
| P1 | 0 unresolved | Cross-org NIK/BPJS concealment, canonical hop matrix, body tenant override, audience, raw identifier return, late Org A PHI under Org B — tested and blocked |
| P2 | inherited | DENIED-audit rollback from prior backend freezes; **not** redesigned here; **not** classified as P3 |
| P3 | documented | Per-principal lookup throttle deferred; F5 re-select due memory-only session/patient state; Docker `:9100` image lag (lookup 404); source OpenAPI generation requires backend venv Python |

---

## L. Docker state

**P3 DOCKER IMAGE LAG:** process on `:9100` returns **404** for `POST /api/v1/mpi/patients/lookup`. Health live/ready 200. Image **not** rebuilt. Does **not** block this source freeze. `backend/docker-compose.yml` untouched. Source OpenAPI remains authoritative.

---

## M. Exact files included

- `backend/app/api/v1/mpi.py` (additive `POST /patients/lookup` only)
- `backend/app/api/v1/schemas.py`
- `backend/app/core/logging.py`
- `backend/app/modules/mpi/application/services.py`
- `backend/app/modules/mpi/domain/enums.py`
- `backend/app/modules/mpi/domain/patient_lookup.py`
- `backend/app/modules/mpi/infrastructure/repositories.py`
- `backend/tests/integration/test_patient_lookup.py`
- `backend/tests/integration/test_patient_lookup_hardening.py`
- `apps/healthcare-web/openapi/iam-shell.json`
- `apps/healthcare-web/scripts/export_iam_openapi.py`
- `apps/healthcare-web/src/api/generated/iam-shell.ts`
- `apps/healthcare-web/src/api/patients.ts`
- `apps/healthcare-web/src/api/errors.ts`
- `apps/healthcare-web/src/api/queryClient.ts`
- `apps/healthcare-web/src/App.tsx`
- `apps/healthcare-web/src/AppRoutes.tsx`
- `apps/healthcare-web/src/components/AppShell.tsx`
- `apps/healthcare-web/src/components/Navigation.tsx`
- `apps/healthcare-web/src/hardening/tenant-races.test.ts`
- `apps/healthcare-web/src/hardening/patient-lookup-hardening.test.tsx`
- `apps/healthcare-web/src/i18n/locales/en.json`
- `apps/healthcare-web/src/i18n/locales/id.json`
- `apps/healthcare-web/src/pages/PatientSelectPage.tsx`
- `apps/healthcare-web/src/pages/WorkspacePages.tsx`
- `apps/healthcare-web/src/patient/**`
- `apps/healthcare-web/src/routing/paths.ts`
- `apps/healthcare-web/src/styles/shell.css`
- `apps/healthcare-web/src/tenant/TenantProvider.tsx`
- `apps/healthcare-web/src/tenant/clinicalBoundary.ts`
- `apps/healthcare-web/src/tenant/generation.ts`
- `apps/healthcare-web/src/test/TestAppHarness.tsx`
- `docs/architecture/patient-lookup-selection-design.md`
- `docs/architecture/patient-lookup-selection-implementation.md`
- `docs/gates/patient-lookup-selection-design-approval.md`
- `docs/gates/patient-lookup-selection-implementation-gate.md`
- `docs/gates/patient-lookup-selection-hardening-gate.md`
- `docs/gates/patient-lookup-selection-final-freeze.md` (this file)

No Clinical Chart UI. No Clinical Read Core frontend client. No migration 0019. No ProductAccessPDP / Wave1PolicyPDP / docker-compose changes.

---

## N. Push verification

Recorded after `git push` of `main` and `patient-lookup-selection-frozen` (no force):

- `HEAD == origin/main`
- working tree clean
- `patient-lookup-selection-frozen` points to HEAD
- old tags unchanged
- Alembic still `20260814_0018`; no 0019

---

## O. Out of scope (unchanged)

**NEXT PRODUCT CAPABILITY = NOT STARTED**

- CLINICAL CHART UI = NOT IMPLEMENTED
- CLINICAL FORMS = NOT IMPLEMENTED
- NAME SEARCH = NOT IMPLEMENTED
- RECENT PATIENTS = NOT IMPLEMENTED
- PATIENT MOBILE = NOT STARTED
- PLATFORM ADMIN WEB = NOT STARTED
- SCHEDULING = NOT STARTED
- NOTIFICATIONS = NOT STARTED
- SUBSCRIPTION = NOT STARTED
- AI = NOT STARTED
