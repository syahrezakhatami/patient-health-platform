# Healthcare Web application shell

**Date:** 2026-08-27  
**Kind:** Frontend shell  
**Status:** FROZEN — PUBLISHED  
**Path:** `apps/healthcare-web`  
**Published backend baseline:** `ca675b5a41782732995a4021fb85af7b9b29d5b5` (`iam-shell-context-frozen`)  
**Parent freeze:** `70baee1bd24969d29d2b5f7eeda0240fb8bde877` (`product-access-multi-org-context-isolation-frozen`)  
**This freeze:** annotated `healthcare-web-shell-frozen` (this publication commit)  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** not created  

This document describes the first Healthcare Web SPA shell. It is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement patient lookup, clinical chart, Clinical Read Core UI, clinical forms, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, or AI.

Authoritative design: `docs/architecture/healthcare-web-shell-iam-context-design.md`.  
Implementation gate: `docs/gates/healthcare-web-shell-implementation-gate.md`.  
Hardening gate: `docs/gates/healthcare-web-shell-hardening-gate.md`.  
Final freeze: `docs/gates/healthcare-web-shell-final-freeze.md`.

---

## Frozen backend baseline

Consumed, not modified:

| Surface | Status |
|---|---|
| IAM Shell Context Backend | Frozen; three GETs only |
| Multi-org authorization isolation | Frozen |
| Clinical Read Core | Frozen; **not called** by this SPA |
| Product Access & Tenancy | Frozen |
| Wave1PolicyPDP | Untouched SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| ProductAccessPDP | Untouched SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical domains | Untouched |

Staff routes used by the shell:

- `GET /api/v1/iam/me/organizations`
- `GET /api/v1/iam/me/context` (requires `X-Organization-Id`)
- `GET /api/v1/organizations/{organization_id}/facilities/accessible` (header must equal path)

`GET /api/v1/iam/users/me` is not used for org/facility bootstrap.

---

## App structure

```
apps/healthcare-web/
  src/
    api/            typed fetch client, IAM wrappers, generated DTOs
    auth/           in-memory token, OIDC PKCE, session expiry
    tenant/         org bootstrap, facility policy, permission nav
    components/     shell UI (AppShell, gates, switchers)
    pages/          login, org picker, empty workspaces
    i18n/           id / en catalogs
    routing/        path helpers and URL privacy
    styles/         shell CSS
    test/           fixtures and render harness
  openapi/iam-shell.json
  scripts/export_iam_openapi.py
  scripts/generate_iam_types.py
  .env.example      public configuration only
```

No `packages/design-system`, `packages/auth`, or `packages/shared-state`. No Next.js.

---

## Dependencies (installed versions)

| Package | Role |
|---|---|
| Vite 8.2.2 | bundler / dev server (port 3000, `/api` proxy → `:9100`) |
| React 19.2.8 | UI |
| TypeScript ~6.0.2 | types |
| React Router 7.18.2 | routing |
| TanStack Query 5.102.5 | server state (memory only) |
| i18next 26.4.0 / react-i18next 17.0.12 | ID/EN |
| oidc-client-ts 3.5.0 | Authorization Code + PKCE |
| Vitest 4.1.11 + Testing Library | tests |
| oxlint 1.80.0 | lint (`--deny-warnings`) |

Node.js `>=20.20.0` (`.nvmrc` 20.20.2).

---

## Auth / OIDC

Healthcare Web is a **staff** client. Audience must be `php-api`. `php-platform` and `php-patient` tokens are rejected in the SPA before they are stored.

Flow:

1. `/login` starts `UserManager.signinRedirect` (Authorization Code + PKCE; `state`; `nonce` via OIDC library).
2. `/auth/callback` completes the code exchange.
3. Access token is copied into process memory.
4. Bootstrap calls `/iam/me/organizations`.
5. On 401 or access-token expiry: clear session → `/session-expired`.

There is **no** SPA username/password form and **no** PHP login API. The backend remains a JWT resource server.

`POST /api/v1/auth/refresh` is not used and was not created.

Silent renewal: `automaticSilentRenew` is enabled **only** when `VITE_OIDC_SILENT_REDIRECT_URI` is set (dedicated same-origin silent page). It is not enabled against `/auth/callback`. If the IdP issues a refresh token, it stays in the in-memory user store. If silent renew is off or fails, the user re-authenticates. This SPA does not invent backend refresh semantics.

