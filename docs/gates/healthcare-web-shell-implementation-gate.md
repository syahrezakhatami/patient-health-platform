# Healthcare Web shell — implementation gate

**Date:** 2026-08-27  
**Verdict:** IMPLEMENTED  
**Healthcare Web shell hardening:** COMPLETE  
**Healthcare Web shell:** FROZEN (see `docs/gates/healthcare-web-shell-final-freeze.md`)  
**Commit / tag / push:** not performed (this pass)  

Hardening record: `docs/gates/healthcare-web-shell-hardening-gate.md`.

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

---

## Frozen backend baseline

| Item | Value |
|---|---|
| HEAD / published SHA | `ca675b5a41782732995a4021fb85af7b9b29d5b5` |
| Tag | annotated `iam-shell-context-frozen` → same SHA |
| Parent | `70baee1bd24969d29d2b5f7eeda0240fb8bde877` (`product-access-multi-org-context-isolation-frozen`) |
| Branch | `main` == `origin/main` at that SHA |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration 0019 | **Not created** |
| Wave1PolicyPDP SHA-256 | `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| ProductAccessPDP SHA-256 | `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Backend pytest | **403 passed** |
| Backend ruff | pass (`ruff check` + `ruff format --check`) |
| Backend mypy | pass (`mypy app`) |

IAM Shell Context Backend, multi-org isolation, Clinical Read Core, Product Access, Wave1PolicyPDP, ProductAccessPDP, and clinical domains were not modified.

---

## Frontend path and stack

| Item | Value |
|---|---|
| Path | `apps/healthcare-web` |
| Framework | Vite 8.2.2, React 19.2.8, TypeScript ~6.0.2 |
| Router | React Router 7.18.2 |
| Server state | TanStack Query 5.102.5 (memory only) |
| Forms | not a dependency (react-hook-form removed; add when clinical forms exist) |
| i18n | i18next 26.4.0, react-i18next 17.0.12 |
| OIDC | oidc-client-ts 3.5.0, Authorization Code + PKCE |
| Lint | oxlint 1.80.0 (`--deny-warnings`) |
| Test | Vitest 4.1.11, Testing Library, jsdom |
| Node | `>=20.20.0` (`.nvmrc` 20.20.2) |

No Next.js. No `packages/*`.

---

## App structure

See `docs/architecture/healthcare-web-shell.md`. Shell components: `AppShell`, `TopBar`, `Navigation`, `OrganizationSwitcher`, `FacilitySwitcher`, `LocaleSwitcher`, `ProtectedRoute`, `PermissionGate`, `SessionExpired`, `Forbidden`, `NotFound`, `LoadingBoundary`. Empty workspaces only.

---

## Auth / OIDC / tokens

- Staff `php-api` only. Patient/platform audiences rejected.
- Access token: **in memory only**.
- OIDC `userStore`: `InMemoryWebStorage`.
- OIDC `stateStore` (PKCE `state` / `code_verifier`): **sessionStorage**, documented as transient protocol material.
- No `localStorage` bearer tokens.
- No `POST /api/v1/auth/refresh`. Silent renew in memory if the IdP supports it; otherwise re-login.
- Logout: clear memory, Query cache, sessionStorage org/facility, patient placeholder; IdP end-session if configured; **no** PHP revocation.
- 401: same clearing → `/session-expired`.
- Open redirect: internal path allow-list (`/app`, `/select-organization`, `/unassigned`).
- PKCE enabled (`disablePKCE` left false). Implicit flow not implemented.

---

## API client

Central `fetch` client with Bearer, `X-Organization-Id`, optional `X-Facility-Id` / `X-Purpose`, `X-Correlation-ID`. Public env only (`VITE_*`). Default API base is same-origin; Vite proxies `/api` → `:9100`.

Types: generated from frozen Pydantic IAM shell schemas (`npm run generate:api-types` / Python scripts). Not duplicated by hand except the generator itself.

---

## Organization / facility / permissions

| Case | Result |
|---|---|
| Zero orgs, `provisioned: true` | Unassigned screen; not Platform Admin |
| One ACTIVE org | Auto-select |
| Multiple | Picker; stored org revalidated |
| Stale stored org | Ignored |
| Org switch | Clears previous context, permissions, work facility, tenant queries, patient placeholder |
| `ALL_IN_ORGANIZATION` | No forced facility; no fake “All Facilities” id |
| `EXPLICIT` one + required | Auto-select |
| `EXPLICIT` many | User selects; never first row |
| `work_facility_required` | UX hint only |
| Work vs chart filter | Separate placeholders; chart filter never auto-copied from work facility |

