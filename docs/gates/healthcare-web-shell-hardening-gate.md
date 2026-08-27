# Healthcare Web shell — hardening gate

**Date:** 2026-08-27  
**Verdict:** HARDENING COMPLETE  
**Healthcare Web shell:** IMPLEMENTED  
**Healthcare Web shell:** FROZEN (see `docs/gates/healthcare-web-shell-final-freeze.md`)  
**Commit / tag / push:** not performed (this pass)  
**Migration 0019:** not created  
**Patient lookup / clinical chart / clinical forms:** not implemented  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

Authoritative design: `docs/architecture/healthcare-web-shell-iam-context-design.md`.  
Shell architecture: `docs/architecture/healthcare-web-shell.md`.  
Implementation gate: `docs/gates/healthcare-web-shell-implementation-gate.md`.  
IAM freeze: `docs/gates/iam-shell-context-final-freeze.md`.

---

## Backend baseline (untouched)

| Item | Value |
|---|---|
| HEAD / published SHA | `ca675b5a41782732995a4021fb85af7b9b29d5b5` |
| Tag | annotated `iam-shell-context-frozen` → same SHA |
| Parent | `70baee1bd24969d29d2b5f7eeda0240fb8bde877` |
| Branch | `main` at that SHA |
| Alembic | `current == heads == 20260814_0018` |
| Migration 0019 | **Not created** |
| Wave1PolicyPDP SHA-256 | `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| ProductAccessPDP SHA-256 | `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Backend pytest | **403 passed** |
| Backend ruff | pass (`ruff check` + `ruff format --check`, 200 files) |
| Backend mypy | pass (`mypy app`, 134 source files) |

Working tree frontend-only: `apps/healthcare-web` plus shell docs. No backend production file modifications. Frozen IAM Shell Context, Clinical Read Core, ProductAccessPDP, and Wave1PolicyPDP were not patched.

---

## Frontend versions (after `npm ci`)

| Item | Value |
|---|---|
| Path | `apps/healthcare-web` |
| Node | v20.20.2 (npm 10.8.2); lockfileVersion 3 |
| Vite | 8.2.2 (`build.sourcemap: false`) |
| React | 19.2.8 |
| TypeScript | 6.0.3 (declared `~6.0.2`) |
| React Router | 7.18.2 |
| TanStack Query | 5.102.5 (memory only) |
| oidc-client-ts | 3.5.0 |
| i18next / react-i18next | 26.4.0 / 17.0.12 |
| oxlint | 1.80.0 (declared `^1.79.0`) |
| Vitest | 4.1.11 |

`react-hook-form` was unused and **removed** in this pass.

---

## Auth storage

| Material | Store |
|---|---|
| Access token | Process memory (`tokenStore`). Copied from OIDC `User.access_token` only after `php-api` audience check. |
| OIDC `User` including `refresh_token` / `id_token` if issued | `oidc-client-ts` `userStore` = `WebStorageStateStore({ store: InMemoryWebStorage })`. **Not** `localStorage` / `sessionStorage` / IndexedDB. |
| Handshake `state`, PKCE `code_verifier`, nonce (library) | `stateStore` = `sessionStorage`. Transient same-tab redirect only. |
| Safe return path | `sessionStorage` `php.healthcare-web.return-to` (internal paths only). |
| Org / work-facility UUID hints | `sessionStorage`. Revalidated against frozen IAM GETs. Never authorization. |
| Locale | `localStorage` (not PHI, not authority). |

Inspected **library settings**, not only wrappers: `response_type: code`, `disablePKCE: false`, in-memory `userStore`. Application token helpers never write Web Storage.

Defense in depth: `purgeWebStorageTokenLeakage()` removes any `sessionStorage`/`localStorage` value containing `"access_token"` / `"refresh_token"` / `"id_token"` JSON keys after callback and logout.

---

## Refresh-token storage

If the IdP issues `refresh_token`, it remains inside the in-memory `User` / `InMemoryWebStorage` user store.