Issuer, client id, and redirect URIs come from public `VITE_*` env. **No client secret.**

---

## Token storage

| Material | Storage |
|---|---|
| Access token / OIDC `User` (including any refresh token the IdP returned) | **In-memory only** (`InMemoryWebStorage` `userStore`) |
| OIDC interaction state (`state`, PKCE `code_verifier`) | **sessionStorage** (`stateStore`) — transient same-tab redirect handshake, not a bearer token |
| Selected organization UUID | sessionStorage `php.healthcare-web.organization-id` |
| Selected work-facility UUID | sessionStorage `php.healthcare-web.work-facility-id` |
| Locale (`id` \| `en`) | localStorage `php.healthcare-web.locale` (not PHI, not authority) |

Access tokens are never written to `localStorage`, IndexedDB, or logs. Error UI uses mapped messages only.

---

## Logout and session expiry

Logout clears: in-memory token, OIDC user, TanStack Query cache, sessionStorage org/facility, patient placeholder, chart-filter placeholder. Then `/login`. If `VITE_OIDC_END_SESSION_URL` or discovery `end_session_endpoint` exists, `signoutRedirect` is used. PHP JWT revocation **does not exist** and is not claimed.

On authenticated API **401**: the same sensitive state is cleared and the user is sent to `/session-expired`. Protected routes then refuse authenticated rendering. Browser back after logout cannot restore a usable in-memory token.

---

## API client

`src/api/client.ts` is a thin `fetch` wrapper.

Injected when present:

- `Authorization: Bearer <memory token>`
- `X-Organization-Id`
- `X-Facility-Id` only when a work facility is selected
- `X-Purpose` only when a caller supplies it (IAM shell GETs omit it)
- `X-Correlation-ID`

Headers are request context. Backend authorization remains authoritative.

`VITE_API_BASE_URL` defaults to empty (same-origin). Dev: Vite proxies `/api` → `http://127.0.0.1:9100` so custom org/facility headers do not require a CORS allow-list change. Do not point the SPA at a split origin unless CORS is extended in a separate review.

Error mapping: 401 session expired; 403 permission denied; 404 not found/concealed; 409 conflict; 422 validation/context; 5xx generic. No stacks, JWTs, or `Authorization` headers in UI.

Retries: none for 401/403/404/409/422; limited for 5xx/network.

---

## OpenAPI types

Frozen IAM DTOs are exported from Pydantic (`scripts/export_iam_openapi.py`) into `openapi/iam-shell.json`, then TypeScript (`scripts/generate_iam_types.py` → `src/api/generated/iam-shell.ts`).

```bash
# from repo, backend venv on PYTHONPATH
backend/.venv/bin/python apps/healthcare-web/scripts/export_iam_openapi.py
python3 apps/healthcare-web/scripts/generate_iam_types.py
```

Live `:9100/api/v1/openapi.json` currently **omits** the frozen IAM shell paths (Docker image lag). Types are generated from source DTOs, not from that lagging image.

---

## Organization bootstrap

After authentication:

| Organizations | Behavior |
|---|---|
| 0 (even if `provisioned: true`) | Unassigned screen. `provisioned` is **not** tenant authority. No Platform Admin entry. |
| 1 ACTIVE | Auto-select, then `GET /iam/me/context`. |
| Many | Picker. Stored sessionStorage org is used only if it is still in the live list, then revalidated via context. |

Stale stored org is ignored. Permissions are never merged across organizations. Organization switch removes previous tenant-scoped TanStack queries, work facility, patient placeholder, and previous `effective_permissions` before loading the new context.

---

## Facility / work context

`GET .../facilities/accessible` with matching `X-Organization-Id`.

| Scope | UI |
|---|---|
| `ALL_IN_ORGANIZATION` | Do not auto-select a facility. Do not invent an “All Facilities” id. Work facility optional. |
| `EXPLICIT` + one facility + `work_facility_required` | Auto-select that facility. |
| `EXPLICIT` + many | User must choose. Never `facilities[0]`. |
| Empty `EXPLICIT` list | Do not reinterpret as all-in-org. |

`work_facility_required` is a **UX hint**, not authorization.

**Work facility ≠ clinical chart facility filter.** This pass never calls Clinical Read Core and never appends `?facility_id=<work facility>`. Changing work facility clears facility-dependent command/form placeholder state only; it does not clear a (future) organization-wide chart.

