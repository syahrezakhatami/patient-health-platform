# Product access and tenancy foundation — hardening gate

**Status:** COMPLETE  
**Frozen:** NO  
**Date:** 2026-08-26  
**Published parent:** `wave-2b-clinical-foundation-complete` / `b1606fe38dfaf4ee24d95775c07e77cb842c3736`  
**Family History freeze:** `wave-2b8-family-history-frozen` / `9a56c0893f8638c1a66d854ca61f137a6177ebf4` (unchanged)  
**Alembic:** `current == heads == 20260814_0018` (exactly one head)  
**Wave1PolicyPDP:** FROZEN (no production diff vs published parent)  
**Git commit/tag this gate:** none

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. Product Access & Tenancy Foundation is **not frozen**. This pass does not start Healthcare Web, Patient Mobile, Platform Admin Web, subscription, entitlement, billing, AI, scheduling, notifications, pharmacy, emergency, patient multi-org, or break-glass.

Authoritative design: `docs/architecture/product-access-tenancy-foundation-design.md`.  
Design approval: `docs/gates/product-access-tenancy-foundation-design-approval.md`.  
Implementation record: `docs/architecture/product-access-tenancy-foundation.md`.  
Implementation gate: `docs/gates/product-access-tenancy-foundation-implementation-gate.md`.

---

## A. Baseline

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD / published parent | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Tag | Annotated `wave-2b-clinical-foundation-complete` → same commit |
| Working tree | Dirty: uncommitted Product Access implementation + hardening + facility/org isolation resolution |
| Uncommitted implementation | **is the code being hardened**, not baseline corruption |
| Migrations `0001`–`0017` | Untouched vs published parent |
| Migration `0018` | Uncommitted; `down_revision = 20260814_0017` |
| `docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| Wave 2B.8 Family History | IMPLEMENTED + HARDENED + FROZEN |
| Wave 2B Native Clinical Foundation | CLOSED |
| Wave 2B.9 | Does not exist |
| Unrelated frontend / SaaS / AI | Not implemented |

Do **not** checkout or reset to `8d455b3` or `9a56c08`.

---

## B. Files added or changed during hardening

Hardening-only additions and contract-defined security fixes on top of the uncommitted implementation:

| Path | Change |
|---|---|
| `backend/tests/integration/test_product_access_tenancy_foundation_hardening.py` | New hardening suite |
| `backend/tests/unit/test_product_access_tenancy.py` | Dispatcher, catalog, mixed-audience, unknown-principal tests |
| `backend/tests/security/test_authentication.py` | Introspection deny reason now `principal_type_denied` |
| `backend/alembic/versions/20260814_0018_product_access_tenancy.py` | Binding immutability trigger/function (still `0018`, no `0019`) |
| `backend/app/modules/iam/infrastructure/jwt_oidc_validator.py` | Single distinct `aud` only; mypy-safe audience parse |
| `backend/app/modules/authorization/application/product_access_pdp.py` | Unknown/malformed principal deny-by-default |
| `backend/app/modules/patient_access/application/services.py` | `SELECT FOR UPDATE`; persist collision/RETIRED disable across 403 |
| `backend/app/modules/patient_access/infrastructure/repositories.py` | Account row locks (no Redis) |
| `docs/gates/product-access-tenancy-foundation-hardening-gate.md` | This gate |
| `backend/app/modules/authorization/application/facility_scope.py` | Central facility∈organization lookup (this resolution pass) |
| `backend/app/modules/authorization/application/authorize.py` | Apply tenant facility check after PDP allow; conceal mismatch as 404 |
| `backend/app/modules/organization/application/services.py` | Store `self._session` for `authorize()` |
| `backend/tests/integration/test_facility_organization_isolation.py` | Targeted empty-list / explicit-list / tamper / platform / patient tests |
| `backend/tests/unit/test_product_access_tenancy.py` | `facility_tenant_decision` and authorize-order unit tests |

`wave1_pdp.py` was not modified.

---

## C. Production defects found and fixed

| ID | Severity | Defect | Fix |
|---|---|---|---|
| H1 | **P1** | `app_dml` UPDATE could rebind `subject` or `patient_identity_id` to an arbitrary victim | Trigger `trg_patient_accounts_binding_immutable` / `prevent_patient_account_rebinding()`: subject/id/`created_at` immutable; identity may rebind only to canonical MPI survivor; `DISABLED → ACTIVE` forbidden; DELETE denied |
| H2 | **P1** | JWT `aud` arrays such as `["php-api","php-patient"]` could pass verification and pick a route class from `aud[0]` | Validator requires exactly one distinct non-empty audience string |
| H3 | **P1** | Collision disable (`Account A→X`, `Account B→Y`, merge `X→Y`) ran in the same session as the subsequent 403, so rollback left both rows `ACTIVE` and the survivor account usable indefinitely | `resolve_principal` commits after RETIRED/COLLISION disable, then returns `None` |
| H4 | P2 | Direct `pdp.evaluate` for `SYSTEM` / `AI_SERVICE` fell through to frozen Wave1 | `ProductAccessPDP` denies unknown principal types (`principal_type_denied`). `/api/v1/auth/context` is introspection-only (not PHI) and now reports this deny |
| H5 | **P1 integrity / contract** | Org-wide staff (`actor_facility_ids` empty) could create/update a same-org clinical/MPI/IAM resource while stamping a **foreign organization's** `facility_id` | Central `facility_tenant_decision` in `authorize()` after PDP allow: if `facility_id` is present, `facility.organization_id` must equal request/resource organization; mismatch/unknown → conceal 404 |

No break-glass, no new statuses, no patient multi-org, no Wave1PolicyPDP edit.

---

## D. ProductAccessPDP bypass review

Protected production path:

```
request → audience gate → principal loader → authorize() → ProductAccessPDP
         → Patient PDP | platform PHI deny | frozen Wave1PolicyPDP
