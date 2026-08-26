# Healthcare Web shell and IAM context — design contract

**Date:** 2026-08-26  
**Kind:** Design only  
**Status:** APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN  
**Baseline:** `clinical-read-core-frozen` / `5d124de2c80bc17127fc17e9f6a730828c13a63a`  
**Parent:** `product-access-tenancy-foundation-frozen` / `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716`  
**Alembic:** `current == heads == 20260814_0018`  
**Wave1PolicyPDP:** FROZEN — must not be edited  
**ProductAccessPDP:** remains `default_pdp()`  
**Clinical Read Core:** FROZEN — must not be edited  

This contract does not implement Healthcare Web, IAM context APIs, migration `0019`, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, or AI. It is not a HIPAA, ISO 27001, or SOC 2 certification.

Companion gate: `docs/gates/healthcare-web-shell-iam-context-design-approval.md`.  
Companion canvas (review-only, outside git): [healthcare-web-shell-iam-context.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/healthcare-web-shell-iam-context.canvas.tsx)

Authoritative inputs: Healthcare Web / Clinical Chart discovery, Clinical Read Core freeze, Product Access freeze, and live IAM / auth / organization / facility code.

---

## Decisions (normative)

| # | Topic | Decision |
|---|---|---|
| 1 | Product | **One** Healthcare Web application. Workspaces are permission-derived navigation, not separate apps |
| 2 | Audience | Staff `php-api` only. Never `php-platform` or `php-patient`. Never PatientPrincipal |
| 3 | Frontend | Vite + React + TypeScript SPA; React Router; TanStack Query; React Hook Form; i18next; OpenAPI-generated types |
| 4 | Repo | Same git repo; first app at `apps/healthcare-web`. No `packages/*` yet. Do not reorganize now |
| 5 | Auth | Existing backend **validates** JWTs; it does **not** issue, refresh, or revoke them. Healthcare Web uses OIDC Authorization Code + PKCE against `AUTH_ISSUER` |
| 6 | Token storage | **In-memory only.** No `localStorage` access tokens. No persistent refresh tokens in JS storage |
| 7 | Refresh | **No** `POST /auth/refresh`. Silent renew via OIDC in memory if the IdP issues a refresh token; otherwise re-login on expiry |
| 8 | Session expiry | API 401 → clear credentials + PHI query cache + tenant/patient state → `/session-expired` → re-authenticate |
| 9 | Logout | Clear memory, TanStack cache, sessionStorage context, navigate to login. IdP end-session if configured. **No** PHP token revocation (does not exist) |
| 10 | Keep `/iam/users/me` | Unchanged. Insufficient for shell. Do not turn it into a mega-response |
| 11 | Bootstrap APIs | Three new GETs (below). Self-context only. No PHI |
| 12 | Org selection | Frontend sends `X-Organization-Id`. Selection is **not** authorization. Backend membership remains authoritative |
| 13 | Org persistence | **Per-tab `sessionStorage`** of selected org UUID only. Not security authority. Not `localStorage` |
| 14 | Facility list | New accessible-facility GET. Empty explicit binding = **all facilities in the selected organization**, never global |
| 15 | Work vs chart facility | **CURRENT WORK CONTEXT FACILITY** ≠ **CHART FILTER FACILITY**. Chart default remains organization-wide |
| 16 | Default facility | Auto-select only when exactly **one** accessible facility. Never first-row default for org-wide staff |
| 17 | Permissions | Context returns **effective permission codes for the selected organization only**. Nav derives from permissions, not `role === CLINICIAN` |
| 18 | Multi-org | Hospital A CLINICIAN and Hospital B ORG_ADMIN must not merge in the shell. Effective set is selected-org memberships |
| 19 | Frontend guards | UX only. Direct API calls still fail server-side |
| 20 | PHI cache | In-memory TanStack Query only. **No** `persistQueryClient`. No Service Worker / PWA / offline EMR |
| 21 | Multi-tab | Organization/facility/patient context is **per-tab**. Do not sync org via `localStorage` |
| 22 | i18n | ID + EN MVP; ZH later. Locale in frontend only (no user-profile column, no 0019) |
| 23 | Patient entry | Frozen MPI identifier lookup only. No directory. No name search |
| 24 | Today’s patients | **Not** this shell. Encounter ≠ appointment. Separate later design |
| 25 | Migration 0019 | **Not required.** Memberships, roles, permissions, organizations, facilities already exist |
| 26 | CORS / origin | Prefer same-origin reverse proxy (and Vite proxy in dev). If split origin: allow tenant/purpose headers. Not a new auth product |
| 27 | Sequence | IAM context APIs → harden/freeze those APIs → Healthcare Web shell → lookup → chart UI |
| 28 | First frontend pass | Scaffold, auth/session, org/facility context, permission nav, i18n, empty layout, API client. **Not** chart UI |