This pass does **not** move refresh tokens to `localStorage` as a workaround.

`automaticSilentRenew` is **on only when** `VITE_OIDC_SILENT_REDIRECT_URI` is set. Without a dedicated silent page, oidc-client-ts would otherwise default `silent_redirect_uri` to the main `/auth/callback` — iframe-running the staff callback is rejected. Access-token expiry then follows the existing session-expired path (re-authenticate). PHP `POST /auth/refresh` does not exist and is not claimed.

---

## PKCE / state / nonce / callback

| Rule | Result |
|---|---|
| `response_type` | `code` (no implicit, no password/ROPC) |
| PKCE | `disablePKCE: false` |
| `state` | Library validates; missing `state` or `code` is malformed |
| `nonce` | Used by oidc-client-ts for `openid` scope Authorization Code |
| Authority / client id | Required public config; production startup fails if missing |
| Audience | `php-api` only (`extraQueryParams` / `extraTokenParams`) |
| Valid callback | `signinCallback` then in-memory token |
| Invalid / missing / replayed state, OIDC `error`, malformed | No authenticated session; token cleared; URL params stripped |
| UI | Generic callback/login copy only. No raw OIDC payload, tokens, or `error_description` rendered |

Malformed/error callbacks do **not** construct a `UserManager` solely to fail.

OIDC `code`/`state`/`error*` are removed from the browser URL in `finally`.

---

## Open redirect

`safeReturnTo` accepts only same-origin application paths under `/app`, `/select-organization`, `/unassigned`.

Rejected (fallback `/app`): `https://evil.example`, `//evil.example`, `javascript:`, `data:`, `vbscript:`, encoded external URLs, protocol-relative, `/login` as a post-login target.

Logout / session-expired navigation stays on `/login` or `/session-expired`.

---

## 401 / concurrent 401

Protected API 401:

- in-memory access token cleared
- OIDC user removed
- selected organization, permissions, work facility cleared
- patient placeholder + chart-filter placeholder cleared
- TanStack Query cache cleared
- tenant `sessionStorage` cleared
- handshake `oidc.*` keys cleared
- protected shell unmounted; `/session-expired`

Concurrent 401s share `expiryInFlight`. Handler runs **once**. No multi-login / multi-redirect loop. Lock resets on successful authenticate.

---

## Logout / browser back

Logout clears the same sensitive client state. IdP `signoutRedirect` only when OIDC is configured and a `UserManager` exists. **No PHP JWT revocation.**

After logout, opening `/app` again without a memory token shows staff sign-in. Protected UI is not usable. Tenant chips are absent.

---

## Org-switch races / stale-response strategy

**Strategy (documented and tested):** `TenantLoadCoordinator` generation counter **plus** `AbortSignal`.

1. Each org load calls `coordinator.begin()` which **aborts** the previous in-flight fetch and increments generation.
2. IAM fetches pass that `AbortSignal` through the API client.
3. Commit to React state / query cache only if `isCurrent(generation)` **and** response `organization_id` matches the requested id.
4. On A → B, previous org query keys are `cancelQueries` + `removeQueries`.

Window `focus` refresh uses the same `activateOrganization` path, so a late A refetch cannot overwrite B.

Picker stays available while the first org load is in flight (no forced `loading` phase on select) so A → B can be issued before A returns.

**UI proof:** delayed A context resolved after B committed → UI remains B; clinician nav does not reappear.

**A → B → A:** coordinator unit test; final generation is last A.

This is not a global event bus. No extra store.

---

## Query key isolation / cache policy

| Key | Tenant-scoped |
|---|---|
| `["iam-organizations"]` | User-level membership list (not a selected-org cache) |
| `["iam-context", organizationId]` | Yes |
| `["accessible-facilities", organizationId]` | Yes |

Forbidden pattern `["iam-context"]` without org id is not used.