Navigation is permission-derived for the **selected org only**. Frontend guards are UX, not security.

---

## TanStack Query PHI policy

Memory only. No `persistQueryClient`, IndexedDB, localStorage cache, or Service Worker. Keys include `organizationId`. Logout: `queryClient.clear()`. Org switch: remove previous tenant keys. `refetchOnWindowFocus: true` (IAM context freshness). No retry on 401/403/404/422.

---

## Multi-tab / i18n / a11y

Per-tab `sessionStorage` for org/facility. No `BroadcastChannel`. Locale in localStorage, independent of auth. ID + EN; fallback `id`; ZH later. Keyboard-accessible labeled selects; landmarks; visible context chips for org and work facility (clinical safety / shared workstation).

---

## Security headers / CSP / XSS / URL privacy

Documented in `docs/architecture/healthcare-web-shell.md`. No `dangerouslySetInnerHTML`. No NIK/BPJS/MRN/names in routes. No analytics SDKs. No Service Worker.

---

## Frontend quality gates (this pass)

| Gate | Result |
|---|---|
| Tests | **72 passed** (18 files) after hardening — see hardening gate |
| Lint | oxlint exit 0, **0 warnings** (`--deny-warnings`) |
| Typecheck | pass (`tsc -b`) |
| Production build | pass (Vite 8; no source maps) |

---

## Backend regression

| Gate | Result |
|---|---|
| pytest | **403 passed** |
| ruff check / format | pass |
| mypy app | pass |
| Alembic | `20260814_0018` current and heads; no 0019 |
| `/api/v1/health/live` | 200 `alive` |
| `/api/v1/health/ready` | 200 postgres/redis/object_storage `ok` |

---

## Secret scan

No OIDC client secrets, JWTs, private keys, database credentials, or `.env` files committed under `apps/healthcare-web`. Public template: `.env.example` (`VITE_*` only). `.env` gitignored.

---

## Docker state

Inherited **P3 Docker image lag**: process on `:9100` returns **404** for `GET /api/v1/iam/me/organizations` and `GET /api/v1/iam/me/context`, and **401** for `GET /api/v1/iam/users/me`. Health live/ready still 200. Image was **not** rebuilt in this pass. Working-tree pytest exercises the ASGI app (403 passed). Dev SPA proxy will see the same lag until the API container/process is rebuilt from frozen source.

Ports remain 9100 / 5433 / 6380 / 9101. `backend/docker-compose.yml` untouched.

---

## P0 / P1 / P2 / P3

| Severity | Count | Notes |
|---|---|---|
| P0 | 0 | |
| P1 | 0 | |
| P2 | inherited | DENIED-audit rollback from prior freezes; not redesigned |
| P3 | documented | Docker image lag (IAM shell 404 on `:9100`); live OpenAPI on `:9100` lacks shell paths |

---

## Contract deviations

1. OpenAPI types generated from **source Pydantic DTOs**, not from live `:9100/openapi.json` (that spec still lags Docker).
2. Audit workspace nav requires `clinical.condition.read` (not every `clinical.*.read`) so registrar encounter-read does not open Audit. Matches the catalog’s primary Audit permission.
3. React Hook Form was unused and **removed** in the hardening pass.
4. CORS was **not** expanded; Vite same-origin proxy is used instead (approved design).
5. No `packages/*` shared libraries (approved).

No frozen backend contracts, PDPs, or IAM shell routes were patched.

---

## Exact forbidden scope (this pass)

Not implemented: patient lookup, patient list, clinical chart/summary/timeline/sections, clinical forms, fake patient data, Clinical Read Core calls, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, AI, migration 0019, final freeze, commit, tag, push.

`PermissionGate` is UI-only.

---

## Known findings

- Shared-workstation UX is present (visible user, org, facility, logout) but not a formal a11y/security audit.
- IdP is not in `docker-compose.yml`; local OIDC requires a separately configured issuer.
- Silent iframe renew HTML is optional (`VITE_OIDC_SILENT_REDIRECT_URI`); default does **not** iframe `/auth/callback`.