---

## 1. Healthcare Web boundary

Healthcare Web is the staff clinical application for hospitals and clinics. One app. Clinicians, registrars, organization admins, auditors, and later nurses / pharmacy / lab / emergency workspaces share it.

Do **not** create Doctor Web, Nurse Web, Clinic Web, or Hospital Web.

Platform Admin Web remains a separate client (`php-platform`). Patient Mobile remains a separate client (`php-patient`). Healthcare Web must not embed either.

Backend authorization remains ProductAccessPDP + frozen Wave1. Workspaces are UX projections of **permission codes**.

---

## 2. Frontend technology

**Final recommendation:** Vite + React + TypeScript SPA.

| Library | Role |
|---|---|
| React Router | Frontend routes (UX only) |
| TanStack Query | Server state; PHI in memory |
| React Hook Form | Later clinical forms; shell conventions only now |
| i18next | ID/EN catalogs |
| OpenAPI types | Generated from FastAPI `/openapi.json` (`openapi-typescript` + thin fetch wrapper) |

**Reject Next.js / SSR for MVP.** Rendering PHI on a server/CDN adds cache and log risk without a clinical-product advantage. The API is already FastAPI.

Do not create frontend files in this pass.

---

## 3. Repository layout

Keep the existing git repository.

Intended later (do not create now):

```
backend/
apps/healthcare-web/
apps/platform-admin-web/   # later, separate client
```

No `packages/design-system`, `packages/auth`, or `packages/api` in the first implementation. Patient Mobile will not share React DOM components. Shared packages are unjustified at current team size.

Independent deploy: static SPA + existing API process.

---

## 4. Existing authentication (repository fact)

The backend **does not issue JWTs**. It validates Bearer access tokens.

| Item | Live behavior |
|---|---|
| Issuer | `AUTH_ISSUER` (default Keycloak-shaped `http://localhost:8080/realms/php-dev`). No IdP service in `docker-compose.yml` |
| Production verify | JWKS at `AUTH_JWKS_URL`, `RS256` / `ES256` |
| Local/test verify | HS256 `AUTH_DEV_HS256_SECRET` only when `APP_ENV ∈ {local, test, development}` |
| Required claims | `exp`, `iss`, `aud`, `sub` |
| Audience | Exactly one of `php-api`, `php-platform`, `php-patient`. Mixed array → 401 |
| Permissions / org / facility | **Not in the token.** Loaded from IAM DB via `sub` |
| Login HTTP | **None** |
| Logout HTTP | **None** |
| Refresh HTTP | **None** |
| Revocation | **None** |
| Cookies / CSRF / server session | **None** |
| Introspection | `GET /api/v1/auth/context` (not a shell bootstrap) |

Staff clinical and Clinical Read Core routes use `require_staff_audience` (`aud == php-api`). IAM/org routes currently allow `php-api` **or** `php-platform`. Healthcare Web must still send **`php-api` only**.

---

## 5. Browser auth / session (MVP)

**Chosen model:** OIDC Authorization Code + PKCE against the configured issuer. Access token (and any IdP refresh token) live **in process memory** of the SPA.

| Option | Verdict |
|---|---|
| A. In-memory access token + re-login on expiry | **Required fallback** when silent renew is unavailable |
| B. New HttpOnly session cookie / PHP session layer | **Rejected for MVP.** Would be a new auth product. Backend has no session store |
| C. OIDC Code + PKCE with memory handling | **Primary** |
| localStorage bearer | **Forbidden** on shared clinical workstations |

Transitional local development may use the existing HS256 validator only inside non-production `APP_ENV`. Production Healthcare Web must not ship a “paste JWT” screen.

**Do not add `POST /api/v1/auth/refresh`.** Nothing in the repository supports it.

Silent renew: if the IdP returns a refresh token, the OIDC client may keep it **in memory** and renew the access token. If renew fails or the IdP has no refresh: treat as expiry (decision 8).