```

- `default_pdp()` returns `ProductAccessPDP`.
- The only production `Wave1PolicyPDP()` instantiation is inside `product_access_pdp.py`.
- Clinical / MPI / IAM / organization routes take `CurrentPDP`.
- `authorize()` derives `PrincipalType.PATIENT` or `STAFF` from the loaded principal object, not from token claims.
- `has_platform_scope` visibility shortcuts in frozen clinical/MPI services run **after** authorize; they are unreachable when the wrapper denies PHI.
- Unknown / malformed principal: **deny by default**. No fall-through-to-staff.

**Result:** no production bypass that lets a platform principal reach clinical/MPI PHI by calling Wave1PolicyPDP directly.

---

## E. PLATFORM_ADMIN clinical / MPI deny

Intentional new contract. Historical PLATFORM_ADMIN clinical 200/201 was **not** restored.

Representative create / list / get / amend-or-update / terminal actions return **403** for:

Encounter, Clinical Note, Condition, Observation, Laboratory (order / specimen / result), Medication, Allergy, Consent, Immunization, Procedure, Medical Device, Adverse Event, Family History.

MPI PHI **403** for identity create/read, anonymous create, lookup, identifiers, identify, verify, reject, match, match review, merge, unmerge.

Staff `php-api` + `PLATFORM_ADMIN` → 403. Platform audience `php-platform` on clinical → **401**.

---

## F. Stale permission defense

Injecting `clinical.condition.create` and `mpi.identity.read` onto `PLATFORM_ADMIN` `role_permissions` still yields **403**. `ProductAccessPDP` (`iam.platform` + `clinical.*`/`mpi.*`) is the security boundary, not catalog deletion alone.

---

## G. Privilege escalation

`PLATFORM_ADMIN` cannot assign `CLINICIAN`, `IDENTITY_OFFICER`, `REGISTRAR`, `AUDITOR`, lowercase `clinician`, self-assign CLINICIAN, or assign CLINICIAN to another platform actor. No membership PATCH. Facility/identifier bootstrap remains tenant/`ORG_ADMIN`.

Allowed bootstrap (unchanged contract): organization create; `ORG_ADMIN` / `PLATFORM_ADMIN` assignment.

---

## H. Patient account schema

Live `patient_accounts`:

- UUID PK
- unique `subject`
- `patient_identity_id` → `patient_identities.id` `ON DELETE RESTRICT`
- CHECK `ACTIVE` \| `DISABLED`
- partial unique `uq_patient_accounts_active_identity` WHERE `status = 'ACTIVE'`
- indexes on identity
- no NIK, BPJS, demographics, or clinical payload

`app_dml`: SELECT / INSERT / UPDATE; DELETE and TRUNCATE denied.

Historical `DISABLED` rows may exist for the same identity. They cannot become competing controllers: reactivation is trigger-denied.

---

## I. Account-control invariant

| Case | Result |
|---|---|
| Two ACTIVE binds to the same identity | 409 |
| Same subject → different identity | 409 |
| Different subject → same ACTIVE identity | 409 |
| DISABLED account | `/me` 403; cannot resolve `PatientPrincipal` |
| Concurrent bind to one identity | one 200/201, one 409 |
| Concurrent SQL reactivation | both fail; row stays DISABLED |

Partial unique ACTIVE identity + immutable subject + no reactivation preserves the approved **one active authenticated controller per canonical person** at the database layer. Request-time merge rebind is survivor-only.

---

## J. Binding immutability / SQL bypass

Direct SQL:

- `UPDATE subject` → denied (`subject is immutable`)
- `UPDATE patient_identity_id` to a non-survivor → denied
- `DELETE` / `TRUNCATE` → denied
- `ACTIVE → DISABLED` → allowed
- `DISABLED → ACTIVE` → denied

Canonical MPI merge rebind through the service remains allowed by the trigger (walk `surviving_identity_id`, max 8 hops). That is **not** generic rebinding permission.

---

## K. Token audiences and principal forgery

Approved audiences: `php-api`, `php-platform`, `php-patient`.

| Case | Result |
|---|---|
| Patient → staff/clinical API | 401 |
| Patient → platform/org API | 401 |
| Staff → patient API | 401 |
| Platform audience → patient API | 401 |
| Platform audience → clinical API | 401 |
| Mixed `aud` array | 401 |
| Missing / wrong / malformed `aud` | 401 |
| Fake `patient_identity_id` claim | ignored; persisted binding wins |
| `principal_type=PATIENT` on a staff token | ignored; still staff |
| Staff/platform subject + patient audience | 403 (no patient account) |
| Unknown / disabled / empty sub | 401/403 |

Cross-client token reuse fails.

---

## L. Self-access, tenant, facility, PATIENT_ACCESS

- Patient A → A: allow when purpose + org + permission pass.
- Patient A → B / random UUID / other-org: **404**, no existence leak.
- Hospital A staff ↛ Hospital/Clinic B: deny/404.
- Patient `X-Organization-Id` tamper: 404, no authority expansion.
- Platform + org header ≠ tenant clinician (clinical 403).
- Empty `actor_facility_ids`: org-wide, not global. Same-org facility header works. Foreign facility UUID does **not** grant foreign-org patient access. Same-org write with a foreign `facility_id` is now **404 concealed** (see FACILITY / ORGANIZATION ISOLATION RESOLUTION). `wave1_pdp.py` remains frozen and is not the enforcement point.
- `PATIENT_ACCESS` is context: missing/unknown 422; wrong purpose 403; wrong patient/org 404; self + org + `patient.*` allow.
- Patient catalog: `patient.account.read`, `patient.record.read` only. No `clinical.*`, `mpi.*`, `iam.platform`, or org-admin permissions. No prefix/wildcard grant into staff namespaces.

---

## M. MPI ACTIVE / ANONYMOUS / RETIRED / merge

- ACTIVE identity: bind, canonical self, same-org policy, isolation.
- ANONYMOUS: not eligible for patient account; emergency clinical encounter behavior unchanged.
- RETIRED: cannot continue as self-access; 403, no leak; account disable persisted.
- Unique merge `Account A → X`, `X → Y`: account remains usable; canonical becomes Y; historical `patient_identity_id` on clinical rows is **not** rewritten; cluster-aware `record-access` includes X; no duplicate facts; no cross-org escalation.

---

## N. Merge account collision

Start: `Account A → X` ACTIVE, `Account B → Y` ACTIVE. MPI merge `X → Y`.

On the next resolve of the merged-source account: both accounts are disabled in one transaction and **committed** before the 403. Neither subject remains an active controller of Y. No Patient A → Patient B takeover. Cluster expansion is not used to hide dual control.

If the survivor account is used **before** the merged-source account resolves, that survivor remains the sole working controller until collision disable runs. That window is request-time (approved “disable on collision”), not a second independent controller of a new person.

Reverse-direction unique merge (one account) rebinds to the survivor.

---

## O. Concurrency

PostgreSQL `SELECT FOR UPDATE` on account/identity rows. Redis is not a lock.

Covered: concurrent bind to one identity; concurrent SQL reactivation; unique subject/identity constraints. Merge vs bind: merged identity cannot bind (`409`).

Final database state preserves a single authorized ACTIVE controller.

---

## P. Patient API surface

`/api/v1/patient`: `POST /accounts`, `GET /me`, `GET /record-access` only.

No arbitrary search, UUID listing, NIK/BPJS lookup, full history aggregate, `/api/v2`, or `/fhir`.

---

## Q. Audit, leakage, clinical provenance

Unauthorized bodies do not reveal NIK, BPJS, tokens, SQL, or stack traces. Cross-patient/org uses 404 concealment.

Security events: `PATIENT_ACCOUNT_BOUND`, `PATIENT_ACCOUNT_DISABLED` (reason `COLLISION` / `RETIRED`). No tokens/NIK/BPJS in those events.

Access operations (bind, `/me`, record-access authorize, platform PHI deny) create **zero** `clinical_provenances` rows.

Inherited **P2**: DENIED-audit rollback — platform clinical 403 still inserts 0 `DENIED` `audit_events` rows. Not redesigned.

---

## R. Migration `0018` and catalog

`0017 → 0018` works. Cycle `0018 → 0017 → 0018` restores:

- `patient_accounts` + immutability trigger
- `patient.account.read`, `patient.record.read`
- `PLATFORM_ADMIN` `clinical.*` = 0 and `mpi.*` = 0
- exactly one Alembic head `20260814_0018`

After re-upgrade, `scripts/grant_dev_privileges.sql` was re-applied (inherited P3: grants outside Alembic). Live `app_dml` on `patient_accounts`: INSERT/SELECT/UPDATE only.

No dangling `role_permissions`. No duplicate permission codes. No `patient.*` assigned to staff/platform roles.

---

## S. Frozen clinical regression

Full pytest includes Encounter through Family History. Lifecycle, provenance, audit, immutability, and concurrency semantics remain frozen.

**Only intentional authorization change:** `PLATFORM_ADMIN` clinical/MPI access is **403**.

CLINICIAN / ORG_ADMIN / REGISTRAR / IDENTITY_OFFICER established behavior retained.

---

## T. Quality gates

| Check | Result |
|---|---|
| `ruff check app tests` | Pass (0 issues) |
| `ruff format --check app tests` | Pass (174 files) |
| `mypy app` | Pass (118 source files) |
| `pytest` | **326 passed** |
| Alembic | `current == heads == 20260814_0018` (one head) |
| `/api/v1/health/live` | 200 `{"status":"alive"}` |
| `/api/v1/health/ready` | 200; postgres=ok, redis=ok, object_storage=ok |
| Secret scan | Clean (no private keys, `AKIA…`, or credential files in this pass) |

---

## U. Docker image

Compose untouched. Image **not** rebuilt.

`:9100` `GET /api/v1/patient/me` → **404** because the running image predates Product Access.

**P3 DOCKER IMAGE LAG.**

---

## FACILITY / ORGANIZATION ISOLATION RESOLUTION

Independent analysis of the leftover finding. Not carried forward as unreviewed P2. No freeze document. No commit / tag / push. No migration `0019`. `wave1_pdp.py` untouched (SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd`).

