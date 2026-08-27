# Healthcare Web shell — final freeze

**Date:** 2026-08-27  
**Verdict:** PASS WITH P2  
**P0:** none  
**P1 unresolved:** none  
**HEALTHCARE WEB SHELL:** FROZEN  
**HEALTHCARE WEB SHELL:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement patient lookup, patient selection, clinical chart UI, clinical forms, Clinical Read Core UI, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, or AI. Migration `0019` was not created. Frozen backend contracts, IAM Shell Context Backend, Clinical Read Core, ProductAccessPDP, and Wave1PolicyPDP were not modified.

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` (at freeze) |
| Published backend parent SHA | `ca675b5a41782732995a4021fb85af7b9b29d5b5` |
| Parent tag | annotated `iam-shell-context-frozen` → same SHA |
| Parent of that baseline | `70baee1bd24969d29d2b5f7eeda0240fb8bde877` (`product-access-multi-org-context-isolation-frozen`) |
| Final freeze SHA | annotated tag `healthcare-web-shell-frozen` peel (this publication commit) |
| Final annotated tag | `healthcare-web-shell-frozen` → this publication commit |
| App path | `apps/healthcare-web` |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration `0019` | **Not created** |
| `backend/docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `product_access_pdp.py` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical Read Core / IAM Shell Context Backend | Untouched |

Old tags were not moved or rewritten:

- `iam-shell-context-frozen`
- `product-access-multi-org-context-isolation-frozen`
- `clinical-read-core-frozen`
- `product-access-tenancy-foundation-frozen`
- `wave-2b-clinical-foundation-complete`

Expected lineage:

```
iam-shell-context-frozen
ca675b5a41782732995a4021fb85af7b9b29d5b5
        |
        v
healthcare-web-shell-frozen
(this publication commit)
```

---

## B. Frontend path, framework, versions

After `npm ci` (Node v20.20.2, npm 10.8.2, lockfileVersion 3):

| Package | Version |
|---|---|
| Vite | 8.2.2 |
| React / react-dom | 19.2.8 |
| TypeScript | 6.0.3 (declared `~6.0.2`) |
| React Router | 7.18.2 |
| TanStack Query | 5.102.5 |
| i18next / react-i18next | 26.4.0 / 17.0.12 |
| oidc-client-ts | 3.5.0 |
| oxlint | 1.80.0 (declared `^1.79.0`) |
| Vitest | 4.1.11 |

`react-hook-form` is **not** installed. Runtime dependencies are only those listed in `package.json` and are used. Lockfile present. No dependency drift after clean install.

Shell-only responsibilities: OIDC staff session, organization context, facility work context, permission navigation, API client, ID/EN i18n, secure layout, empty workspace placeholders.

---

## C. Auth / OIDC

Staff client. Audience **`php-api`**. `php-patient` and `php-platform` rejected. No implicit flow. No password/ROPC.

- Authorization Code + PKCE (`response_type: code`, `disablePKCE: false`)
- `state` validated by oidc-client-ts; missing `code`/`state` is malformed
- `nonce` via library when `openid` scope is requested
- Authority and client id from public `VITE_*` config; production fail-fast if missing
- No client secret

**Token storage:** access token, refresh token (if issued), and id token live in `InMemoryWebStorage` `userStore` only. Application `tokenStore` is process memory. **Not** `localStorage`, `sessionStorage`, or IndexedDB.

**Transient OIDC state:** `sessionStorage` `stateStore` may hold handshake `state`, PKCE `code_verifier`, nonce, and a safe internal return path. Callback `finally` strips URL `code`/`state`/`error*` and purges any Web Storage JSON containing token keys. No bearer token is stored in Web Storage.

**Silent renew:** `automaticSilentRenew` is enabled **only** when `VITE_OIDC_SILENT_REDIRECT_URI` is set. The main `/auth/callback` page is **not** used in an iframe. No silent-renew HTML is shipped in this freeze (later operational enhancement).