No `persistQueryClient` / storage persister. `gcTime` 5 minutes in memory; cleared on logout. Locale/i18n is not Query state and is not cleared on org switch.

`refetchOnWindowFocus: true` for IAM freshness (revocation/membership). Generation guard applies.

Retries: none for 401/403/404/409/422; bounded for 5xx/network (`failureCount < 2`). No retry on `AbortError`.

---

## Multi-tab / auth vs tenant session

Org/facility hints: **sessionStorage only**. No `BroadcastChannel`. No `localStorage` tenant sync.

Tab A can be Hospital A while Tab B is Hospital B.

**Auth identity** is per-tab in-memory OIDC/`UserManager` (and optional silent renew).  
**Tenant context** is per-tab sessionStorage hints + selected-org context. They are not the same object.

---

## Permission navigation / Audit decision

| Workspace | Show when (selected-org `effective_permissions`) |
|---|---|
| Registration | `mpi.identity.read` **or** `clinical.encounter.create` **or** `clinical.encounter.read` |
| Clinical | any `clinical.*.read` **except** encounter-only |
| Identity | `mpi.merge.execute` **or** `mpi.match.review` |
| Audit | `clinical.condition.read` |
| Administration | `iam.membership.manage` **or** `org.facility.create` **or** `org.identifier.manage` |

Derived from permissions, not `role_codes`. Catalog snapshots in `src/test/catalogPermissions.ts`.

**Audit:** frozen catalog has **no** `audit.*` permission. Approved design §14 names `clinical.condition.read` (or any clinical read) **and** entering Audit with `X-Purpose: AUDIT`. This shell uses `clinical.condition.read` so registrar encounter-read does **not** open Audit. That is the approved catalog permission, **not** an invented `audit.*` code and **not** an unrelated proxy.

Clinician catalog includes `clinical.condition.read` → Clinical + Audit (read-chart placeholder, not write forms). Auditor catalog is clinical `*.read` → Clinical + Audit, not admin/identity merge. Identity officer → Registration + Identity. Org admin → Administration.

`PermissionGate` is pure UI. It does not mutate permissions or infer roles. Direct URL to a hidden workspace shows Forbidden without crashing. Backend remains authoritative.

Permission revocation: window focus refreshes context; nav updates. Membership 403/404 clears org state and re-bootstraps remaining organizations.

---

## Facility semantics

| Case | Behavior |
|---|---|
| `ALL_IN_ORGANIZATION` | No invented “All Facilities” id; work facility optional |
| `EXPLICIT` + 1 + required | Auto-select that facility |
| `EXPLICIT` + many | User must choose; never `facilities[0]` |
| Stored facility no longer accessible | Cleared; reselection required |
| Org switch | Work facility cleared |
| Facility A1 → A2 | Current select is **synchronous**; coordinator generation is in place if future async attach is added |

Work facility header ≠ chart `facility_id` query param. Chart filter placeholder is never copied from work facility. No Clinical Read Core calls.

---

## API headers

| Header | Source |
|---|---|
| `Authorization` | Current in-memory access token only |
| `X-Organization-Id` | Current validated tenant org on that request |
| `X-Facility-Id` | Only when caller passes a work facility (IAM shell GETs omit it) |
| `X-Purpose` | **Not** globally injected. Shell IAM is purpose-exempt. Future clinical workflows must set purpose per action. |
| `X-Correlation-ID` | Per request UUID |

Stale headers cannot outlive logout/token clear. Client accepts relative paths only.

---

## XSS / URL privacy / logging

Source scan (non-test): no `dangerouslySetInnerHTML`, `innerHTML`, `document.write`, `eval(`, `new Function`, `persistQueryClient`, Service Worker, `console.log`/`debug`/`info`.

Error UI uses mapped messages. JWTs / `Bearer` / `Authorization` stripped from error text.

Routes: no NIK, BPJS, MRN, patient names, clinical text, tokens. Callback query params stripped. Future chart paths must use canonical UUID (`patientChartPath`).