CSRF: Bearer-in-header has low CSRF risk; XSS and shared-workstation token theft are the primary threats. If a later pass introduces cookies, CSRF protections become mandatory. Do not call CSRF “irrelevant” without that qualifier.

---

## 6. Logout and expiry

On **401** from the API (expired/invalid token):

1. Drop in-memory tokens.
2. `queryClient.clear()`.
3. Clear `sessionStorage` tenant/work/patient keys.
4. Navigate to `/session-expired` (then login).
5. Do not leave chart data reachable via back-forward cache: `Cache-Control: no-store` already on API; SPA must not restore PHI from `history.state`.

On **explicit logout**:

1. Same local cleanup.
2. Redirect to OIDC end-session endpoint **if** `VITE_OIDC_END_SESSION_URL` (or discovery `end_session_endpoint`) is configured.
3. Do **not** claim PHP-side revocation.

Visible chrome: active user `display_name`, selected organization name, work-facility label, obvious logout control.

---

## 7. Current `/iam/users/me` (insufficient)

`GET /api/v1/iam/users/me` returns:

`provisioned`, `id`, `subject`, `display_name`, `roles`, `permissions`.

Without `X-Organization-Id`, roles/permissions remain the loaded union across memberships. With `X-Organization-Id`, they follow the selected-organization projection used by enforcement. The DTO still does **not** return memberships, organizations, facilities, or an explicit facility-scope discriminant. Keep the route. Healthcare Web must not use it as the org/facility bootstrap; use the context APIs below.

---

## 8. New APIs (exact)

All three are **staff `php-api` only** (`require_staff_audience`). No clinical PHI. No other-org directories. No patient data.

Provisioned principal required; unprovisioned → same shape as today (`provisioned: false`) or 401/403 consistent with existing unprovisioned handling. Foreign org id → **404 conceal** (not 403).

### 8.1 `GET /api/v1/iam/me/organizations`

After authentication, before org selection. **No** `X-Organization-Id` required.

Authorization: authenticated staff + `iam.user.read` (already not org-scoped) **or** the existing `/users/me` pattern of returning the caller’s own principal. Do not require `iam.membership.manage`.

Response: caller’s **ACTIVE** memberships grouped by organization. Include only orgs the caller belongs to.

### 8.2 `GET /api/v1/iam/me/context`

Requires `X-Organization-Id`. Selected organization must be in the caller’s memberships.

Returns user identity, that organization’s memberships, **effective permission codes for that organization only**, facility-scope discriminator, and display role labels for that org.

### 8.3 `GET /api/v1/organizations/{organization_id}/facilities/accessible`

Requires `X-Organization-Id` **equal to** `{organization_id}`. Authorize `org.facility.read` (all current staff roles have it).

Returns facilities the caller may use **in that organization**:

- Memberships in this org with `facility_id IS NULL` → `facility_scope = ALL_IN_ORGANIZATION` → all **ACTIVE** facilities of this org (never other orgs).
- Only explicit `facility_id` rows in this org → `facility_scope = EXPLICIT` → those facilities only (ACTIVE, this org).
- Never encode “all in org” as an empty `facility_ids` array without the discriminator.

Repository `list_facilities(organization_id)` already exists; this is an HTTP + authorization wrapper, not a schema change.

`GET /iam/users/me` stays. Do not add a fourth mega `/me`.

---

## 9. DTOs (Pydantic, `extra=forbid`)

Illustrative names; implementation may suffix `Response`.

```
StaffSessionUserDTO
  id: UUID
  subject: str
  display_name: str

AccessibleOrganizationDTO
  organization_id: UUID
  name: str
  code: str
  organization_type: str   # HOSPITAL | CLINIC | …
  status: str              # ACTIVE | INACTIVE
  role_codes: list[str]    # roles in THIS org only

StaffOrganizationsResponse
  provisioned: bool
  user: StaffSessionUserDTO | None
  organizations: list[AccessibleOrganizationDTO]

FacilityScopeKind = ALL_IN_ORGANIZATION | EXPLICIT

AccessibleFacilityDTO
  id: UUID
  name: str
  code: str
  facility_type: str
  status: str

StaffContextResponse
  provisioned: bool
  user: StaffSessionUserDTO
  organization: AccessibleOrganizationDTO
  role_codes: list[str]                 # this org only
  effective_permissions: list[str]      # this org only
  facility_scope: FacilityScopeKind
  work_facility_required: bool          # true iff EXPLICIT and at least one facility
  accessible_facilities: list[AccessibleFacilityDTO]  # may be omitted on context if loaded via 8.3; if included, same rule as 8.3

AccessibleFacilitiesResponse
  organization_id: UUID
  facility_scope: FacilityScopeKind
  facilities: list[AccessibleFacilityDTO]
```