### Original finding

> Wave1 empty facility list does not reject a foreign facility UUID on a same-org write.

Prior hardening pass parked this as inherited P2 because `wave1_pdp.py` is frozen. This pass reproduced it and applied the **already approved** tenant/facility contract without editing Wave1.

### Reproduction

Setup: Organization A / Facility A1; Organization B / Facility B1. Authorized CLINICIAN in A with `actor_facility_ids = empty` (org-wide membership).

`POST /api/v1/clinical/conditions` with `X-Organization-Id = A` and `X-Facility-Id = B1` **returned 200** before the fix. The row was still `organization_id = A` (no Hospital B PHI read/write). The stamped `facility_id` was Hospital B's UUID.

After the fix the same request returns **404** `"Resource not found"` (conceal). Same-org A1/A2 and `facility_id = null` remain allowed.

Direct schema: `conditions.organization_id` and `conditions.facility_id` are independent FKs. A composite org+facility constraint is **not** present. Service/`authorize()` is the production gate.

### Affected surface

| Surface | Accepts facility | Before fix (empty `actor_facility_ids`) | After fix |
|---|---|---|---|
| Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, Medical Device, Adverse Event, Family History | `X-Facility-Id` on all `/api/v1/clinical/*` routes | Same-org write could persist foreign `facility_id` | Deny/conceal 404 if facility org ≠ request org |
| MPI identities / identifiers / match / merge / unmerge | `X-Facility-Id` on `/api/v1/mpi/*` | Same hole on writes that persist header facility | Same central deny |
| IAM `POST /iam/memberships` | Body `facility_id` | Wave1 empty list allowed; later 422 only if service check ran | 404 conceal at `authorize()` before the 422 |
| Organization facility create | Path org only; no resource `facility_id` | N/A | Unchanged |
| Patient `/accounts`, `/me`, `/record-access` | No `X-Facility-Id` | Org header tamper cannot become another tenant's PHI | Unchanged; extra facility header ignored |
| Direct repository INSERT | Independent FKs | DB would accept org A + facility B | Unchanged (P3 schema); API path blocked |