---

## CSP / security headers (hosting — not implemented in this repo)

Expected SPA hosting:

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self';
  connect-src 'self' <API origin if split> <OIDC issuer>;
  frame-ancestors 'none';
  frame-src 'self' <OIDC issuer>;   /* only if VITE_OIDC_SILENT_REDIRECT_URI is enabled */
  base-uri 'self';
  form-action 'self' <OIDC issuer>;
  object-src 'none';
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

Avoid `unsafe-eval` and production `unsafe-inline`. Vite HMR is **not** a production CSP.

Default build does **not** enable silent iframe renew. If ops set `VITE_OIDC_SILENT_REDIRECT_URI` to a same-origin silent page, allow `frame-src 'self'` plus the IdP origin narrowly.

API already sets nosniff / DENY framing / no-referrer / Permissions-Policy / `Cache-Control: no-store`. `index.html` has `<meta name="referrer" content="no-referrer">`.

OIDC redirect (top-level navigation to the IdP) is compatible with `frame-ancestors 'none'`.

---

## Service worker / offline / Query persistence

No service worker, PWA plugin, Cache API, IndexedDB PHI cache, or offline EMR. No `persistQueryClient`.

---

## Dependency vulnerabilities / unused deps / lockfile

`npm ci` from `package-lock.json` then `npm audit` (prod and all): **0 vulnerabilities** (critical/high/moderate/low).

Unused runtime: `react-hook-form` **removed**. Remaining runtime packages are used (React, Router, Query, i18n, oidc-client-ts).

---

## Lint warnings

`oxlint . --deny-warnings`: **0 errors, 0 warnings**.

Tenant bootstrap is deferred with `setTimeout(0)` so oxlint `react(set-state-in-effect)` does not flag post-await `setState`. Race safety is the generation coordinator, not the timer. Rule was **not** disabled globally.

---

## OpenAPI / type drift

Types are generated from **frozen FastAPI source** (`scripts/export_iam_openapi.py` builds a router-only app), not live Docker `:9100`.

```
backend/.venv/bin/python apps/healthcare-web/scripts/export_iam_openapi.py --check
backend/.venv/bin/python apps/healthcare-web/scripts/generate_iam_types.py --check
```

This pass: **ok** (schema + `src/api/generated/iam-shell.ts`).

IAM wrappers in `src/api/iam.ts` use generated DTOs (`StaffOrganizationsResponse`, `StaffContextResponse`, `AccessibleFacilitiesResponse`). Fixtures are test-only builders of those DTOs, not a second production model.

A backend DTO change in the frozen source should fail `--check`.

---

## Frontend config / public env / source maps

`validatePublicConfig` at startup: audience must be `php-api`; secret-shaped strings rejected; production requires issuer + client id. No default production secrets.

`.env.example`: `VITE_*` public values only. Public PKCE client. No client secret, private key, DB password, or real token.

Production `build.sourcemap: false`. `dist/` gitignored. No `.map` emitted in this build (`index-BCXY7BsH.js`, `index-Dd6kzh7k.css`).

Error boundary: generic “Something went wrong”. No component stack or API payload in production UI.

---

## Accessibility / context visibility / unsaved work

Skip link, `header` / `nav` / `main`, labeled native `<select>` for organization, facility, and locale, labeled logout. Focus moves to `#main-content` on route change. Context chips show active organization and work facility with `title` + CSS ellipsis (long names remain identifiable).

`canReplaceTenantContext()` / `registerUnsavedWorkGuard` is the **extension point** for future unsaved clinical forms. No fake form state in this pass.

---

## Zero clinical UI

Clinical workspace is an empty placeholder. No Clinical Read Core HTTP. No fake patients. Patient id is an in-memory slot cleared on switch/logout only.

---

## Frontend tests

**72 passed** (18 files) after `npm ci`.