Do not return: `role_id`, `revoked_at`, JWT, other users, foreign orgs, patient identifiers, internal PDP reasons, `matching_value`.

**Effective permissions** for selected org O = union of `role_permissions` for ACTIVE memberships where `organization_id = O`. Do not union Hospital B’s ORG_ADMIN into Hospital A’s context.

---

## 10. Authorization context (org-scoped before shell implementation)

`load_principal` still loads every ACTIVE membership. Runtime staff authorization no longer feeds that global union into ProductAccessPDP / Wave1PolicyPDP when an organization is selected.

Selected organization O:

- permissions = union of `role_permissions` for ACTIVE memberships where `organization_id = O`
- facilities = that organization’s membership bindings only (any `facility_id is None` ⇒ org-wide empty list for O, never all facilities across every membership)
- platform memberships (`organization_id is None`) stay platform; they are not rewritten as a hospital membership

Record: `docs/gates/product-access-multi-org-context-isolation-resolution.md`.

**Shell context must report the same effective permissions and facility authority the backend now enforces.** Do not return a UI-only subset of a global union. Do not edit Wave1PolicyPDP or ProductAccessPDP in the shell implementation.

---

## 11. Organization selection and switch

Flow:

```
OIDC login → GET /iam/me/organizations
  → 0 orgs: provisioned-but-unassigned screen
  → 1 ACTIVE org: select automatically
  → many: /select-organization
→ persist selected org UUID in sessionStorage (this tab)
→ GET /iam/me/context + facilities/accessible with X-Organization-Id
→ enter /app
```

Every subsequent API call sends `X-Organization-Id`. Backend membership remains authoritative.

On organization switch **must** clear:

- selected patient / canonical id
- chart / summary / timeline / section queries
- selected encounter
- work facility if it is not valid in the new org
- chart facility filter
- org-scoped MRN/header data
- permission-derived navigation cache (refetch context)

Do not silently switch organization while a dirty clinical form is open (see §22).

Inactive organizations: omit from picker or show disabled; do not auto-select.

---

## 12. Facility: work context vs chart filter

Frozen Clinical Read Core default grain is **organization-wide**. Forcing `?facility_id=workFacility` on every chart read would hide longitudinal history.

| Concept | Header / query | When |
|---|---|---|
| **Work context facility** | `X-Facility-Id` | Optional org-wide; required when `facility_scope=EXPLICIT` for writes that use request facility. Used for attribution on **commands** |
| **Chart filter facility** | Query `facility_id` on Read Core only | User explicitly filters the chart. Default: **unset** |

Changing work facility **must not** automatically set the chart filter or discard the longitudinal chart.

Default work facility:

- EXPLICIT + exactly one facility → select it.
- EXPLICIT + many → user chooses; do not pick row 0.
- ALL_IN_ORGANIZATION → no automatic facility; work facility optional.

Write path: frozen `/api/v1/clinical/*` commands. Do not change write semantics. Chart-filter facility must not become write attribution unless the user also selected it as work context.

---

## 13. Purpose UX

Purpose is required on Clinical Read Core and MPI; it is **not** a grant. Do not show a purpose dropdown on every request.

| Workspace | `X-Purpose` |
|---|---|
| Clinical | `TREATMENT` |
| Registration | `REGISTRATION` |
| Identity / MPI | `IDENTITY_RESOLUTION` |
| Audit | `AUDIT` |
| Organization administration | `ADMINISTRATION` |

`PATIENT_ACCESS` is forbidden on staff chart. `CARE_COORDINATION` and `EMERGENCY` remain valid catalog values for later workspaces; not MVP chrome. `SYSTEM_OPERATION` is not a Healthcare Web UI purpose.

---

## 14. Permission-driven navigation

Frontend may show role labels (`CLINICIAN`, `REGISTRAR`, …) as text.

Capability **must** derive from `effective_permissions` for the selected org.