Not every path was independently exploitable: a **non-empty** `actor_facility_ids` allow-list already denied unlisted/foreign facilities in frozen Wave1 (403 `facility_scope_denied`). The hole was **empty list + foreign UUID**.

### Root cause

Combination, not a new architecture gap:

- **A + E.** Frozen `Wave1PolicyPDP._facility_allowed`: empty `actor_facility_ids` → `True` with no DB lookup of `facility.organization_id`. The Wave1 docstring already says empty list is org-bounded; Wave1 cannot verify that without a facility row.
- **B.** Clinical/MPI/IAM services passed header/body `facility_id` into `authorize()` then persisted it. Only IAM `assign_membership` had a later org-match 422.
- **F.** Frozen tables have separate FKs to `organizations.id` and `facilities.id`. No composite constraint. **No 0019**; rewriting frozen tables is out of scope.

**Not modified:** Wave1PolicyPDP. Tenant enforcement lives in `authorize()` after PDP evaluate.

### Severity

| Impact | Result |
|---|---|
| Cross-tenant PHI read | **No** (foreign org header still membership-deny/404) |
| Cross-tenant PHI write | **No** (resource `organization_id` stayed A) |
| Foreign facility metadata disclosure | Avoided by **404 conceal** (unknown UUID and foreign UUID look the same) |
| Resource misattribution | **Yes** — `facility_id` could name another tenant's facility |
| Audit/provenance facility attribution | **Yes** |
| Authorization bypass / patient-mobile leakage / platform clinical restore | **No** |
| Confidentiality vs integrity | **Integrity and contract**, not demonstrated confidentiality PHI access |

