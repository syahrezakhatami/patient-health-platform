# Product access and tenancy foundation — implementation

**Date:** 2026-08-26  
**Kind:** Implementation (not freeze, not hardening)  
**Status:** IMPLEMENTED  
**Hardening:** NOT STARTED  
**Frozen:** NO  
**Baseline:** `wave-2b-clinical-foundation-complete` / `b1606fe38dfaf4ee24d95775c07e77cb842c3736`  
**Alembic:** `current == heads == 20260814_0018`  
**Wave1PolicyPDP:** FROZEN — file not edited

This document records what was implemented. Authoritative design remains `docs/architecture/product-access-tenancy-foundation-design.md`. This pass does not start Healthcare Web, Patient Mobile, Platform Admin Web, subscription, entitlement, AI, scheduling, notifications, pharmacy, or emergency.

Companion gate: `docs/gates/product-access-tenancy-foundation-implementation-gate.md`.

---

## Baseline

Verified before production-code changes and still true of published `main`:

| Item | Value |
|---|---|
| HEAD | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Tag | `wave-2b-clinical-foundation-complete` |
| Branch | `main` == `origin/main` |
| Wave 2B | CLOSED |
| Wave 2B.9 | MUST NOT EXIST — not created |
| Migrations `0001`–`0017` | Untouched |
| `docker-compose.yml` | Untouched |
| `Wave1PolicyPDP` | Untouched |

Working tree after this pass is **uncommitted** (no commit, tag, or push).

---

## Migration `20260814_0018`

Exactly one forward migration after `20260814_0017`. Single Alembic head.

### Schema: `patient_accounts`

| Column | Contract |
|---|---|
| `id` | UUID PK |
| `subject` | IdP `sub`, UNIQUE NOT NULL |
| `patient_identity_id` | UUID NOT NULL → `patient_identities.id` `ON DELETE RESTRICT` |
| `status` | `ACTIVE` \| `DISABLED` |
| `created_at` / `updated_at` | timestamps |

Constraints/indexes:

- unique `subject`
- partial unique `uq_patient_accounts_active_identity` on `patient_identity_id` WHERE `status = 'ACTIVE'`
- no NIK, BPJS, phone, email, or MRN columns
- no tenant table

### Catalog

Insert:

- `patient.account.read`
- `patient.record.read`

`PLATFORM_ADMIN` `role_permissions` retained only:

- `iam.platform`
- `iam.user.read`
- `iam.user.provision`
- `iam.membership.manage`
- `org.organization.create`
- `org.organization.read`

All other `PLATFORM_ADMIN` grants, including `clinical.*` and `mpi.*`, are deleted by this forward migration. Seed history in `0001`–`0017` is not rewritten.

No subscription, entitlement, plan, billing, AI, scheduling, notification, pharmacy, frontend-metadata, or hospital-group tables.

After upgrade, `scripts/grant_dev_privileges.sql` must be re-run. `app_dml` on `patient_accounts`: INSERT/SELECT/UPDATE; DELETE/TRUNCATE revoked.

---

## Organization as MVP tenant

No `tenants` / `tenant_accounts` / `tenant_organizations` table. Canonical tenant boundary remains `organization_id`. Frozen clinical `organization_id` semantics are unchanged. Empty `actor_facility_ids` still means all authorized facilities **in the actor's organization**, never global.

---

## PLATFORM_ADMIN before / after

| | Before (Wave 2B closeout) | After this pass |
|---|---|---|
| Role code | `PLATFORM_ADMIN` | `PLATFORM_ADMIN` (no `PLATFORM_OPERATOR`) |
| Catalog | `ROLE_PERMISSIONS[PLATFORM_ADMIN] = CATALOG_PERMISSIONS` | `PLATFORM_ADMIN_PERMISSIONS` (platform/org bootstrap only) |
| Clinical create/read/amend/EIE | Allowed (201/200 in tests) | **403** |
| MPI PHI browse | Allowed | **403** |
| Organization create | Allowed | Allowed |
| Facility / org-identifier create | Allowed | **403** (tenant `ORG_ADMIN`) |
| Assign `CLINICIAN` | Allowed via `iam.membership.manage` | **403** (bootstrap roles only: `PLATFORM_ADMIN`, `ORG_ADMIN`) |

