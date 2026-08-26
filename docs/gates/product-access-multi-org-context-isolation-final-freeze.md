# Product Access multi-organization context isolation — final freeze

**Date:** 2026-08-26  
**Verdict:** PASS  
**P0:** none  
**P1 unresolved:** none  
**MULTI-ORG PERMISSION ISOLATION:** FROZEN  
**MULTI-ORG FACILITY ISOLATION:** FROZEN  
**PRODUCT ACCESS SECURITY PATCH:** FROZEN  
**PRODUCT ACCESS SECURITY PATCH:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement IAM shell context APIs, Healthcare Web, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, entitlement, billing, or AI. Migration `0019` was not created. Wave1PolicyPDP and ProductAccessPDP were not modified. Clinical Read Core was not modified.

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` (at freeze) |
| Published parent SHA | `5d124de2c80bc17127fc17e9f6a730828c13a63a` |
| Parent tag | annotated `clinical-read-core-frozen` → same SHA |
| Parent of that baseline | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` (`product-access-tenancy-foundation-frozen`) |
| Final freeze SHA | this publication commit (annotated tag peel) |
| Final annotated tag | `product-access-multi-org-context-isolation-frozen` → this publication commit |
| Parent of freeze | `clinical-read-core-frozen` |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration `0019` | **Not created** |
| `docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `product_access_pdp.py` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical Read Core | Untouched |

Old tags were not moved or rewritten:

- `clinical-read-core-frozen`
- `product-access-tenancy-foundation-frozen`
- `wave-2b-clinical-foundation-complete`
- `wave-2b8-family-history-frozen`

Expected lineage:

```
clinical-read-core-frozen
5d124de2c80bc17127fc17e9f6a730828c13a63a
        |
        v
