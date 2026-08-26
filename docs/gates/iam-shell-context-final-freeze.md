# IAM shell context backend — final freeze

**Date:** 2026-08-26  
**Verdict:** PASS WITH P2  
**P0:** none  
**P1 unresolved:** none  
**IAM SHELL CONTEXT BACKEND:** FROZEN  
**IAM SHELL CONTEXT BACKEND:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement Healthcare Web frontend, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, or AI. Migration `0019` was not created. Wave1PolicyPDP, ProductAccessPDP, Clinical Read Core, and frozen multi-org authorization semantics were not modified.

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` (at freeze) |
| Published parent SHA | `70baee1bd24969d29d2b5f7eeda0240fb8bde877` |
| Parent tag | annotated `product-access-multi-org-context-isolation-frozen` → same SHA |
| Parent of that baseline | `5d124de2c80bc17127fc17e9f6a730828c13a63a` (`clinical-read-core-frozen`) |
| Final freeze SHA | this publication commit (annotated tag peel) |
| Final annotated tag | `iam-shell-context-frozen` → this publication commit |
| Parent of freeze | `product-access-multi-org-context-isolation-frozen` |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration `0019` | **Not created** |
| `backend/docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `product_access_pdp.py` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical Read Core | Untouched |

Old tags were not moved or rewritten:

- `product-access-multi-org-context-isolation-frozen`
- `clinical-read-core-frozen`
- `product-access-tenancy-foundation-frozen`
- `wave-2b-clinical-foundation-complete`

Expected lineage:

```
clinical-read-core-frozen
5d124de2c80bc17127fc17e9f6a730828c13a63a
        |
        v
product-access-multi-org-context-isolation-frozen
70baee1bd24969d29d2b5f7eeda0240fb8bde877
        |
        v
iam-shell-context-frozen
(this publication commit)
```

---

## B. Route surface

GET only:

| Method | Path |
|---|---|
| GET | `/api/v1/iam/me/organizations` |
| GET | `/api/v1/iam/me/context` |
| GET | `/api/v1/organizations/{organization_id}/facilities/accessible` |

`GET /api/v1/iam/users/me` public contract is unchanged. No extra shell routes. No POST/PUT/PATCH/DELETE variants. No `/api/v2`. No `/fhir`.

Staff audience: `php-api` only. `php-patient`, `php-platform`, missing/wrong/mixed `aud`, malformed JWT → 401.

---

## C. Organizations endpoint

ACTIVE tenant memberships only. Platform-null is not a tenant entry. Revoked memberships excluded. Multiple ACTIVE memberships in the same org → **one** organization row with sorted `role_codes`. Deterministic sort: `(name.lower(), code, id)`. No global directory. No PHI.

Stale `X-Organization-Id` does not shrink the picker (unscoped principal).

---

## D. Platform-only semantics

Platform-only principal:

```
provisioned: true
organizations: []
```

**`provisioned` means the IAM user account exists. It does not mean tenant access.** Design §11: 0 orgs → provisioned-but-unassigned. Context/facilities against a non-member org → 404 conceal. Platform Admin is not a Healthcare Web superuser.

---

## E. Hybrid platform + tenant

Platform membership + A ORG_ADMIN: organizations list is **A only**. Context A is A tenant permissions only. `iam.platform` and other platform-bootstrap codes are not Healthcare Web `effective_permissions`. Frozen ProductAccessPDP platform PHI deny remains intact.

---

## F. Context endpoint

Requires `X-Organization-Id`. Missing → 422. No fallback to first/last/global/platform. Unknown, foreign, and revoked membership → 404 conceal (aligned with facilities).

Uses frozen `Principal.for_organization(selected org)`. DTO tenant permissions drop platform catalog while leaving the frozen projection internally unchanged.

---

## G. Effective permissions and equivalence

Selected-org tenant memberships only. Sorted unique. A CLINICIAN / B ORG_ADMIN: context A clinician only; context B org-admin only. Representative APIs agree: A clinical condition create allowed; B denied. B facility create allowed; A denied.

`role_codes`: selected-org, sorted, deduplicated, revoked excluded, platform roles excluded. Display/context metadata only. Security remains permission-driven.

---

## H. Facility scope and `work_facility_required`

Exactly two states: `ALL_IN_ORGANIZATION` | `EXPLICIT`. NULL membership facility binding → `ALL_IN_ORGANIZATION`. Explicit ids → `EXPLICIT`. Same-org A1+A2 → EXPLICIT union. Any same-org ACTIVE NULL → ALL_IN_ORGANIZATION. Never `EXPLICIT []` meaning org-wide.

**`work_facility_required` is a UX helper only.** True iff scope is EXPLICIT and at least one membership facility id exists. It does **not** grant or deny authorization. It does **not** auto-select a facility. Backend writes remain ProductAccessPDP / Wave1 authoritative.