| Workspace | Show when (any of) |
|---|---|
| Registration | `mpi.identity.read` or `clinical.encounter.create` / `clinical.encounter.read` |
| Clinical | any `clinical.*.read` except encounter-only-without-other-clinical (registrar stays Registration) **or** `mpi.identity.read` plus any non-encounter clinical read |
| Identity | `mpi.merge.execute` or `mpi.match.review` (IDENTITY_OFFICER catalog) without clinical chart |
| Audit | `clinical.condition.read` (or any clinical read) **and** workspace entered as Audit (purpose `AUDIT`); still permission-gated |
| Organization admin | `iam.membership.manage` or `org.facility.create` or `org.identifier.manage` |

Do **not** implement `if (role === "CLINICIAN")`. Registrar with only encounter+MPI must not see Conditions. IDENTITY_OFFICER must not see chart sections. NURSE workspace: **FORBIDDEN** until a separate permission design.

Frontend route guards hide/redirect. They are **not** security.

---

## 15. Frontend routes (conceptual)

| Path | Notes |
|---|---|
| `/login` | Start OIDC |
| `/auth/callback` | PKCE callback |
| `/session-expired` | Post-401 |
| `/select-organization` | Multi-org |
| `/app` | Shell home (empty workspaces ok in first pass) |
| `/app/registration` | Lookup + encounters later |
| `/app/clinical/patients/:patientId` | Canonical UUID only |
| `/app/identity` | MPI tools later |
| `/app/admin` | Org admin later |
| `/app/audit` | Read-only chart later |

**Forbidden in URLs:** NIK, BPJS, patient name, note text, MRN. Canonical patient UUID is acceptable and remains authorization-protected.

---

## 16. Patient context and Clinical Read Core

Patient entry: `POST /api/v1/mpi/identities/lookup` (identifier). Optional `POST /mpi/match` with frozen strict criteria. **No** patient directory. **No** open name search.

After lookup/get: store **canonical** id from the identity or from chart shell `canonical_patient_identity_id`. If request X returns canonical Y, replace in-memory patient context with Y (no extra merge UX).

Read Core (frozen; do not change):

- `GET /api/v1/clinical/patients/{id}/chart` — shell + header + `authorized_sections`
- `GET .../chart/summary` — on demand after shell
- `GET .../chart/timeline` — on demand (paginated)
- `GET .../chart/sections/{section}` — when the user opens that tab

Do **not** prefetch every section at chart open. Do not send work-facility as chart `facility_id` unless the user enabled the chart filter.

Writes remain frozen command APIs. First Healthcare Web implementation pass **does not** include chart UI.

---

## 17. TanStack Query and PHI

| Setting | MVP |
|---|---|
| `staleTime` | short (e.g. 30s) for context; 0–30s for chart |
| `gcTime` | modest; cleared on logout/org switch |
| `refetchOnWindowFocus` | yes for `/iam/me/context` |
| `retry` | no retry on 401; limited otherwise |
| `persistQueryClient` | **Forbidden** for PHI |
| IndexedDB / localStorage cache | **Forbidden** for clinical queries |
| Service Worker cache of API | **Forbidden** |
| Offline / PWA | **Forbidden** |

Query keys **must** include `organizationId` and, for chart, `patientId`. Org switch → remove queries for the previous org.

---

## 18. Frontend state

| Store | Owner |
|---|---|
| Auth/session (token, exp, user) | Memory + OIDC client |
| Selected org | React context + `sessionStorage` (UUID only) |
| Work facility | React context + `sessionStorage` (UUID only, this org) |
| Chart facility filter | React context (not automatically work facility) |
| Patient / encounter | React context; cleared on org switch |
| Server data | TanStack Query |
| UI chrome | Local component state |

**No Redux/Zustand** for MVP. Not justified.

---

## 19. API client

Generated types from FastAPI OpenAPI. Commit generated types in `apps/healthcare-web` so drift is reviewable; regenerate in CI and fail on diff.

Inject on every PHI/staff call:

- `Authorization: Bearer <memory token>`
- `X-Organization-Id`
- `X-Facility-Id` only when work facility is set **and** sending it is safe (see §10 workaround)
- `X-Purpose` from workspace
- `X-Correlation-ID`

Headers are **request context**. Backend may deny/conceal regardless.

Error mapping (no raw stacks):