Principle: **platform ownership ≠ automatic clinical access.** No break-glass in this pass.

Runtime bootstrap limit is in `IamService.assign_membership`: if the actor has `iam.platform`, assignable roles are `PLATFORM_BOOTSTRAP_ROLES` only.

---

## Authorize dispatcher

`ProductAccessPDP` wraps frozen `Wave1PolicyPDP`. `default_pdp()` now returns the wrapper. Clinical/MPI/IAM services are not given role-name checks.

```
authorize(principal, action, resource_context)
├─ PATIENT → PatientSelfAccessPDP
├─ action clinical.* or mpi.* AND iam.platform ∈ scopes
│     → DENY platform_clinical_forbidden (do not call Wave1PolicyPDP)
└─ else → Wave1PolicyPDP.evaluate (frozen)
```

`Wave1PolicyPDP` unit tests that call the frozen class directly still observe `platform_scope` allow when clinical is in scopes. HTTP/integration uses the wrapper.

Implementation note: PHI deny fires whenever `iam.platform` is in scopes, not only when the actor is org-less. Dual-hat staff+operator remains deferred. This matches the approved security principle and the implementation contract (`PLATFORM_ADMIN` + `iam.platform` + clinical/MPI → 403).

Concealment: patient identity mismatch raises `NotFoundError` (404), not 403.

---

## PatientPrincipal

Distinct from IAM `users`. `PrincipalType.PATIENT` is authoritative. Not faked as `CLINICIAN` / `REGISTRAR` / `ORG_ADMIN` / `PLATFORM_ADMIN`.

Minimum context:

- account id + `subject`
- bound `patient_identity_id`
- request-time `canonical_patient_identity_id`
- cluster identity ids for historical visibility
- `patient.*` permissions only
- organization from `X-Organization-Id` (not a token claim)

Raw NIK/BPJS are not placed in authorization context.

---

## Authentication subject → binding

```
token.sub
  → patient_accounts lookup
  → patient_identity_id
  → canonical MPI walk
  → authorize
```

A `patient_identity_id` token claim is ignored. Callers cannot swap UUIDs by editing the token.

---

## Account eligibility and MPI merge

| Identity status | Bind | Login / self-access |
|---|---|---|
| ACTIVE | Allow (1:1) | Allow |
| ANONYMOUS | 409 `identity_not_eligible` | N/A |
| RETIRED | 409 | Deny; bound account disabled |
| MERGED | 409 (cannot bind as standalone) | Resolve to survivor |
| Unknown | 404 | 404 |

Merge: frozen clinical rows are **not** rewritten. Request-time canonical walk (max 8 hops). Unique survivor → rebind. Survivor already bound to another ACTIVE account → disable both (`PATIENT_ACCOUNT_DISABLED`, reason `COLLISION`). Record-access expands `{canonical} ∪ cluster (ACTIVE + MERGED_IN)`.

Identity-proofing UX is **not** implemented (approved deferred). Bind still requires ACTIVE + 1:1 UUID FK.

---

## Patient Self-Access PDP

Patients are not evaluated by `Wave1PolicyPDP`.

Allow only when:

- principal type is PATIENT
- required `patient.*` permission is present
- purpose == `PATIENT_ACCESS`
- requested identity is canonical (account.read) or in `{canonical} ∪ cluster` (record.read)
- organization exists and the identity cluster is visible in that org (provenance/identifier org match)

Patient A cannot access Patient B. UUID guessing returns 404. Wrong org returns 404. Purpose never grants access by itself.

`GET /api/v1/patient/record-access` is a **foundation** check (canonical + cluster ids). It is **not** the patient medical-record read model. No `patient_histories` table. No duplicate clinical tables. Patient reads do **not** write `clinical_provenances`.

---

## Patient permissions

| Code | Use |
|---|---|
| `patient.account.read` | Own account metadata (`GET /me`) |
| `patient.record.read` | Own same-org record-access foundation |

Patients do **not** receive `clinical.*` or `mpi.*`.

---

## PATIENT_ACCESS purpose

Existing purpose catalog value. Required on `/api/v1/patient/*`. Missing/unknown → 422. Wrong purpose → 403. Correct purpose + wrong patient → 404. Purpose is context/audit, not a grant.

---

