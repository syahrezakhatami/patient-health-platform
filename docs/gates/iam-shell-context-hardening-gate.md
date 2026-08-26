# IAM shell context backend — hardening gate

**Status:** HARDENING COMPLETE  
**Frozen:** NO  
**Date:** 2026-08-26  
**Baseline:** `product-access-multi-org-context-isolation-frozen` / `70baee1bd24969d29d2b5f7eeda0240fb8bde877`  
**Alembic:** `current == heads == 20260814_0018`  
**Implementation pytest:** 384 passed  
**Hardening pytest:** **403 passed**

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. IAM shell context is **not frozen**. No commit, tag, or push.

Authoritative design: `docs/architecture/healthcare-web-shell-iam-context-design.md`.  
Implementation: `docs/architecture/iam-shell-context-backend.md`.  
Implementation gate: `docs/gates/iam-shell-context-implementation-gate.md`.

---

## Verdict

IAM SHELL CONTEXT BACKEND = IMPLEMENTED  
IAM SHELL CONTEXT HARDENING = COMPLETE  
IAM SHELL CONTEXT BACKEND = NOT FROZEN  
MIGRATION 0019 = NOT CREATED  
HEALTHCARE WEB FRONTEND = NOT CREATED

---

## Baseline

| Item | Result |
|---|---|
| HEAD | `70baee1bd24969d29d2b5f7eeda0240fb8bde877` |
| Tag | `product-access-multi-org-context-isolation-frozen` peels to HEAD |
| Branch | `main` == `origin/main` |
| Working tree | Uncommitted implementation + this hardening pass |
| Alembic | `20260814_0018` (one head) |
| Migration `0019` | Not created |
| `Wave1PolicyPDP` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `ProductAccessPDP` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical Read Core | Untouched |
| `backend/docker-compose.yml` | Untouched |

---

## Routes

GET only:

- `/api/v1/iam/me/organizations`
- `/api/v1/iam/me/context`
- `/api/v1/organizations/{organization_id}/facilities/accessible`

OpenAPI confirms GET-only on those paths. Unsupported methods return 405/404. No `/api/v2`, `/fhir`, patient shell, or extra IAM shell routes.

---

## Staff audience

`php-api` accepted when otherwise authorized. `php-patient`, `php-platform`, missing `aud`, wrong `aud`, mixed `aud` array, and malformed JWT → **401**. Audience is enforced before tenant data.

---

## Organizations endpoint

ACTIVE tenant memberships only, grouped by organization (one row per org). Sorted `(name.lower(), code, id)`. Stale `X-Organization-Id` is ignored (unscoped principal). No global directory.

Same-org CLINICIAN + REGISTRAR → **one** organization entry with sorted `role_codes`. Platform-null is not listed.

---

## Platform-only semantics

`provisioned: true` + `organizations: []` is **account provisioning**, not tenant authorization. Design §11: 0 orgs → provisioned-but-unassigned. Retained. Context/facilities for a dummy org → 404 conceal.

Hybrid platform + A ORG_ADMIN: picker is A only; context A has tenant permissions only (`iam.platform` absent).

---

## Context

Missing `X-Organization-Id` → 422. No fallback to first/last/global/platform principal.

Unknown UUID, known foreign org, and revoked membership: context **and** facilities both 404 with the same conceal message. Invalid UUID header → 422.

`effective_permissions` match `ROLE_PERMISSIONS` for the selected-org role and match enforcement: A CLINICIAN can create a condition; B ORG_ADMIN cannot; B can create a facility; A cannot. Role codes are selected-org, sorted, deduplicated, platform-excluded. Permissions are sorted unique and stable across repeated calls. No B metadata in context A.

---

## Facility scope / `work_facility_required`

Discriminator is only `ALL_IN_ORGANIZATION` or `EXPLICIT`. Org-wide is never `EXPLICIT []`.

`work_facility_required` is a **UX hint**: true iff EXPLICIT and at least one membership facility id. It is not authorization. Backend writes remain PDP-authoritative.

