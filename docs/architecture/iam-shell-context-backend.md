# IAM shell context backend — implementation

**Date:** 2026-08-26  
**Kind:** Implementation (not freeze, not hardening)  
**Status:** IMPLEMENTED  
**Hardening:** NOT STARTED  
**Frozen:** NO  
**Baseline:** `product-access-multi-org-context-isolation-frozen` / `70baee1bd24969d29d2b5f7eeda0240fb8bde877`  
**Parent:** `clinical-read-core-frozen` / `5d124de2c80bc17127fc17e9f6a730828c13a63a`  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** NOT CREATED  
**Wave1PolicyPDP:** FROZEN — file not edited  
**ProductAccessPDP:** FROZEN — file not edited (`default_pdp()`)

This document records the Healthcare Web **staff shell IAM/context APIs**. It does not implement Healthcare Web, Patient Mobile, Platform Admin Web, scheduling, notifications, pharmacy, subscription, or AI.

Authoritative design: `docs/architecture/healthcare-web-shell-iam-context-design.md`.  
Companion gate: `docs/gates/iam-shell-context-implementation-gate.md`.

---

## Baseline

Verified before production-code changes and still true of published `main`:

| Item | Value |
|---|---|
| HEAD | `70baee1bd24969d29d2b5f7eeda0240fb8bde877` |
| Tag | Annotated `product-access-multi-org-context-isolation-frozen` peels to HEAD |
| Parent | `5d124de2c80bc17127fc17e9f6a730828c13a63a` |
| Branch | `main` == `origin/main` |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Does not exist |
| `Wave1PolicyPDP` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `ProductAccessPDP` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Clinical Read Core | Untouched |
| `backend/docker-compose.yml` | Untouched |
| Production rate limit | `120` req/min (unchanged) |

Working tree after this pass is **uncommitted** (no commit, tag, or push).

---

## Route surface (GET only)

| Method | Path | `X-Organization-Id` | Audience |
|---|---|---|---|
| GET | `/api/v1/iam/me/organizations` | not required; ignored if sent | `php-api` |
| GET | `/api/v1/iam/me/context` | required | `php-api` |
| GET | `/api/v1/organizations/{organization_id}/facilities/accessible` | required; must equal path id | `php-api` |

No POST/PUT/PATCH/DELETE. No extra shell routes. `GET /api/v1/iam/users/me` is unchanged.

Staff routers still allow `php-api` or `php-platform` at the IAM/org router level. These three routes add `require_staff_audience` so `php-platform` and `php-patient` are **401**.

---

## DTOs

Pydantic, `extra=forbid`. No ORM leakage.

`StaffSessionUserDTO`: `id`, `subject`, `display_name`.

`AccessibleOrganizationDTO`: `organization_id`, `name`, `code`, `organization_type`, `status`, `role_codes` (this org only).

`StaffOrganizationsResponse`: `provisioned`, `user | None`, `organizations`.

`FacilityScopeKind`: `ALL_IN_ORGANIZATION` | `EXPLICIT`.

`AccessibleFacilityDTO`: `id`, `name`, `code`, `facility_type`, `status`.

`StaffContextResponse`: `provisioned`, `user`, `organization`, `role_codes`, `effective_permissions`, `facility_scope`, `work_facility_required`. **Does not** include `accessible_facilities` (loaded via the facilities route).

`AccessibleFacilitiesResponse`: `organization_id`, `facility_scope`, `facilities`.

Never returned: `role_id`, `revoked_at`, JWT, passwords, other users, foreign orgs, patient identifiers, PDP reasons, `matching_value`, PHI.

---

## Staff audience

Accept: `php-api`.

Reject: `php-patient`, `php-platform` (401). `PatientPrincipal` cannot use these routes.

Platform operators must not use these as Healthcare Web context APIs. A platform-null membership is not a tenant organization entry.

---

## Organizations

`GET /iam/me/organizations` loads the **unscoped** principal (`IamRepository.load_principal`, ACTIVE memberships only). Platform memberships (`organization_id is None`) are excluded from the list.

- Provisioned staff with tenant orgs: those orgs only, sorted by `(name.lower(), code, id)`.
- Platform-only: `provisioned: true`, `organizations: []` (not a global directory).
- Unprovisioned: `provisioned: false`, `user: null`, `organizations: []` (same shape as `/users/me`).
- Revoked memberships are absent (`load_principal` filters ACTIVE).
- Inactive **organizations** remain listed with `status=INACTIVE` so the UI can omit/disable; they are not auto-selected.

Authorization: self-read, matching `/users/me`. No `iam.membership.manage`. No `X-Purpose`.

---

## Context

`GET /iam/me/context` requires `X-Organization-Id`.

Flow: authenticated principal → `Principal.for_organization(selected_org)` → DTO.

Unprovisioned → 403. No tenant membership in the selected org, unknown org, or foreign org → **404 conceal**. Missing/invalid header → 422.