Not left as automatic P2. Reproducible approved-contract violation on mutation. Classified **P1 integrity / contract** and **fixed**. Not a confidentiality P1.

**Reclassification:** RESOLVED INHERITED SECURITY DEFECT

### Fix

Central reusable check: `facility_tenant_decision(session, facility_id=, organization_id=)` in `facility_scope.py`, invoked from `authorize()` **only when the PDP already allowed**.

Invariant: if `facility_id` is not null, `facility.organization_id ==` effective request/resource `organization_id` before mutation succeeds. `facility_id is None` skips the lookup (optional facility preserved).

Wrong-organization / unknown facility: conceal **404** `"Resource not found"` (`facility_organization_mismatch`, `facility_not_found`).

PDP deny (including `PLATFORM_ADMIN` PHI) does **not** run the lookup and remains **403**. Facility validation cannot restore platform clinical access.

### Database defense

Service/`authorize()` is **authoritative**. Composite FK `(facility_id, organization_id) → facilities(id, organization_id)` would require frozen-table redesign and migration `0019`. Not done. Residual **P3**: DB still accepts a mismatched pair if a caller bypasses the API.

### Files changed (this resolution)

- `backend/app/modules/authorization/application/facility_scope.py` (new)
- `backend/app/modules/authorization/application/authorize.py`
- `backend/app/modules/organization/application/services.py` (`self._session`)
- Clinical / MPI / IAM / organization / patient_access `authorize(..., session=self._session)` call sites (already required by the shared helper)
- `backend/tests/integration/test_facility_organization_isolation.py` (new)
- `backend/tests/integration/test_product_access_tenancy_foundation_hardening.py` (foreign facility now 404)
- `backend/tests/unit/test_product_access_tenancy.py`
- this gate document

