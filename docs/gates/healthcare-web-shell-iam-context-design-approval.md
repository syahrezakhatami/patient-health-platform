# Healthcare Web shell and IAM context — design approval

**Date:** 2026-08-26  
**Kind:** Design only  
**Verdict:** APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN  
**Baseline:** `clinical-read-core-frozen` / `5d124de2c80bc17127fc17e9f6a730828c13a63a`  
**Parent:** `product-access-tenancy-foundation-frozen` / `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716`  
**Alembic:** `current == heads == 20260814_0018` (one head; no `0019`)  
**Wave1PolicyPDP:** FROZEN  
**ProductAccessPDP:** FROZEN (`default_pdp()`)  
**Clinical Read Core:** FROZEN  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does **not** authorize frontend files, production routes, migration `0019`, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, AI, commit, tag, or push.

Source contract: `docs/architecture/healthcare-web-shell-iam-context-design.md`.  
Companion canvas (review-only, outside git): [healthcare-web-shell-iam-context.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/healthcare-web-shell-iam-context.canvas.tsx)

---

## 1. Verified baseline

If this table were materially wrong, this pass would STOP.

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `5d124de2c80bc17127fc17e9f6a730828c13a63a` |
| Tag | Annotated `clinical-read-core-frozen` → HEAD |
| Parent | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` |
| Working tree besides this design | Clean published freeze; this pass adds design docs only |
| Alembic | `current == heads == 20260814_0018` |
| Migration `0019` | Does not exist |
| `docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| Frontend app | Does not exist |

Independently verified: Healthcare Web must use `php-api`; ProductAccessPDP is authoritative; organization is MVP tenant; facility empty-list means org-wide in Wave1; `GET /iam/users/me` exists and is insufficient; no HTTP facility list; no refresh-token API; Clinical Read Core is frozen; one Healthcare Web app; Vite+React+TS remains the technology choice.

---

## 2. Decisions (approved)

| # | Topic | Decision |
|---|---|---|
| 1 | App | One Healthcare Web. No Doctor/Nurse/Hospital/Clinic apps |
| 2 | Stack | Vite, React, TypeScript, React Router, TanStack Query, React Hook Form, i18next, OpenAPI types |
| 3 | Repo | `apps/healthcare-web` later in this git repo. No shared packages yet |
| 4 | Audience | `php-api` only |
| 5 | Auth | OIDC Authorization Code + PKCE. Backend remains validator-only |
| 6 | Tokens | In-memory only. No localStorage bearer |
| 7 | Refresh | No PHP refresh API. Silent OIDC renew in memory or re-login |
| 8 | Logout | Local + IdP end-session if configured. No PHP revocation |
| 9 | Bootstrap | Do not expand `/iam/users/me` |
| 10 | APIs | `GET /api/v1/iam/me/organizations`; `GET /api/v1/iam/me/context`; `GET /api/v1/organizations/{organization_id}/facilities/accessible` |
| 11 | 0019 | **Not created / not required** |
| 12 | Org switch | Clears patient, chart queries, invalid facility, nav cache |
| 13 | Facility | Work context ≠ chart filter. Chart stays org-wide by default |
| 14 | Multi-org | Effective permissions for **selected org only** in the context DTO |
| 15 | Nav | Permission codes, not role-name switches |
| 16 | PHI cache | Memory only. No PWA/offline |
| 17 | Multi-tab | Per-tab `sessionStorage` org/facility |
| 18 | i18n | ID+EN; locale local to SPA; no schema |
| 19 | Lookup | Frozen MPI identifier lookup. No directory |
| 20 | Sequence | Context APIs → freeze APIs → SPA shell → lookup → chart UI |

---

## 3. Exact API surface (next backend pass)

| Method | Path | Org header | PHI |
|---|---|---|---|
| GET | `/api/v1/iam/me/organizations` | not required | none |
| GET | `/api/v1/iam/me/context` | required | none |
| GET | `/api/v1/organizations/{organization_id}/facilities/accessible` | required; must match path | none |

Audience: `php-api`. Foreign org/facility: 404 conceal. `facility_scope` distinguishes `ALL_IN_ORGANIZATION` from `EXPLICIT` so an empty id list is never “no facilities”.

---

## 4. Inherited findings (not redesigned)

- Multi-org permission/facility union was a real P1 at design time. It is **resolved** in `docs/gates/product-access-multi-org-context-isolation-resolution.md` (principal/context projection; Wave1PolicyPDP untouched). Shell context **must** match that enforcement.
- P2 DENIED-audit rollback; P3 Docker lag; P3 notes index; P3 inverted date range — **do not block** this shell.

---

## 5. Next implementation scope

**Backend (minimum):** the three GETs, org-specific permission aggregation, accessible facilities, tests listed in the contract. No Clinical Read Core edits. No Wave1/ProductAccessPDP edits.

**Frontend first pass:** `apps/healthcare-web` scaffold, OIDC memory session, org/facility context, permission nav, i18n, API client, empty layout. **Not** chart UI, not clinical forms, not lookup (lookup is the following pass).

---

## 6. Working tree

This pass adds/updates:

- `docs/architecture/healthcare-web-shell-iam-context-design.md`
- `docs/gates/healthcare-web-shell-iam-context-design-approval.md`
- links from prior Healthcare Web discovery docs

No production code. No tests. No migration. **NO COMMIT. NO TAG. NO PUSH.**

---

## 7. Verdict

HEALTHCARE WEB SHELL & IAM CONTEXT = APPROVED FOR DESIGN ONLY  

IMPLEMENTATION = NOT STARTED  
MIGRATION 0019 = NOT CREATED  
HEALTHCARE WEB FRONTEND = NOT CREATED  
CLINICAL READ CORE = FROZEN / UNCHANGED