| Status | UX |
|---|---|
| 401 | session expired |
| 403 | permission denied; revalidate context |
| 404 | not found / concealed |
| 409 | state conflict (e.g. retired identity) |
| 422 | invalid input/filter/context |

Env (public only): `VITE_API_BASE_URL` (empty = same-origin), `VITE_OIDC_ISSUER`, `VITE_OIDC_CLIENT_ID`, optional end-session URL. **No secrets** in frontend env.

Dev: Vite proxy `/api` → backend to avoid CORS. Production: reverse proxy same origin. If split origin later: extend `CORSMiddleware` `allow_headers` with `X-Organization-Id`, `X-Facility-Id`, `X-Purpose` (config change, not 0019). Current allow-list is `Authorization`, `Content-Type`, `X-Correlation-ID` only; default origin `http://localhost:3000` (Vite is typically 5173).

---

## 20. i18n, a11y, responsive

MVP locales: `id`, `en`. Fallback `id`. ZH later (catalogs + date/number), not this implementation.

Locale source: browser + frontend preference key `php.healthcare-web.locale` in `localStorage` (not PHI). **No** user locale column. **No** 0019.

Do not translate canonical codes (`clinical.condition.read`, SNOMED, status enums). UI chrome via i18next. `code_display` remains authored.

Accessibility (implementation standard, not this pass): keyboard, focus management, contrast, labels, live status, table navigation.

Responsive: desktop primary, tablet supported, limited mobile browser. **Not** a Patient Mobile replacement.

Print/export: **DEFERRED**.

---

## 21. Security headers (expected later)

API already sets `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy`, `Cache-Control: no-store`, HSTS on HTTPS.

SPA hosting should add CSP (`default-src 'self'`; IdP issuer; no `unsafe-inline` scripts if possible; `frame-ancestors 'none'`). Not implemented in this pass.

XSS: React default escaping; clinical note `body_text` as text, never `dangerouslySetInnerHTML`; no rich-text editor in MVP.

---

## 22. Unsaved writes and multi-tab

Future clinical forms: organization or work-facility switch, logout, and session expiry must prompt if the form is dirty. Do not silently change tenant behind an open form.

Two tabs: independent `sessionStorage` org/facility/patient. A shared `localStorage` org would retarget another tab — **forbidden**. Same access token may exist in two tabs’ memory; that is acceptable. Visible org name in chrome reduces operational mistakes.

---

## 23. Stale permissions and membership

Backend is always authoritative. Bootstrap permissions are hints.

MVP: refetch `GET /iam/me/context` on window focus and after **403**. No periodic poll required.

If membership is removed: next authorize fails; frontend clears tenant PHI, refetches organizations, selects another org or exits.

If facility scope changes: on 403/404, refetch accessible facilities; drop invalid work facility.

---

## 24. Threat model

| Threat | Impact | Mitigation | Implementation test |
|---|---|---|---|
| Token theft / XSS | Session hijack | Memory-only token; React text; CSP later; no `dangerouslySetInnerHTML` | No token in localStorage; note body as text |
| localStorage token | Shared workstation | Forbidden | Grep / e2e: no `access_token` in web storage |
| CSRF | Session use | Bearer header; cookies not used | Document; if cookies added later, CSRF required |
| Stale session after logout | PHI on back button | Clear Query + sessionStorage; no-store | Logout then back → login, no chart |
| Persisted PHI cache | Leak on shared PC | No persistQueryClient / SW | Assert no IndexedDB PHI |
| Org header tamper | Cross-tenant | PDP membership; 404 conceal | Foreign org 404 |
| Facility header tamper | Cross-site | Frozen facility tenant check | Foreign facility conceal |
| Merged permissions in UI | Wrong workspace | Context permissions for selected org only | A clinician+B admin: A context lacks admin perms |
| Role spoofing in SPA | Hidden UI only | API still denies | Direct API 403 |
| Direct API calls | Bypass UI | Unchanged PDP | Existing Product Access tests |
| Open redirect | Phishing | OIDC redirect URI allow-list at IdP | Config review |
| NIK/BPJS in URL | Referrer leak | Forbidden in routes | Router tests |
| Stale bootstrap | Extra chrome | 403 → refetch context | Integration |
| Multi-tab org confusion | Wrong tenant writes | Per-tab sessionStorage | Two tabs independent |
| Patient/platform token | Wrong PDP | `php-api` only | 401 |
| IdP none / HS256 in prod | Weak auth | HS256 only non-prod | Config invariant |