**F5 / reload:** memory-only tokens mean a full reload may require re-authentication. **P3 UX-security tradeoff.** Tokens were not moved to persistent storage.

Callback: only a valid code exchange authenticates. Missing/invalid/replayed state, malformed callback, and OIDC error callbacks leave the session unauthenticated. No raw OIDC payload in UI.

Open redirect: `safeReturnTo` allows `/app`, `/select-organization`, `/unassigned` only. Rejects `https://evil.example`, `//evil.example`, `javascript:`, `data:`, encoded external URLs, protocol-relative paths.

---

## D. 401 / logout / browser back

401 and logout wipe: in-memory OIDC token/user, selected org, effective permissions, role codes, facility scope, work facility, patient placeholder, tenant `sessionStorage` hints, OIDC handshake `oidc.*` keys, TanStack Query cache, protected UI. Then `/session-expired` or `/login`.

Concurrent 401s are idempotent (`expiryInFlight`). One expiry flow.

IdP end-session only when configured. **No PHP JWT revocation.**

After logout, `/app` is not usable without a new memory token. Browser back cannot restore authority.

---

## E. Tenant / races / cache / multi-tab

**Authoritative stale-response strategy:**

`TenantLoadCoordinator` generation + `AbortSignal` + response `organization_id` validation + organization-scoped TanStack Query keys.

A → B with A completing last: **final state remains B.** Rapid A → B → A: **final state is last A.**

Query keys: `["iam-context", organizationId]`, `["accessible-facilities", organizationId]`. Org list is user-level `["iam-organizations"]`. Previous org queries cancelled/removed on switch. Logout/401: `queryClient.clear()`. No `persistQueryClient`.

Org/facility hints: **sessionStorage**, not localStorage. No `BroadcastChannel`. Per-tab tenant context. Auth identity (in-memory OIDC) is not tenant selection.

Bootstrap: 0 orgs → unassigned; 1 ACTIVE → auto-select; many → picker; stored UUID is a hint revalidated against live `/iam/me/organizations` then `/iam/me/context`.

---

## F. Permissions / Audit / facilities / headers

Navigation from selected-org `effective_permissions` only. Not role names. No union across orgs.

| Workspace | UI mapping |
|---|---|
| Registration | `mpi.identity.read` or `clinical.encounter.create` / `.read` |
| Clinical | any `clinical.*.read` except encounter-only |
| Identity | `mpi.merge.execute` or `mpi.match.review` |
| Audit | `clinical.condition.read` |
| Administration | `iam.membership.manage` or `org.facility.create` or `org.identifier.manage` |

**Audit navigation** is a **DESIGN-APPROVED UI CAPABILITY MAPPING**, not an audit authorization permission. Frozen catalog has no `audit.*`. Backend remains authoritative. Clinician/auditor may both see the Audit **placeholder** if they hold `clinical.condition.read`. Future audit-specific capability design may tighten UX. No `audit.*` permission was created. Backend catalog unchanged.

`PermissionGate` / route guards are **UX only**. Direct navigation to a hidden workspace: Forbidden, no crash.

Permission revocation: focus refresh updates nav. Membership 403/404 clears tenant state and re-bootstraps remaining orgs or unassigned. Inaccessible work facility is cleared; no stale `X-Facility-Id`.

Facilities: EXPLICIT one + required → auto-select; EXPLICIT many → user choice, never row 0; ALL_IN_ORGANIZATION → no fake “All Facilities” id.

**Work facility ≠ chart filter.** Work facility is never copied to `?facility_id=` for Clinical Read Core. No Clinical Read Core calls in this freeze.

Headers: `Authorization` from memory; `X-Organization-Id` from validated org; `X-Facility-Id` only when the call supplies a work facility; **`X-Purpose` not globally injected.** Shell IAM is purpose-exempt.

---

## G. XSS / privacy / CSP / headers / source maps

No `dangerouslySetInnerHTML`, `innerHTML`, `document.write`, `eval(`, `new Function`. No token/OIDC/`Authorization` logging. Routes contain no tokens, NIK, BPJS, MRN, names, or clinical text. Callback query cleaned.