---

## Effective permissions and navigation

Navigation uses `effective_permissions` from selected-org context only. `role_codes` are labels. There is no `if (role === "CLINICIAN")`.

| Workspace | Shown when |
|---|---|
| Registration | `mpi.identity.read` or `clinical.encounter.create` / `.read` |
| Clinical | any `clinical.*.read` other than encounter-only |
| Identity | `mpi.merge.execute` or `mpi.match.review` |
| Audit | `clinical.condition.read` |
| Administration | `iam.membership.manage` or `org.facility.create` or `org.identifier.manage` |

`PermissionGate` / `ProtectedRoute` are **UX only**. Backend remains the security boundary. After 403, context is refreshed. After 403/404 that indicates membership loss, tenant state is cleared and organizations are re-fetched.

Nurse workspace is not present.

---

## Stale-response strategy

Organization loads use `TenantLoadCoordinator`: abort the previous in-flight request, increment a generation, pass `AbortSignal` into IAM fetches, and commit only if the generation is still current **and** the payload `organization_id` matches the requested org. Query keys include that org id; A → B removes A’s tenant queries. Window-focus refresh uses the same path.

---

## Frontend state

React context: auth, tenant (org, permissions, facility scope, work facility), locale via i18next.  
TanStack Query: server state. Query keys include `organizationId` (`iam-context`, `accessible-facilities`). No Redux/Zustand. No `persistQueryClient`. No Service Worker. `refetchOnWindowFocus` is enabled (useful for IAM context; documented default). `gcTime` 5 minutes; cache is cleared on logout and previous-org keys are removed on switch.

Patient placeholder exists only to be cleared on org switch/logout. It is never populated in this pass.

---

## Multi-tab

Org/facility UUIDs are per-tab `sessionStorage`. No `BroadcastChannel`. No `localStorage` tenant sync. Tab A may be Hospital A while Tab B is Hospital B. Auth tokens may exist independently in each tab’s memory after OIDC.

---

## i18n

Default: stored `php.healthcare-web.locale`, else browser `en*` → `en`, else `id`. Fallback `id`. Simplified Chinese is not shipped; catalogs can add `zh` later. Permission codes are not translated. Locale changes do not alter authorization.

Minimal `Intl` date/number helpers live in `src/i18n/format.ts`.

---

## Accessibility

Landmarks: skip link, `header`, `nav`, `main`. Organization, facility, and locale controls are labeled `<select>` elements (keyboard accessible). Logout is a clearly labeled button. Focus outlines are visible. This is an implementation baseline, not an audit.

---

## CSP / security headers (hosting)

API already sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cache-Control: no-store`.

Expected **SPA hosting** (production; not implemented by this repo):

```
Content-Security-Policy:
  default-src 'self';
  script-src 'self';
  style-src 'self';
  connect-src 'self' <API origin if split> <OIDC issuer>;
  frame-ancestors 'none';
  base-uri 'self';
  form-action 'self' <OIDC issuer>;
  object-src 'none';
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: geolocation=(), microphone=(), camera=()
```

Do not require `unsafe-eval`. Avoid `unsafe-inline` in production. Vite **development** uses module HMR and is not a production CSP. `index.html` sets `<meta name="referrer" content="no-referrer">`. Silent iframe renew is off unless `VITE_OIDC_SILENT_REDIRECT_URI` is set; then hosting may add narrow `frame-src 'self'` plus the IdP origin.

---

## XSS / URL privacy

No `dangerouslySetInnerHTML`. No generic raw-HTML component. React escaping is default. Routes do not include NIK, BPJS, MRN, or patient names. Future patient chart paths must use canonical UUID only (`patientChartPath`).

No analytics/session-replay SDKs. No PWA.

---

## Scripts

```bash
cd apps/healthcare-web
nvm use
npm ci
npm run dev          # http://localhost:3000
npm run build
npm run typecheck
npm run lint
npm run test
```

OpenAPI drift (backend venv):

```bash
backend/.venv/bin/python apps/healthcare-web/scripts/export_iam_openapi.py --check
backend/.venv/bin/python apps/healthcare-web/scripts/generate_iam_types.py --check
```

---

## Known findings / deviations

See `docs/gates/healthcare-web-shell-hardening-gate.md`.