### Tests

1. Empty list + same-org A1 / A2 → allow
2. Empty list + foreign B1 → 404 (Condition, Encounter, Allergy, Consent, MPI identity)
3. Explicit list + listed A1 → allow
4. Explicit list + same-org unlisted A2 → 403 (Wave1 allow-list unchanged)
5. Explicit list + foreign B1 → 403
6. `X-Organization-Id=A` + `facility_id=B1` → 404; `X-Organization-Id=B` + `facility_id=B1` → 403/404 (no membership)
7. `facility_id` null remains valid on Condition
8. `PLATFORM_ADMIN` + org A + facility A/B + clinical mutation → 403
9. Patient org/facility tamper → no cross-org record-access; clinical audience 401
10. IAM membership foreign facility → 404 conceal

Previous Product Access P1s remain covered by the hardening suite (SQL rebind, mixed `aud`, merge-collision commit, unknown principal).

### Final invariant

Empty `actor_facility_ids` means all facilities **inside the actor's organization**. It never means an arbitrary global facility UUID. `resource.organization_id` must be consistent with `facility.organization_id` when `facility_id` is present.

### Regression results

- Frozen clinical tests: pass (only invalid foreign-facility writes changed)
- Product Access implementation + hardening: pass
- `pytest` **326 passed**
- Wave1 checksum unchanged

---

## V. P0 / P1 / P2 / P3

- **P0:** none
- **P1 (found and fixed):** SQL rebinding; mixed audience; collision disable rollback; **foreign-facility stamp on same-org write (integrity/contract, H5)**
- **P2 (inherited):** DENIED audit rollback; historical clinical `patient_identity_id` non-rewrite (cluster expansion)
- **P3 (inherited):** grants outside Alembic; nullable clinical `provenance_id`; Docker image lag; independent org/facility FKs on frozen clinical tables (API/`authorize()` is the gate; no `0019`)

No security issue was downgraded to finish the pass. The empty-list foreign-facility finding was **fixed**, not re-labeled P2.

---

## W. Verdict

PRODUCT ACCESS & TENANCY FOUNDATION = IMPLEMENTED  

PRODUCT ACCESS & TENANCY FOUNDATION HARDENING = COMPLETE  

FACILITY / ORGANIZATION ISOLATION = PASS  

PRODUCT ACCESS & TENANCY FOUNDATION = NOT FROZEN  

NO COMMIT  
NO TAG  
NO PUSH  
NO MIGRATION `0019`  
NO WAVE1POLICYPDP EDIT  
NO FAMILY HISTORY RE-HARDENING  
NO HEALTHCARE WEB / PATIENT MOBILE / PLATFORM ADMIN WEB / SUBSCRIPTION / AI