---

## 25. Migration 0019

**Do not create.** Shell APIs read existing `users`, `organization_memberships`, `roles`, `role_permissions`, `organizations`, `facilities`.

No user preference table. No locale column. No session table.

---

## 26. Implementation sequence

1. **Backend:** three context/facility GETs + tests (single-org, multi-org, role-differs-by-org, explicit vs ALL_IN_ORGANIZATION, foreign 404, php-patient 401). Optional CORS header allow-list if split-origin is in that same pass; prefer documenting Vite/proxy instead.
2. **Harden and freeze** those APIs (no 0019, no PDP edits).
3. **Healthcare Web scaffold** at `apps/healthcare-web`: Vite/React/TS, router, i18n, API client, OIDC memory session, org picker, work-facility picker, permission nav, empty `/app` layout.
4. **Patient lookup UI** (separate implementation after shell freeze) using frozen MPI lookup.
5. **Chart UI** consuming frozen Clinical Read Core (shell first, then summary/sections/timeline on demand).
6. Clinical **command** forms later (React Hook Form + frozen command APIs).

Do not start the SPA before step 1 is at least implemented; the picker cannot function without the APIs. Do not start chart UI in the first frontend pass.

---

## 27. Test contract (preview — no tests now)

**Backend:** single-org staff; multi-org staff; CLINICIAN in A + ORG_ADMIN in B → context A lacks admin permissions and context B lacks clinician-only writes as applicable; explicit facilities; org-wide empty facility binding → ALL_IN_ORGANIZATION and org facilities only; foreign org/facility excluded; `php-patient` / `php-platform` denied on these staff routes; no PHI fields.

**Frontend (later):** login/expiry; org switch clears PHI queries; work-facility change does not apply chart `facility_id`; permission nav; 401/403/404/409/422 mapping; logout clears cache; per-tab org; no persistent PHI cache; patient/platform tokens rejected.

---

## 28. Classification

| Topic | Class |
|---|---|
| Healthcare Web shell | **APPROVED FOR IMPLEMENTATION** (after this design; no code in this pass) |
| Staff auth `php-api` + OIDC PKCE | **APPROVED FOR IMPLEMENTATION** |
| Context bootstrap APIs | **APPROVED FOR IMPLEMENTATION** |
| Organization picker | **APPROVED FOR IMPLEMENTATION** |
| Facility picker | **APPROVED FOR IMPLEMENTATION** |
| Permission navigation | **APPROVED FOR IMPLEMENTATION** |
| Patient lookup UI | **READY FOR SEPARATE DESIGN** of the screen; API **APPROVED BY FROZEN FOUNDATION** |
| Clinical chart UI | **READY FOR SEPARATE DESIGN** (APIs frozen) |
| Patient timeline UI | **READY FOR SEPARATE DESIGN** |
| Clinical forms | **READY FOR SEPARATE DESIGN** |
| Request-org-scoped staff principal | **IMPLEMENTED** (resolution pass; Wave1PolicyPDP untouched) |
| Nurse workspace | **FORBIDDEN** until permission design |
| Scheduling | **DEFERRED** |
| Notifications | **DEFERRED** |
| Pharmacy | **DEFERRED** |
| Today’s patients / encounter index | **DEFERRED** / separate read design |
| Name search | **FORBIDDEN** |
| Print/export | **DEFERRED** |
| Offline/PWA | **FORBIDDEN** for MVP |
| Patient Mobile | **FORBIDDEN** in this client |
| Platform Admin | **FORBIDDEN** in this client |
| Subscription / AI | **DEFERRED** / **FORBIDDEN** in shell |

---

## 29. P0/P1/P2/P3 impact on this design

| Finding | Blocks shell design? |
|---|---|
| P2 DENIED-audit rollback | No |
| P3 Docker image lag | No (source APIs exist) |
| P3 clinical_notes org index | No |
| P3 inverted Read Core date range empty page | No |
| Multi-org permission/facility union (was inherited) | **Resolved** before shell APIs; see `docs/gates/product-access-multi-org-context-isolation-resolution.md` |

---

## 30. What this pass does not do

No production code, tests, migration `0019`, `apps/healthcare-web`, commit, tag, or push. Frozen Clinical Read Core, clinical domains, Product Access semantics, ProductAccessPDP, and Wave1PolicyPDP remain untouched.