## Token audiences

| Client | Audience setting | Default |
|---|---|---|
| Healthcare staff | `AUTH_AUDIENCE` | `php-api` |
| Platform operator | `AUTH_PLATFORM_AUDIENCE` | `php-platform` |
| Patient | `AUTH_PATIENT_AUDIENCE` | `php-patient` |

JWT decode accepts all three. Route class rejects the wrong audience with 401 `"Token audience is invalid"`.

- `/api/v1/clinical`, `/api/v1/mpi` → staff only
- `/api/v1/iam`, `/api/v1/organizations` → staff or platform
- `/api/v1/patient` → patient only

No new IdP. No OAuth product UI.

---

## Tenant isolation

Hospital A staff → Hospital B: DENY/404 (unchanged).  
Clinic B staff → Hospital A: DENY/404 (unchanged).  
Patient A → Patient B: 404.  
Patient A + wrong org: 404.  
Patient cross-org aggregation: **not approved**, not implemented.

---

## Patient HTTP API

Namespace `/api/v1/patient`:

| Method | Path | Role |
|---|---|---|
| POST | `/accounts` | Bind current patient `sub` to MPI UUID |
| GET | `/me` | Account + canonical id |
| GET | `/record-access` | Same-org self/cluster visibility foundation |

No `/api/v2`. No `/fhir`. No `/api/v1/platform` (not required for this pass).

---

## Audit

Added:

- `PATIENT_ACCOUNT_BOUND` (account id, identity UUID, org; no NIK/BPJS/token)
- `PATIENT_ACCOUNT_DISABLED` (reason `RETIRED` or `COLLISION`)

Denied authorization still uses existing `authorize()` DENIED audit. Inherited P2: DENIED rows roll back with `ForbiddenError` / `NotFoundError`.

---

## MPI integration

Additive only: `MpiRepository.list_cluster_identity_ids`. Matching, merge, unmerge, and identity normalization are unchanged. MPI services still do not contain `if role == PLATFORM_ADMIN`. PHI is blocked by the dispatcher before service visibility shortcuts.

---

## Quality

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass |
| `mypy app` | Pass (117 source files) |
| `pytest` | **278 passed** |
| Alembic | `current == heads == 20260814_0018` (one head) |
| `/api/v1/health/live` | 200 |
| `/api/v1/health/ready` | 200 (`postgres=ok`, `redis=ok`, `object_storage=ok`) |
| Secret scan | Clean (no `.env`, keys, or credentials in git) |

---

## Docker image state

`docker-compose.yml` unchanged. Ports remain 9100 / 5433 / 6380 / 9101. Image was **not** rebuilt. Live `:9100` health is 200; `GET /api/v1/patient/me` on that image returns **404** because the running image does not contain this pass. Inherited **P3 image lag**.

---

## Findings

| Severity | Item | Change this pass? |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rollback with request transaction | Inherited; not redesigned |
| P2 | Historical clinical `patient_identity_id` non-rewrite after MPI merge | Inherited; patient path uses canonical + cluster expansion |
| P2 | Same-org UUID read for staff | Inherited; not used as a patient multi-org grant |
| P3 | `app_dml` grants outside Alembic | Inherited; grant script updated for `patient_accounts` |
| P3 | Nullable clinical `provenance_id` at DB vs service | Inherited |
| P3 | Intentionally allowed duplicate clinical facts | Inherited |
| P3 | Docker image lag on `:9100` | Inherited; confirmed for new `/patient` routes |

---

## Contract deviations

None that change the approved security model.

Documented implementation notes (not redesigns):

1. Identity-proofing UX is deferred; bind still enforces ACTIVE + 1:1 UUID.
2. PHI wrapper denies all `clinical.*` / `mpi.*` when `iam.platform` is present (stricter than “org-less only”; dual-hat deferred).
3. No `/api/v1/platform` routes (not required).
4. `GET /record-access` is not a medical-record aggregation.

---

## Forbidden scope confirmation

Healthcare Web, Patient Mobile, Platform Admin Web, patient medical-record read model, subscription/entitlement/billing, AI, scheduling, notifications, pharmacy, emergency, hospital groups, patient multi-org PDP, break-glass, FHIR, `/api/v2`, Wave 2B.9: **not started / not created**.
