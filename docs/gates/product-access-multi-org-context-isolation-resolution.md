# Product Access multi-organization context isolation — resolution

**Date:** 2026-08-26  
**Kind:** Security verification / resolution (not a freeze)  
**Verdict:** Defect reproduced and fixed under the existing organization-isolation contract  

| Flag | Value |
|---|---|
| MULTI-ORG PERMISSION ISOLATION | FIXED |
| MULTI-ORG FACILITY ISOLATION | FIXED |
| PRODUCT ACCESS SECURITY PATCH | IMPLEMENTED |
| PRODUCT ACCESS SECURITY PATCH HARDENING | COMPLETE |
| PRODUCT ACCESS SECURITY PATCH | NOT FROZEN |
| IAM SHELL CONTEXT IMPLEMENTATION | NOT STARTED |
| HEALTHCARE WEB | NOT IMPLEMENTED |

Hardening record: `docs/gates/product-access-multi-org-context-isolation-hardening.md` (**COMPLETE**; patch still **not frozen**).

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, or push.

---

## 1. Baseline

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `5d124de2c80bc17127fc17e9f6a730828c13a63a` |
| Tag | Annotated `clinical-read-core-frozen` → same commit |
| Parent | `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716` (`product-access-tenancy-foundation-frozen`) |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Migration `0019` | Does not exist |
| `docker-compose.yml` | Untouched |
| Clinical Read Core module | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `product_access_pdp.py` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |
| Frozen clinical domains | Untouched |

Working tree also contains the already-approved Healthcare Web Shell & IAM Context design documents. This pass adds the authorization-foundation fix those APIs must match. It does **not** implement those APIs.

---

## 2. Principal construction trace

Production path (unchanged order, scoped projection added):

```
JWT (php-api)
  → token validator
  → IamRepository.load_principal(subject)
       memberships (all ACTIVE)
       permissions_by_role_id (per role)
       permission_codes = union of those maps (global load)
       facility_ids = union of non-null membership facility_id (global load)
  → get_principal: if X-Organization-Id present, Principal.for_organization(id)
  → authorize._context: if staff and organization_id present, for_organization again
  → ProductAccessPDP.evaluate (unknown-principal deny, PLATFORM_ADMIN PHI deny)
  → Wave1PolicyPDP.evaluate (frozen)
  → facility_tenant_decision (facility ∈ request organization)
```

`actor_permissions` / Wave1 `scopes` = `Principal.permission_codes` after the organization projection.  
`actor_facility_ids` = `Principal.facility_ids` after the projection.  
`actor_organization_id` on the context is the request organization; `actor_organization_ids` is the projected set (selected tenant only, or empty for platform-only).

PatientPrincipal is unchanged and is not routed through `for_organization`.

---

## 3. Defect (before this patch)

`load_principal` built one global staff principal. `authorize._context` copied that union into Wave1 `scopes` and `actor_facility_ids`. ProductAccessPDP did **not** narrow permissions or facilities by selected organization before calling Wave1.

Wave1 still only required:

- action ∈ (unioned) scopes
- request org ∈ `actor_organization_ids`
- if `X-Facility-Id` present: empty facility list ⇒ org-wide allow, else allow-list

So membership in organization B could authorize B-only permissions while the request organization was A, and a non-empty facility id from B could pollute A’s empty-list (org-wide) semantics.

This is **not** a new contract. Frozen Product Access already required: Organization == MVP tenant; evaluate permissions and facility authority in the active organization context.

---

## 4. Severity

| Item | Class |
|---|---|
| Permissions from organization B authorizing operations in organization A | **P1 CROSS-ORGANIZATION PRIVILEGE BLEED** |
| Facility allow-list / empty-list union across organizations | Security defect (same class of isolation failure; org-wide A incorrectly became a cross-org allow-list collision) |
| P0 | None found |
| P2 / P3 from this pass | None opened |

Do not treat this as P3 because the union was inherited from Wave1 principal loading.

---

## 5. Reproduction matrix (before → after)