No service worker, PWA, Cache API clinical strategy, IndexedDB PHI cache, or persisted Query client.

Production CSP (hosting responsibility, not implemented in this repo):

```
default-src 'self';
script-src 'self';
object-src 'none';
base-uri 'self';
frame-ancestors 'none';
connect-src 'self' <API origin if split> <OIDC issuer>;
frame-src 'self' <OIDC issuer>;   /* only if silent-renew URI is configured later */
form-action 'self' <OIDC issuer>;
```

No `unsafe-eval`. Avoid `unsafe-inline` in production.

Also: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, Permissions-Policy as documented in `docs/architecture/healthcare-web-shell.md`. API already sets several of these. `index.html` has `<meta name="referrer" content="no-referrer">`.

Production build: `sourcemap: false`. No public `.map` files (`index-BCXY7BsH.js`, `index-Dd6kzh7k.css`).

---

## H. Config / env / a11y / zero clinical UI

`validatePublicConfig` fail-fast: audience must be `php-api`; secret-shaped values rejected; production requires issuer + client id. `.env.example` is `VITE_*` public placeholders only.

Skip link, labeled native `<select>` for org/facility/locale, landmarks, logout button, focus to `#main-content` on route change. Active organization and work facility always visible (ellipsis + `title`).

Clinical/Registration/Identity/Audit/Admin workspaces are empty placeholders. No patient lookup, list, selection, chart, summary, timeline, condition/observation/medication/allergy/lab/note UI, or clinical forms. No fake patient data.

---

## I. Quality gates (this publication)

| Gate | Result |
|---|---|
| `npm ci` | 132 packages; 0 audit findings |
| oxlint | **0 errors, 0 warnings** |
| typecheck | pass |
| frontend tests | **72 passed** (18 files) |
| production build | pass; no `.map` |
| `npm audit` / `--omit=dev` | critical 0 / high 0 / moderate 0 / low 0 |
| OpenAPI `--check` from frozen FastAPI source | ok (not Docker `:9100`) |
| pytest | **403 passed** |
| ruff check / format | pass |
| mypy app | pass (134 files) |
| Alembic | `20260814_0018` current and heads; no 0019 |
| health live | 200 `alive` |
| health ready | 200 postgres/redis/object_storage `ok` |
| secret scan | no JWT, client secret, private key, DB password, or `.env` secret in intended commit |

---

## J. P0 / P1 / P2 / P3

| Severity | Count | Notes |
|---|---|---|
| P0 | 0 | |
| P1 | 0 unresolved | Org A-late-after-B does not overwrite B. Tokens not in durable Web Storage. Open redirect rejected. |
| P2 | inherited | DENIED-audit rollback from prior backend freezes; not redesigned. No unresolved frontend P2. |
| P3 | documented | Docker/OpenAPI image lag on `:9100`; F5 re-login (intentional memory-only tokens); optional silent-renew page not shipped |

---

## K. Docker state

**P3 DOCKER IMAGE LAG:** process on `:9100` may still omit frozen IAM shell GETs. Health live/ready 200. Image **not** rebuilt. Does **not** block this frontend source freeze. `backend/docker-compose.yml` untouched.

---

## L. Exact files included

- `apps/healthcare-web/**` (SPA shell, tests, lockfile, generated IAM types, OpenAPI export scripts)
- `docs/architecture/healthcare-web-shell.md`
- `docs/gates/healthcare-web-shell-implementation-gate.md`
- `docs/gates/healthcare-web-shell-hardening-gate.md`
- `docs/gates/healthcare-web-shell-final-freeze.md` (this file)

Previously published Healthcare Web IAM context design docs remain on the parent commit. No backend production files. No migration 0019.

---

## M. Push verification

Recorded after `git push` of `main` and `healthcare-web-shell-frozen` (no force):

- `HEAD == origin/main`
- working tree clean
- `healthcare-web-shell-frozen` points to HEAD
- old tags unchanged
- Alembic still `20260814_0018`; no 0019