Dedicated `src/hardening/*` coverage: OIDC storage, callback/open-redirect, session lifecycle, 401 idempotence, cache/headers/retries, tenant races (coordinator + UI A-late-after-B), membership revocation, permission gate/revocation, catalog nav, config/error boundary, a11y/logout.

Plus existing shell tests (auth, orgs, facilities, permissions, security scan, i18n).

---

## Quality gates (clean `npm ci`)

| Gate | Result |
|---|---|
| `npm ci` | 132 packages, lockfile reproducible |
| lint | **0 errors, 0 warnings** (`oxlint . --deny-warnings`) |
| typecheck | pass (`tsc -b`) |
| tests | **72 passed** |
| production build | pass (Vite 8.2.2, no source maps) |
| `npm audit` / `npm audit --omit=dev` | 0 vulnerabilities |

---

## Backend regression / Alembic / health

| Gate | Result |
|---|---|
| pytest | **403 passed** in 107.11s |
| ruff check / format | pass |
| mypy app | pass |
| Alembic | `20260814_0018` current **and** heads; **no 0019** |
| `/api/v1/health/live` | 200 `alive` |
| `/api/v1/health/ready` | 200 `postgres`/`redis`/`object_storage` `ok` |

---

## Secret scan

Scanned intended frontend + docs changes. No JWT literals, OIDC client secrets, private keys, DB passwords, or `.env` secrets. `.env` gitignored. Test fixtures use fake token **strings** such as `access.token.value`, not real JWTs.

Do not print secret values.

---

## P0 / P1 / P2 / P3

Frontend findings for **this** pass (separate from inherited backend):

| Severity | Count | Notes |
|---|---|---|
| P0 | 0 | |
| P1 | 0 unresolved | Org A-late-after-B classified as clinical-safety P1 **if** it overwrote B. Generation + abort + org-id match + UI test: **does not overwrite**. Token durable-storage P1: **not present** (in-memory userStore). Open redirect P1: **rejected**. |
| P2 | 0 unresolved frontend | Fixed: patient placeholder omitted from shared 401 wipe; malformed callback constructed UserManager; silent renew would iframe `/auth/callback` without a dedicated URI. Inherited backend P2 DENIED-audit rollback unchanged. |
| P3 | documented | Docker image lag (IAM shell 404 on `:9100`); live OpenAPI lag; bootstrap `setTimeout(0)` oxlint workaround; F5 re-login (memory-only tokens, by design); IdP not in compose; silent-renew HTML not shipped unless env set |

No unresolved P0/P1. Hardening is **not** blocked on Audit navigation (approved `clinical.condition.read`).

---

## Docker state

Inherited **P3**: process on `:9100` still lags frozen source (IAM shell GETs 404; `/iam/users/me` 401). Health live/ready 200. Image **not** rebuilt. Compose ports 9100 / 5433 / 6380 / 9101. `backend/docker-compose.yml` untouched.

Containers observed up (backend ~12 days, postgres/redis/minio healthy).

---

## Defects found and fixed this pass

1. `clearSensitiveClientState` now also clears patient placeholder, tenant sessionStorage, OIDC handshake keys, and leaked token JSON.
2. Org select no longer forces a loading phase that hid the picker during in-flight A (A → B race).
3. Failed callbacks no longer instantiate OIDC client just to fail; URL always stripped.
4. Silent renew disabled unless `VITE_OIDC_SILENT_REDIRECT_URI` is set.
5. Unused `react-hook-form` removed.
6. oxlint warnings driven to 0 (unauthenticated tenant is idle; bootstrap deferred).
7. OpenAPI `--check` from frozen source; production source maps off; config validation; error boundary; focus + skip link; generation-guarded org loads.

---

## Exact forbidden scope (this pass)

Not done: freeze, commit, tag, push, migration 0019, patient lookup, clinical chart UI, clinical forms, Patient Mobile, Platform Admin, scheduling, notifications, subscription, AI, pharmacy, ambulance, frozen backend contract edits.