Catalog roles used: `CLINICIAN`, `ORG_ADMIN`, `REGISTRAR`, `AUDITOR`. Differentiating operations: `POST /clinical/conditions` (`clinical.condition.create`) vs `POST /organizations/{id}/facilities` (`org.facility.create`). Chart `authorized_sections` used as a read-side check, not as the sole proof.

| Setup | `X-Organization-Id=A` | `X-Organization-Id=B` (or C) |
|---|---|---|
| A CLINICIAN / B ORG_ADMIN | Condition create **allowed**; facility create **403**; no `org.facility.create` in `/iam/users/me` | Facility create **allowed**; condition create **403**; no `clinical.condition.create` |
| A ORG_ADMIN / B CLINICIAN (reverse) | Facility create **allowed**; condition create **403** | Condition create **allowed**; facility create **403** |
| A CLINICIAN / B REGISTRAR / C AUDITOR | Condition create **allowed**; no registrar `mpi.identity.create` in me | B: condition create **403**; chart sections `["encounters"]` only. C: condition create **403**; chart includes conditions (read) |
| A explicit A1 / B explicit B2 | A1 chart **200**; A2 **403/404**; B1/B2 headers **403/404** | B2 **200**; B1 **403/404**; A1 header **403/404** |
| A empty facility list (org-wide) / B explicit B1 | A1 and A2 **200**; B1 **403/404** | B1 **200**; A1 **403/404** |
| A CLINICIAN+A1 / B ORG_ADMIN org-wide | Clinical write A; no org-admin; A1 only; B’s all-facilities does not apply | Org-admin write B; no clinician write; A1 meaningless; B1 allowed |
| Header tamper `org=A, facility=B1` and reverse | Deny/conceal | Deny/conceal |
| PLATFORM_ADMIN + `X-Organization-Id` of a hospital | Chart **403** PHI deny; organization create still **200/201** | n/a |

Before the patch, A CLINICIAN + B ORG_ADMIN received the unioned permission set in both headers, so A could perform B’s `org.facility.create` against A’s organization path once Wave1 saw the action in global scopes and A in `actor_organization_ids`.

---

## 6. Root cause

Organization isolation was applied only as “is this org in the actor’s membership org set?” Permissions and facility allow-lists were global. ProductAccessPDP received **B: a global principal containing unioned permissions/facilities**. It did not safely narrow that principal before Wave1PolicyPDP.

---

## 7. Production fix

Minimum organization-scoped projection, applied **before** the frozen PDP:

```
authenticated user
  → resolve selected organization membership
  → organization-scoped Principal
  → ProductAccessPDP
  → Wave1PolicyPDP
```

`Principal.for_organization(organization_id)`:

- Requires no new role catalog and no schema.
- Tenant memberships: `organization_id == selected` only.
- Permissions: union of those memberships’ `permissions_by_role_id` maps only.
- Facilities: if any selected-org membership has `facility_id is None` → empty set (org-wide **for that org**). Else explicit ids in that org only.
- Platform memberships (`organization_id is None`) are retained as platform; they are not rewritten as a hospital membership. `iam.platform` remains in scopes so ProductAccessPDP PHI deny stays intact. Other platform permissions remain so frozen platform administration (for example organization create, bootstrap membership assign) still passes Wave1’s “action ∈ scopes” check before the platform short-circuit.
- Re-applying the projection for the same organization is idempotent (needed because both `get_principal` and `authorize` may project).
- No selected-org membership → empty tenant org/facility sets; platform-only permissions if a platform membership exists.

`get_principal` projects when `X-Organization-Id` is present so Clinical Read Core `authorized_sections` (which reads `principal.permission_codes`) matches enforcement **without editing** the Clinical Read Core module.

`authorize._context` also projects using the authorize `organization_id` (path or header) so path-org APIs cannot use a header-A principal to act in B.

Mismatch header A + path B yields an empty tenant projection → deny.

No migration `0019`. Wave1PolicyPDP not modified. ProductAccessPDP not modified. PatientPrincipal not modified.

---

## 8. ProductAccessPDP result

**Before:** B — global unioned principal. ProductAccessPDP only dispatched patient vs staff, unknown-principal deny, and platform PHI deny. It did not org-scope scopes or facilities.