product-access-multi-org-context-isolation-frozen
(this publication commit)
```

---

## B. Defect / root cause / severity

**Before fix:** `IamRepository.load_principal` built one staff `Principal` whose `permission_codes` were the union of every ACTIVE membership’s roles, and whose `facility_ids` were the union of every non-null membership facility. `authorize._context` copied that union into Wave1 `scopes` / `actor_facility_ids`. Wave1 then allowed an action if it was in that global set **and** the request organization was merely one of the actor’s organizations.

**Impact:** **P1 CROSS-ORGANIZATION PRIVILEGE BLEED**

Example: CLINICIAN in Organization A + ORG_ADMIN in Organization B → B’s admin permissions could authorize operations while `X-Organization-Id=A`. Mixed empty/explicit facility bindings could merge across organizations (empty list no longer meant ALL_IN_ORGANIZATION for the selected org only).

**Fix:** project `Principal.for_organization` before ProductAccessPDP / Wave1PolicyPDP. Frozen Product Access contract was already “Organization == tenant”; this freeze records that correction.

Both original P1 items remain **FIXED**.

---

## C. `Principal.for_organization` contract

Frozen dataclass. Returns a **new** projected principal. Does not mutate `self`.

For selected organization O:

| Field | Rule |
|---|---|
| Tenant memberships | `organization_id == O` only |
| Platform memberships | `organization_id is None` retained as platform (not rewritten as hospital membership) |
| Permissions | Union of kept memberships’ `permissions_by_role_id` only |
| Role map | Copied for kept memberships only (no hidden other-org residue) |
| Facilities | Any selected-org `facility_id is None` → empty set (ALL_IN_ORGANIZATION for O). Else explicit ids in O |
| `organization_ids` | `{O}` if a tenant membership exists, else empty |
| PHI | Platform does not grant `clinical.*` / `mpi.*`. Frozen ProductAccessPDP still denies those prefixes when `iam.platform` is in scopes |

---

## D. Idempotence

`P.for_organization(A).for_organization(A)` is authorization-equivalent to `P.for_organization(A)`: no permission gain/loss, no duplicate memberships or facilities. Original `P` unchanged.

---

## E. No tenant hopping

`P.for_organization(A).for_organization(B)` does **not** restore B. Scoping is not a tenant-hopping primitive.

---

## F. Double-scoping and unscoped path

`get_principal` projects when `X-Organization-Id` is present. `authorize._context` projects staff principals when `organization_id` is present.

`get_principal(A)` → `authorize(A)` is idempotent: A authority kept, B not restored.

An unscoped authenticated principal passed to `authorize` with request org A is narrowed to A **before** ProductAccessPDP / Wave1. There is no production staff path that feeds Wave1 a global union when a request organization is present.

`GET /auth/context` evaluates a SYSTEM principal with empty scopes via ProductAccessPDP (not a staff union bypass). Production `Wave1PolicyPDP()` exists only inside `product_access_pdp.py`.

---

## G. Header / path mismatch and missing membership

Header A + path/resource B, and reverse → deny/conceal (403). IAM membership body org mismatch with header → 403.

Valid staff token + `X-Organization-Id` of an organization with no membership → fail. No fallback to global union, platform tenant grant, or another org’s membership.

Clinical routes missing `X-Organization-Id` → 422. Path-org APIs without header still project in `authorize` to the path org (not a global Wave1 union).

---

## H. Platform preservation and hybrid

PLATFORM_ADMIN + `X-Organization-Id=A` + clinical or MPI PHI → **403**. Approved organization bootstrap create remains allowed. Org header does not convert platform into healthcare staff.

Hybrid (platform membership + A ORG_ADMIN) is a supported identity shape: A non-PHI org-admin may apply; `iam.platform` does not add PHI and frozen ProductAccessPDP still denies PHI; B without membership has no tenant authority.

---

## I. Same-org memberships and revoked

Multiple ACTIVE memberships in the **same** organization (different roles) may union. Cross-org union is forbidden.

Explicit same-org A1 + A2 → `{A1, A2}`, not empty/ALL.

REVOKED memberships are excluded by `load_principal`. They do not contribute after revoke.

Roles/permissions have no disable flag. Each request reloads from the database. No principal cache.

---

## J. Role and facility matrices

| Setup | Result |
|---|---|
| A CLINICIAN / B ORG_ADMIN | A: clinical write yes, org-admin no. B: inverse |
| Reverse | Inverse |
| A CLINICIAN / B REGISTRAR / C AUDITOR | No three-role union. Chart A clinician sections; B encounters only; C read, no clinician write |
| A AUDITOR / B CLINICIAN | A write 403; B write allowed |
| A REGISTRAR / B IDENTITY_OFFICER | A encounter yes / merge 403; B encounter 403 |
| Explicit A1 / B2 | A sees A1 only; B sees B2 only |
| A empty (org-wide) / B explicit B1 | A: A1+A2 yes, B1 no. B: B1 yes, A facilities no |
| Org A + facility B1 (and reverse) | deny/conceal |
| Explicit A1, unlisted A2 | A2 deny |

Empty list never means all facilities across every membership.

---

## K. Concurrent isolation and cache

`for_organization` is request-local (new frozen instance). Concurrent same-JWT A and B requests keep independent authority. No `subject → org-scoped-principal` cache. No principal `ContextVar`. `Depends(get_principal)` is per request. `IamRepository.load_principal` hits the database each time.

---

## L. ProductAccessPDP / Wave1 input

STAFF ProductAccessPDP receives already tenant-scoped context (plus preserved platform scope when a platform membership exists). ProductAccessPDP was **not** modified.

Wave1 receives organization-scoped permissions, facility ids, and tenant org set. Hash unchanged (section A).

---

## M. Regression

| Suite | Result |
|---|---|
| Clinical Read Core (including freeze/hardening, A↔B chart sections, cluster/facility/cursor/section/audit) | Passed inside full pytest |
| Product Access & Tenancy (PHI deny, audiences, PatientPrincipal, account immutability, self-access, `facility_tenant_decision`, MPI collision, unknown principal) | Passed inside full pytest |
| PatientPrincipal / PATIENT_ACCESS / binding / audience | Unaffected; passed |

---

## N. Quality gates (fresh 2026-08-26)

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass (195 files) |
| `mypy app` | Pass (132 source files) |
| Full pytest | **374 passed** (equal to hardening; was 345 at Clinical Read Core freeze) |
| Alembic | `current == heads == 20260814_0018` |
| Migration `0019` | Absent |
| `/api/v1/health/live` | 200 `{"status":"alive"}` |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage = ok |
| Secret scan | No `.env`, private keys, JWTs, credentials, DB secrets, runtime logs, or runtime volumes in the intended commit set |

---

## O. P0 / P1 / P2 / P3

| Severity | Item | Status |
|---|---|---|
| P0 | — | None |
| P1 | Cross-org permission union | **FIXED** |
| P1 | Cross-org facility union / empty-scope corruption | **FIXED** |
| P1 unresolved | — | **None** |
| P2 / P3 from this patch | — | None opened |

Verdict: **PASS** (no unresolved P0/P1).

---

## P. Exact files in this publication commit

Production:

- `backend/app/api/v1/deps.py`
- `backend/app/modules/authorization/application/authorize.py`
- `backend/app/modules/iam/domain/models.py`
- `backend/app/modules/iam/infrastructure/repositories.py`

Tests:

- `backend/tests/unit/test_principal_organization_scope.py`
- `backend/tests/unit/test_authorization_organization_scope.py`
- `backend/tests/integration/test_product_access_multi_org_isolation.py`
- `backend/tests/integration/test_multi_org_context_isolation_hardening.py`

Docs:

- `docs/architecture/healthcare-web-shell-iam-context-design.md`
- `docs/gates/healthcare-web-shell-iam-context-design-approval.md`
- `docs/architecture/healthcare-web-clinical-chart-discovery.md` (design-only links)
- `docs/gates/healthcare-web-clinical-chart-architecture-discovery.md` (design-only links)
- `docs/gates/product-access-multi-org-context-isolation-resolution.md`
- `docs/gates/product-access-multi-org-context-isolation-hardening.md`
- `docs/gates/product-access-multi-org-context-isolation-final-freeze.md` (this file)

No IAM shell routes. No `apps/healthcare-web`. No Alembic revision.

---

## Q. Push verification

Expected after push (no force):

- `HEAD == origin/main`
- working tree clean
- `product-access-multi-org-context-isolation-frozen` peels to HEAD
- old freeze tags unchanged
- Alembic still `20260814_0018`; no `0019`

---

## R. Explicitly not started

IAM shell context implementation, Healthcare Web frontend, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, AI.

STOP after publish.
