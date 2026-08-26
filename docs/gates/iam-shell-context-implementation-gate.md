# IAM shell context backend — implementation gate

**Status:** IMPLEMENTED  
**Hardening:** NOT STARTED  
**Frozen:** NO  
**Date:** 2026-08-26  
**Scope:** Staff Healthcare Web IAM/context GET APIs only  
**Baseline:** `product-access-multi-org-context-isolation-frozen` / `70baee1bd24969d29d2b5f7eeda0240fb8bde877` / Alembic `20260814_0018`

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. IAM shell context is **not frozen**. Hardening has **not** started. No commit, tag, or push.

Source implementation: `docs/architecture/iam-shell-context-backend.md`.  
Authoritative design: `docs/architecture/healthcare-web-shell-iam-context-design.md`.  
Design approval: `docs/gates/healthcare-web-shell-iam-context-design-approval.md`.

---

## Verdict

IAM SHELL CONTEXT BACKEND = IMPLEMENTED  
IAM SHELL CONTEXT HARDENING = NOT STARTED  
IAM SHELL CONTEXT BACKEND = NOT FROZEN  
MIGRATION 0019 = NOT CREATED  
HEALTHCARE WEB FRONTEND = NOT CREATED

---

## In scope

Three staff GET routes, explicit DTOs, selected-org permission/facility projection via frozen `Principal.for_organization`, accessible ACTIVE facilities, implementation tests, this gate, architecture record.

## Out of scope

`apps/healthcare-web`, React/Vite, OIDC browser code, login/org/facility/nav/chart UI, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, AI, FHIR, `/api/v2`, migration `0019`, Clinical Read Core edits, ProductAccessPDP/Wave1PolicyPDP edits, multi-org isolation contract changes, hardening gate, freeze, commit, tag, push.

---

## Baseline

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `70baee1bd24969d29d2b5f7eeda0240fb8bde877` |
| Tag | Annotated `product-access-multi-org-context-isolation-frozen` peels to HEAD |
| Parent | `5d124de2c80bc17127fc17e9f6a730828c13a63a` |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Not created |
| `Wave1PolicyPDP` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `ProductAccessPDP` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical Read Core | Untouched |
| `backend/docker-compose.yml` | Untouched |
| Working tree before implementation | Clean published freeze |

---

## Routes

| Method | Path |
|---|---|
| GET | `/api/v1/iam/me/organizations` |
| GET | `/api/v1/iam/me/context` |
| GET | `/api/v1/organizations/{organization_id}/facilities/accessible` |

Audience: `php-api` only. `GET /api/v1/iam/users/me` unchanged.

---

## DTOs / behavior (summary)

Organizations: bounded tenant metadata; platform-null excluded; revoked excluded; stable sort.

Context: selected-org identity, role codes, **tenant** `effective_permissions` (sorted, unique), `facility_scope`, `work_facility_required`. No facility list. No platform permission leak.

Facilities: membership + header/path match + `org.facility.read`; ACTIVE only; org-filtered SQL; stable `name, id` sort.

Facility scope: `ALL_IN_ORGANIZATION` vs `EXPLICIT` matching frozen same-org union / org-wide NULL.

---

## Errors

401 wrong/missing staff token (including patient/platform audience).  
403 unprovisioned.  
404 conceal unknown/foreign/no membership/header mismatch.  
422 invalid/missing org header.

---

## Purpose / audit / provenance

HTTP purpose-exempt (IAM bootstrap). No new purpose catalog. Facilities `authorize` denials may record `ADMINISTRATION`. Success reads not audited. Zero clinical provenance.

---

## Migration

**No 0019.** Existing IAM/org/facility tables only.

---

## Tests

`backend/tests/unit/test_iam_shell_context_scope.py`  
`backend/tests/integration/test_iam_shell_context.py`

No `iam-shell-context-hardening-gate.md`.

---

## Quality

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass |
| `mypy app` | Pass (134 source files) |
| `pytest` | **384 passed** (published freeze baseline 374; +10 this pass) |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Health live | 200 |
| Health ready | 200; postgres=ok, redis=ok, object_storage=ok |
| Secret scan | Clean (no `.env`, JWTs, OIDC secrets, private keys, DB passwords, runtime logs/volumes in intended tree) |

Clinical Read Core, Product Access / multi-org isolation, and frozen clinical suites are included in the 384.

---

## P0 / P1 / P2 / P3

- **P0:** none  
- **P1:** none  
- **P2 (inherited):** DENIED-audit rollback  
- **P3:** Docker image lag — `:9100` `GET /api/v1/iam/me/organizations`, `/iam/me/context`, and `/organizations/{id}/facilities/accessible` return **404 Not Found** unauthenticated, while existing `GET /api/v1/iam/users/me` returns **401**. Image was **not** rebuilt (forbidden in this pass). Inherited P3 notes index / inverted date range remain out of scope.

---

## Docker

Ports unchanged. Compose untouched. Image **not** rebuilt. Missing context routes on `:9100` are **P3 DOCKER IMAGE LAG**. In-process tests exercise the new routes.

---

## Contract deviations

None that require redesign.

Notes (approved or existing conventions):

- Context omits `accessible_facilities` (design allows split with 8.3).
- Organizations list uses an unscoped principal so a stale `X-Organization-Id` cannot shrink the picker.
- DTO tenant-permission filter excludes platform catalog while leaving frozen `Principal.for_organization` (platform memberships retained internally) unchanged.
- Inactive facilities are omitted; inactive organizations are listed with `status` for UI disable/omit.

---

## Files (this pass)

- `backend/app/modules/iam/application/shell_schemas.py` (added)
- `backend/app/modules/iam/application/shell_context.py` (added)
- `backend/app/api/v1/iam.py` (two GETs)
- `backend/app/api/v1/organizations.py` (one GET)
- `backend/app/api/v1/deps.py` (`get_unscoped_principal`)
- `backend/app/modules/organization/infrastructure/repositories.py` (`list_organizations_by_ids`, `list_facilities_for_shell`)
- `backend/tests/unit/test_iam_shell_context_scope.py` (added)
- `backend/tests/integration/test_iam_shell_context.py` (added)
- `docs/architecture/iam-shell-context-backend.md` (added)
- `docs/gates/iam-shell-context-implementation-gate.md` (added)

---

## Publication

NO COMMIT  
NO TAG  
NO PUSH  
NO FREEZE  
NO HARDENING GATE  

HEALTHCARE WEB FRONTEND = NOT CREATED  
PATIENT MOBILE = NOT STARTED  
PLATFORM ADMIN WEB = NOT STARTED  
SCHEDULING = NOT STARTED  
NOTIFICATIONS = NOT STARTED  
SUBSCRIPTION = NOT STARTED  
AI = NOT STARTED  