**After:** A — already organization-scoped staff principal (plus retained platform membership when present). ProductAccessPDP behavior unchanged; it now receives the correct actor context.

---

## 9. Wave1PolicyPDP status

FROZEN. File hash unchanged. Empty `actor_facility_ids` still means all facilities **in the already-authorized organization**. After this patch, that empty list is per selected organization, not a merge of every membership.

---

## 10. Files changed (this resolution)

Production:

- `backend/app/modules/iam/domain/models.py` — `permissions_by_role_id`, `for_organization`
- `backend/app/modules/iam/infrastructure/repositories.py` — per-role permission load
- `backend/app/modules/authorization/application/authorize.py` — staff context uses the projection
- `backend/app/api/v1/deps.py` — `get_principal` projects when org header present

Tests:

- `backend/tests/unit/test_principal_organization_scope.py`
- `backend/tests/integration/test_product_access_multi_org_isolation.py`

Docs:

- this file
- `docs/architecture/healthcare-web-shell-iam-context-design.md` (inherited union superseded)
- `docs/gates/healthcare-web-shell-iam-context-design-approval.md` (same)

---

## 11. Regression tests

Focused coverage:

- A clinician / B org-admin isolation (API + `/iam/users/me` + Clinical Read Core chart)
- Reverse role isolation
- Three-org CLINICIAN / REGISTRAR / AUDITOR (no union)
- Explicit A1 vs B2 facility isolation + cross-org facility header rejection
- Empty facility scope per-org (A org-wide does not authorize B1)
- Mixed CLINICIAN+A1 / ORG_ADMIN org-wide
- PLATFORM_ADMIN PHI deny with org header; platform org create still allowed

Full Product Access & Tenancy suite ran inside full pytest (platform PHI deny, audiences, patient binding, `facility_tenant_decision`, patient isolation, unknown principal, MPI collision).

Clinical Read Core unit, implementation, and hardening tests ran inside full pytest. Chart under A vs B uses scoped `authorized_sections`.

---

## 12. Clinical Read Core impact

No module edits. Header-scoped `CurrentPrincipal` plus authorize projection: clinician chart under A does not gain registrar/admin write; org-admin/auditor/registrar charts under their orgs show only that membership’s read sections. Cluster/org/facility isolation tests remain passing.

---

## 13. Healthcare Web Shell design impact

Approved future `GET /api/v1/iam/me/context` (not implemented here) **must** report the same effective permissions and facility authority this backend projection now enforces.

Required invariant:

```
context.effective_permissions == permissions for selected organization
context.facility_scope == facility authority for selected organization
```

Not a UI-only narrower view of a backend-global union. The design-time “inherited PDP union / READY FOR SEPARATE DESIGN” item is closed by this pass. Shell APIs remain **not started**.

`GET /iam/users/me` is still insufficient for bootstrap (no membership/org/facility list). When the org header is present it now shows the scoped permission set.

---

## 14. Quality results

Executed 2026-08-26 against the live local stack.

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass (193 files) |
| `mypy app` | Pass (132 source files) |
| Full pytest | **355 passed** (was 345 at Clinical Read Core freeze) |
| Alembic | `current == heads == 20260814_0018` |
| Migration `0019` | Absent |
| `/api/v1/health/live` | 200 `{"status":"alive"}` |
| `/api/v1/health/ready` | 200; `postgres` / `redis` / `object_storage` = ok |

---

## 15. P0 / P1 / P2 / P3

| Severity | Class | Item |
|---|---|---|
| P0 | — | None |
| P1 | CROSS-ORGANIZATION PRIVILEGE BLEED | Multi-org permission union — **FIXED** this pass |
| P1 | Facility isolation | Cross-org facility allow-list / empty-list merge — **FIXED** this pass |
| P2 | — | None opened here |
| P3 | — | None opened here |

---

## 16. Stop

- Healthcare Web frontend: not implemented
- IAM shell context endpoints: not implemented
- Migration `0019`: not created
- Wave1PolicyPDP: not modified
- Frozen clinical semantics: not modified
- Patient Mobile / subscription / AI / scheduling: not implemented

**NO COMMIT. NO TAG. NO PUSH.**