---

## I. Facilities endpoint

Requires staff audience, `X-Organization-Id` equal to path `{organization_id}`, tenant membership, and `org.facility.read` on the organization-scoped principal. Returns **ACTIVE** facilities only (existing `Facility.status`). Header A / path B and reverse → 404 conceal **before** facility directory query. Corrupt foreign `facility_id` does not leak. Revoked memberships do not contribute.

`org.facility.read` is the approved design grant. CLINICIAN, REGISTRAR, ORG_ADMIN, AUDITOR, and IDENTITY_OFFICER all retrieve accessible facilities. No role-name bypass.

---

## J. Concurrency, purpose, audit, provenance

Concurrent context A, context B, and organizations picker remain request-local.

HTTP purpose-exempt (same as `/iam/users/me`). Missing, valid, or garbage `X-Purpose` does not expand authority.

Organizations and context success reads are not audited. Facilities success follows existing IAM/org read convention (no success audit). Facility denials may use existing DENIED audit with `ADMINISTRATION`. Inherited DENIED-audit rollback remains **P2**. Zero `clinical_provenances`.

---

## K. Minimization and performance

No patient/clinical PHI. No auth secrets. No `role_id`, `revoked_at`, membership ids, audit/provenance ids, or facility `address_text`. Context omits the full facility list.

Organizations derive from the caller’s ACTIVE memberships (`IN` by id). Context derives from `Principal.for_organization`. Facilities SQL filters `organization_id` (+ ACTIVE, optional explicit ids). No global directory post-filter. No one-query-per-permission or per-facility pattern. No Redis cache.

---

## L. Regression

| Suite | Result |
|---|---|
| `GET /iam/users/me` | Unchanged shape; passed |
| Multi-org isolation (`for_organization`, idempotence, hopping, double-scoping, same-org union, concurrency, platform PHI, facility isolation) | Passed inside full pytest |
| Clinical Read Core (chart/summary/timeline/sections/cluster/cursor/audit/provenance/DTOs) | Untouched; passed inside full pytest |
| Product Access & Tenancy (PHI deny, audiences, PatientPrincipal, account immutability, `facility_tenant_decision`, MPI collision, unknown principal) | Passed inside full pytest |
| Frozen clinical through Family History | Additive only; passed inside full pytest |

---

## M. Quality gates (fresh 2026-08-26)

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass (200 files) |
| `mypy app` | Pass (134 source files) |
| Full pytest | **403 passed** (equal to hardening; 374 at multi-org freeze) |
| Alembic | `current == heads == 20260814_0018` |
| Migration `0019` | Absent |
| `/api/v1/health/live` | 200 `{"status":"alive"}` |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage = ok |
| Secret scan | No `.env`, private keys, JWTs, credentials, DB secrets, runtime logs, or runtime volumes in the intended commit set |

---

## N. P0 / P1 / P2 / P3

| Severity | Item | Status |
|---|---|---|
| P0 | — | None |
| P1 unresolved | — | **None** |
| P2 | Inherited DENIED-audit rollback | Unchanged; not redesigned |
| P3 | Docker image lag | `:9100` new context routes 404 unauthenticated; existing `/api/v1/iam/users/me` 401; image not rebuilt |

Verdict: **PASS WITH P2** (no unresolved P0/P1).

---

## O. Exact files in this publication commit

Production:

- `backend/app/api/v1/deps.py`
- `backend/app/api/v1/iam.py`
- `backend/app/api/v1/organizations.py`
- `backend/app/modules/iam/application/shell_context.py`
- `backend/app/modules/iam/application/shell_schemas.py`
- `backend/app/modules/organization/infrastructure/repositories.py`

Tests:

- `backend/tests/unit/test_iam_shell_context_scope.py`
- `backend/tests/integration/test_iam_shell_context.py`
- `backend/tests/integration/test_iam_shell_context_hardening.py`

Docs:

- `docs/architecture/iam-shell-context-backend.md`
- `docs/gates/iam-shell-context-implementation-gate.md`
- `docs/gates/iam-shell-context-hardening-gate.md`
- `docs/gates/iam-shell-context-final-freeze.md` (this file)

Healthcare Web shell/IAM context **design** docs were already published on the parent freeze commit. No `apps/healthcare-web`. No Alembic revision.

---

## P. Push verification

Expected after push (no force):

- `HEAD == origin/main`
- working tree clean
- `iam-shell-context-frozen` peels to HEAD
- old freeze tags unchanged
- Alembic still `20260814_0018`; no `0019`

---

## Q. Explicitly not started

Healthcare Web frontend, OIDC browser integration, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, AI.

STOP after publish.