| Case | Scope | `work_facility_required` |
|---|---|---|
| NULL binding | ALL_IN_ORGANIZATION | false |
| One explicit ACTIVE | EXPLICIT | true |
| Multiple explicit | EXPLICIT | true |
| Explicit + inactive extra id | EXPLICIT | true; inactive omitted from list |

Context `facility_scope` matches the facilities endpoint.

---

## Facilities endpoint / `org.facility.read`

Design 8.3 explicitly authorizes `org.facility.read`. Catalog grants it to CLINICIAN, REGISTRAR, ORG_ADMIN, AUDITOR, and IDENTITY_OFFICER. All five roles receive 200. **Not a catalog/policy blocker.**

Header must equal path; missing header → 422. Header/path mismatch → 404 before facility/org directory queries (spy-tested). Query always filters `organization_id` (+ ACTIVE). Corrupt membership `facility_id` pointing at another org does not leak that facility. Revoked membership ids do not contribute. Inactive facilities omitted.

---

## Concurrency

Simultaneous context A, context B, and organizations picker: each response is request-local. Unscoped picker does not mutate the scoped context principal. A→B→A switch has no contamination.

---

## Purpose / audit / provenance

HTTP purpose-exempt (same as `/iam/users/me`). Missing, valid, or garbage `X-Purpose` does not change context permissions and does not grant foreign-org access.

Success reads of organizations, context, and facilities do not insert `audit_events` or `clinical_provenances`. Facility `authorize` denials still use existing DENIED audit with `ADMINISTRATION` (inherited P2 rollback unchanged).

---

## PHI / minimization / N+1

No patient identifiers, clinical facts, passwords, tokens, `role_id`, `revoked_at`, membership ids, audit/provenance ids, `address_text`, billing/subscription fields. Context omits `accessible_facilities`.

Nine tenant orgs + eight home facilities: bounded SELECTs (not one query per facility/org). SQLAlchemy bound parameters; sort uses columns not user identifiers. No Redis/permission cache in shell_context.

---

## `/iam/users/me`

Shape unchanged: `provisioned`, `id`, `subject`, `display_name`, `roles`, `permissions`.

---

## Regressions (full pytest)

Multi-org isolation / `Principal.for_organization`, Product Access & Tenancy, Clinical Read Core, frozen clinical through Family History: included in **403 passed**. PDPs untouched.

---

## Defects found / fixed

| Item | Result |
|---|---|
| Duplicate org picker rows | Already grouped; hardening verifies one row + sorted role_codes |
| Header/path mismatch querying facilities | Already 404-first; spy proves zero facility/org list queries; removed unused post-authorize `get_organization` on the facilities path |
| `work_facility_required` | Extracted helper; same approved UX rule |
| Platform catalog in tenant DTO | Already filtered; re-verified |
| `org.facility.read` vs staff roles | Compatible; no new grant |

No unresolved P0/P1. No new permission/policy invention.

---

## Quality

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass |
| `mypy app` | Pass (134 files) |
| `pytest` | **403 passed** (384 + 19) |
| Alembic | `current == heads == 20260814_0018` |
| Health live | 200 |
| Health ready | 200; postgres=ok, redis=ok, object_storage=ok |
| Secret scan | Clean |

Hardening tests: `backend/tests/integration/test_iam_shell_context_hardening.py` plus additional cases in `backend/tests/unit/test_iam_shell_context_scope.py`. Existing implementation tests unchanged in intent.

---

## P0 / P1 / P2 / P3

- **P0:** none  
- **P1:** none  
- **P2 (inherited):** DENIED-audit rollback  
- **P3:** Docker image lag — `:9100` new context routes 404 unauthenticated; existing `/api/v1/iam/users/me` 401. Image not rebuilt.

---

## Publication

NO COMMIT  
NO TAG  
NO PUSH  
NO FREEZE  

HEALTHCARE WEB FRONTEND = NOT CREATED  
PATIENT MOBILE = NOT STARTED  
PLATFORM ADMIN WEB = NOT STARTED  
SCHEDULING = NOT STARTED  
NOTIFICATIONS = NOT STARTED  
SUBSCRIPTION = NOT STARTED  
AI = NOT STARTED  