`effective_permissions` and `role_codes` are the **tenant** memberships of the selected org only (see below). `facility_scope` uses the same frozen same-org facility rule as `Principal.for_organization`. `work_facility_required` is true iff `EXPLICIT` and at least one explicit membership facility id.

Context does not return the facility list.

---

## Effective-permission derivation

Single source of truth for narrowing: frozen `Principal.for_organization(org_id)`.

Healthcare Web DTO permissions additionally **drop platform catalog** even though `for_organization` keeps platform-null memberships internally:

```
tenant memberships = memberships where organization_id is not None
effective_permissions = sorted unique union of permissions_by_role_id for those memberships
role_codes = sorted unique tenant role codes
```

A CLINICIAN / B ORG_ADMIN: context A is clinician only; context B is org-admin only. No union.

Hybrid platform + A ORG_ADMIN: organizations list is A only; context A is ORG_ADMIN tenant permissions only. `iam.platform` and other platform-bootstrap codes are not tenant navigation authority.

Deterministic: sorted, de-duplicated.

---

## Facility scope discriminator

| Memberships in selected org | `facility_scope` | Accessible facilities |
|---|---|---|
| Any `facility_id IS NULL` | `ALL_IN_ORGANIZATION` | All **ACTIVE** facilities in that org |
| Only explicit ids | `EXPLICIT` | Those ids, **ACTIVE**, that org only |
| Same-org A1 + A2 explicit | `EXPLICIT` `{A1,A2}` | Frozen same-org union |
| Same-org mix with one NULL | `ALL_IN_ORGANIZATION` | Frozen org-wide empty `facility_ids` on the principal |

Never encode org-wide as `facilities: []` meaning none. `ALL_IN_ORGANIZATION` with zero ACTIVE facilities is an empty list **with** that discriminator.

Existing `Facility.status` is `ACTIVE` | `INACTIVE`. Shell selection returns **ACTIVE** only. No new status model. `list_facilities(organization_id)` is unchanged (unordered, all statuses). Shell uses `list_facilities_for_shell` (org filter, ACTIVE, optional id filter, `ORDER BY name, id`).

---

## Accessible facilities

Path organization id is **not** authority. Header must equal path or the response is 404 (no foreign directory). Membership in that org is required (else 404). Then `org.facility.read` via existing `authorize` + ProductAccessPDP on the **scoped** principal.

Never returns another organization's facilities.

---

## Multi-org isolation

Selected organization is request context, not a grant. `get_principal` already projects when the header is present. Shell context/facilities call `for_organization` again (idempotent). Cross-org permission/facility union is not recomputed.

Work-context facility (`X-Facility-Id` on later writes) is not this DTO. Chart facility filter remains a Clinical Read Core query param and is not returned here.

---

## Platform / patient tokens

| Caller | Organizations | Context / facilities |
|---|---|---|
| Staff `php-api` with tenant memberships | Those tenants | Selected-org DTO |
| Platform-only `php-api` | Empty list | 404 (no tenant membership) |
| Hybrid platform + tenant `php-api` | Tenant orgs only | Tenant permissions only |
| `php-patient` | 401 | 401 |
| `php-platform` | 401 | 401 |

---

## Error contract

| Status | When |
|---|---|
| 401 | Missing/wrong staff token; `php-patient`; `php-platform` |
| 403 | Valid token, unprovisioned user |
| 404 | Unknown/foreign org, no membership, header≠path, revoked tenant |
| 422 | Missing/invalid `X-Organization-Id` on routes that require it |

Messages do not leak membership internals.

---

## Purpose

IAM bootstrap GETs are **purpose-exempt** (same as `/iam/users/me`). Do not send `X-Purpose`. No new purpose catalog value.

`org.facility.read` denial audit, if any, uses existing catalog `ADMINISTRATION` inside `authorize`. Successful reads are not purpose-gated.

---

## Audit / provenance

`/iam/users/me` is not audited on success. Shell organization and context reads do not call `authorize` and do not write audit rows.

Accessible facilities call `authorize` only so denials use the existing DENIED-audit path. Success is not audited.

Zero clinical provenance. These routes do not touch clinical tables.

---

## Migration

No schema change. Existing `users`, `organization_memberships`, `roles`, `permissions`, `organizations`, `facilities`. **No 0019.**

---

## Performance / cache

Organizations: one principal load + one `IN` query for org rows. Facilities: one org-filtered SQL query. Permissions come from the already-loaded principal map (no per-permission query). No Redis cache.

---

## Tests

Unit: `backend/tests/unit/test_iam_shell_context_scope.py`.

Integration: `backend/tests/integration/test_iam_shell_context.py` (implementation only; no hardening-gate file).

Covers single-org, multi-org and three-org isolation, revoked/no membership, explicit / all-in-org / same-org union, cross-org and header/path mismatch, platform-only, hybrid, patient/platform token 401, staff allowed, deterministic sort, no PHI, no provenance, Clinical Read Core chart smoke, unchanged `/iam/users/me`.

Frozen multi-org isolation, Product Access, Clinical Read Core, and full clinical suites run via full `pytest`.

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
