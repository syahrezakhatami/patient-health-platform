# Product Access multi-organization context isolation — hardening

**Date:** 2026-08-26  
**Kind:** Hardening only (not a freeze)  
**Verdict:** COMPLETE — no unresolved P0/P1  

| Flag | Value |
|---|---|
| MULTI-ORG PERMISSION ISOLATION | FIXED |
| MULTI-ORG FACILITY ISOLATION | FIXED |
| PRODUCT ACCESS SECURITY PATCH | IMPLEMENTED |
| PRODUCT ACCESS SECURITY PATCH HARDENING | COMPLETE |
| PRODUCT ACCESS SECURITY PATCH | NOT FROZEN |
| IAM SHELL CONTEXT IMPLEMENTATION | NOT STARTED |
| HEALTHCARE WEB | NOT IMPLEMENTED |

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, push, or freeze.

Implementation record: `docs/gates/product-access-multi-org-context-isolation-resolution.md`.

---

## 1. Parent baseline

| Item | Live value |
|---|---|
| Branch | `main` == `origin/main` |
| Published HEAD | `5d124de2c80bc17127fc17e9f6a730828c13a63a` |
| Tag | Annotated `clinical-read-core-frozen` → same commit |
| Working tree | Uncommitted security patch + Healthcare Web Shell design docs + this hardening (not baseline corruption) |
| Alembic | `current == heads == 20260814_0018` (one head) |
| Migration `0019` | Does not exist |
| `docker-compose.yml` | Untouched |
| Clinical Read Core | Untouched |
| Frozen clinical modules | Untouched |
| `wave1_pdp.py` | Untouched; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| `product_access_pdp.py` | Untouched; SHA-256 `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |

---

## 2. Security patch state

The implementation pass fixed P1 cross-organization permission union and facility allow-list / empty-list merge by projecting `Principal.for_organization` **before** ProductAccessPDP / Wave1PolicyPDP.

This hardening pass aggressively re-tested that projection (idempotence, double-scoping, header/path mismatch, platform preservation, concurrency, caches) and made one contract-aligned tightening:

- Scoped `permissions_by_role_id` is copied to **kept memberships only**, so an A projection does not retain B’s role map as hidden residue. Authorization already ignored unused map entries; the copy also prevents shared-dict mutation across projections.

Wave1PolicyPDP and ProductAccessPDP were not modified.

---

## 3. `Principal.for_organization` contract

Frozen dataclass; returns a **new** instance. Does not mutate `self`.

For selected organization O:

| Field | Rule |
|---|---|
| `memberships` | Tenant rows with `organization_id == O`, plus platform rows (`organization_id is None`) |
| `permission_codes` | Union of those memberships’ role maps only |
| `facility_ids` | If any selected-org membership has `facility_id is None` → empty set (ALL_IN_ORGANIZATION for O). Else explicit ids in O only |
| `organization_ids` | `{O}` if a tenant membership exists, else empty |
| `role_codes` | Codes from kept memberships |
| `permissions_by_role_id` | Maps for kept memberships only |
| `has_platform_scope` | True iff `iam.platform` remains in `permission_codes` |

Platform membership is not rewritten as a hospital membership. Cross-org tenant authority is dropped.

---

## 4. Idempotence

`principal.for_organization(A).for_organization(A)` is authorization-equivalent to `for_organization(A)`: same permissions, facilities, org ids, membership ids, role map. No duplicates. Original principal unchanged.

---

## 5. Re-projection / tenant hopping

Preferred security behavior (implementation intent): **organization scoping is not a tenant-hopping primitive.**

`principal.for_organization(A).for_organization(B)` does **not** restore B. After A, B memberships are gone; B projection is empty tenant (platform-only if a platform membership was retained).

Not a P1. Hopping is denied.

---

## 6. Double-scoping (`get_principal` + `authorize`)

`get_principal(A)` then `authorize(..., organization_id=A)` does not strip valid A authority and does not resurrect B.

`authorize` on an **unscoped** load still projects to the request org before ProductAccessPDP, so path-org APIs without `X-Organization-Id` do not feed Wave1 a global union.

---

## 7. Header / path mismatch

| Call | Result |
|---|---|
| Header A, `POST /organizations/{B}/facilities` | 403 |
| Header B, `POST /organizations/{A}/facilities` | 403 |
| Header A, `POST /iam/memberships` body org B | 403 |
| Header A, body/path A org-admin | 200/201 |

No “scope to A then authorize B” success path.

---

## 8. Missing organization header

Clinical routes that require `X-Organization-Id` → **422**.

Path-org facility create without header: `authorize` projects to the **path** org. A ORG_ADMIN / B CLINICIAN can create a facility in A, not in B. Global union does not authorize the wrong tenant.

Platform organization create without a real tenant remains allowed under the frozen platform contract.

---

## 9. Platform membership preservation

Platform rows (`organization_id IS NULL`) stay on every projection.

They do **not** add `clinical.*` or `mpi.*` to the catalog. Frozen ProductAccessPDP `_platform_phi_forbidden` still denies those prefixes whenever `iam.platform` is in scopes.

---

## 10. PLATFORM_ADMIN + org header

| Action | Result |
|---|---|
| Clinical chart / condition | 403 |
| MPI identity read | 403 |
| Facility create on that hospital | 403 (not in platform catalog) |
| Organization bootstrap create | 200/201 |

Org header does not convert platform into tenant staff.

---

## 11. Hybrid platform + tenant

Schema permits it: unique index is `(user_id, organization_id, role_id)` `NULLS NOT DISTINCT` on **ACTIVE** rows, so a NULL-org platform membership can coexist with a hospital membership.

**Supported as an identity shape**, not a new product role.

Example: platform + A ORG_ADMIN:

| Context | Behavior |
|---|---|
| A | Non-PHI org-admin (facility create, membership manage) allowed. PHI **403** because frozen ProductAccessPDP denies `clinical.*` / `mpi.*` when `iam.platform` is present. Platform does not add PHI; it **blocks** PHI for dual-hat. |
| B without membership | No tenant authority. Facility create 403. Platform org create still allowed. |

This is frozen ProductAccessPDP behavior, not a new policy. ProductAccessPDP was not changed.

---

## 12. Same-org multiple memberships

Allowed when **roles differ** (unique on user+org+role).

Same-org union **is valid**: CLINICIAN + REGISTRAR in A yields both condition create and identity create.

Explicit facilities A1 + A2 → `{A1, A2}`, **not** empty/all.

If any same-org membership is org-wide (`facility_id is None`), empty `facility_ids` means ALL_IN_ORGANIZATION for that org (Wave1 empty-list semantics). Cross-org union remains forbidden.

REVOKED memberships are excluded by `load_principal` (`status == ACTIVE`). After revoke, B org-admin authority disappears.

Roles/permissions have **no disable flag**. Each request reloads from `role_permissions`. No principal cache.

---

## 13. Permission matrices (APIs)

| Setup | Org A | Org B / C |
|---|---|---|
| A CLINICIAN / B ORG_ADMIN | Condition create yes; facility create 403 | Reverse |
| Reverse roles | Facility yes / condition 403 | Condition yes / facility 403 |
| A CLINICIAN / B REGISTRAR / C AUDITOR | Clinician writes; no registrar/auditor-only | B: encounters only, no condition write. C: read chart, no clinician write |
| A AUDITOR / B CLINICIAN | Condition create 403 | Condition create yes |
| A REGISTRAR / B IDENTITY_OFFICER | Encounter create yes; merge 403 | Encounter create 403 |

A → B → A chart: clinician sections restored after registrar context; no contamination.

---

## 14. Facility matrices

| Setup | A | B |
|---|---|---|
| Explicit A1 / B2 | A1 only | B2 only |
| A empty (org-wide) / B explicit B1 | A1 and A2 200; B1 deny/conceal | B1 200; A1 deny/conceal |
| Same-org A1 + A2 memberships | A1 and A2 200; unlisted A3 deny | n/a |
| Header org A + facility B1 (and reverse) | deny/conceal | deny/conceal |

Empty list internally remains Wave1 ALL_IN_ORGANIZATION **for the already-authorized org**, never “no facilities” and never all facilities across memberships.

---

## 15. Concurrent request isolation

`Principal` is frozen. `for_organization` allocates a new object. Same JWT, `asyncio.gather` of A clinical write, B facility create, A facility create, B clinical write (×3): A write and B admin succeed; A admin and B write stay 403. No cross-request mutation.

---

## 16. Caching / request-locality

| Check | Result |
|---|---|
| Principal cache by subject | **None.** `IamRepository.load_principal` hits the DB each request |
| FastAPI `Depends(get_principal)` | Request-local |
| `ContextVar` for principal | **None** (structlog binds `correlation_id` only; cleared per request) |
| `app.state.pdp` | Shared stateless `ProductAccessPDP` |
| Module-level mutable principal | **None** |

Unscoped load remains the authenticated union; projection is per request org.

---

## 17. ProductAccessPDP input

Staff `AuthorizationContext` recorded in unit tests: scopes, `actor_organization_ids`, and `actor_facility_ids` are the **selected org** only (plus preserved `iam.platform` when a platform membership exists). ProductAccessPDP source unchanged; it does not call `for_organization`.

---

## 18. Wave1 input / bypass

Production `Wave1PolicyPDP()` appears **only** in `product_access_pdp.py`. Staff actions reach Wave1 only after `authorize._context` projection and ProductAccessPDP dispatch.

`GET /auth/context` evaluates a SYSTEM principal with empty scopes (unknown-principal deny). Not a global staff union bypass.

Wave1 file hash unchanged (section 1).

---

## 19. IAM / MPI / Clinical Read Core / patient

IAM org-admin operations work under the admin org and are denied under the clinician org, including header/body org mismatch.

PatientPrincipal is not projected. Patient self-access, binding, `PATIENT_ACCESS`, audience isolation ran in full pytest (existing Product Access suite).

Unknown/None staff principal remains deny-by-default (`unprovisioned_actor`). Missing membership / unknown org UUID does not grant tenant actions; `/iam/users/me` with a foreign org header does not list that org’s permissions.

Error bodies stay `{code, message, correlation_id}` — no membership or permission dumps.

---

## 20. Shell design impact

Approved `GET /iam/me/context` (not implemented) can expose the **same** effective permissions and facility authority this projection now enforces. No DTO redesign required. `/iam/users/me` without an org header still returns the loaded union; Healthcare Web must not use it as bootstrap.

---

## 21. Tests

| File | Coverage |
|---|---|
| `tests/unit/test_principal_organization_scope.py` | Projection contract, idempotence, hop-deny, same-org union, platform hybrid |
| `tests/unit/test_authorization_organization_scope.py` | Double-scope, unscoped→PDP projection, None principal, PatientPrincipal skip |
| `tests/integration/test_multi_org_context_isolation_hardening.py` | Header/path, missing org, revoked, dual membership, hybrid, platform header, three-org chart switch, auditor/registrar/officer, concurrency, empty facility, Wave1 hash / no cache |
| Existing isolation + Product Access + Clinical Read Core suites | Regression |

Previous patch: **355 passed**. This pass: **374 passed**.

---

## 22. Quality results

Executed 2026-08-26 against the live local stack.

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass (195 files) |
| `mypy app` | Pass (132 source files) |
| Full pytest | **374 passed** |
| Alembic | `current == heads == 20260814_0018` |
| Migration `0019` | Absent |
| `/api/v1/health/live` | 200 `{"status":"alive"}` |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage = ok |

---

## 23. P0 / P1 / P2 / P3

| Severity | Item | Status |
|---|---|---|
| P0 | — | None |
| P1 | Cross-org permission union | **FIXED** (implementation + this hardening) |
| P1 | Cross-org facility union / empty-list merge | **FIXED** |
| P1 candidates (hop, concurrency, platform PHI restore, header/path, missing-membership→platform tenant grant) | Not reproduced | **Clear** |
| P2 / P3 | — | None opened this pass |

`GET /iam/users/me` without `X-Organization-Id` still serializes the unscoped load union. That is not request enforcement. Future context APIs remain the bootstrap surface.

---

## 24. Stop

IAM shell context APIs, Healthcare Web, migration `0019`, Wave1PolicyPDP, ProductAccessPDP, Clinical Read Core, subscription, AI, scheduling: not implemented / not modified.

**NOT FROZEN. NO COMMIT. NO TAG. NO PUSH.**
