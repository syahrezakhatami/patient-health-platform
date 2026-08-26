# Product access and tenancy foundation — design

**Date:** 2026-08-26  
**Kind:** Design contract only  
**Status:** APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN  
**Baseline:** `wave-2b-clinical-foundation-complete` / `b1606fe38dfaf4ee24d95775c07e77cb842c3736`  
**Alembic:** `current == heads == 20260814_0017`  
**Wave1PolicyPDP:** frozen — must not be edited

This contract is not an implementation, not migration `0018`, and not a HIPAA certification. It does not start Healthcare Web, Patient Mobile, Platform Admin Web, subscription, billing, AI, scheduling, notifications, pharmacy, or emergency.

Companion gate: `docs/gates/product-access-tenancy-foundation-design-approval.md`.  
Discovery input: `docs/architecture/product-platform-discovery.md`.

---

## Decisions (normative)

| # | Topic | Decision |
|---|---|---|
| 1 | MVP tenant grain | Existing `organizations.id`. No `tenants` table. |
| 2 | Organization vs tenant | **Organization == MVP tenant.** Types `HOSPITAL` and `CLINIC` are classifications, not separate tenant kinds. |
| 3 | Facility | Always exactly one organization. Optional on clinical facts. Empty `actor_facility_ids` = all facilities **in that org**. |
| 4 | Staff membership | `users` + `organization_memberships` + role → permissions. Access requires membership org match. |
| 5 | Platform operator | **Option C:** keep role code `PLATFORM_ADMIN`; split catalog so it is non-clinical by default; add an authorize **wrapper** (not a Wave1PolicyPDP edit). No `PLATFORM_OPERATOR` role in MVP. |
| 6 | Platform clinical default | **DENY.** Platform ownership ≠ clinical access. |
| 7 | Wave1PolicyPDP | Untouched. Extend **around** it: principal-type dispatch in `authorize()` + new Patient PDP. |
| 8 | Patient principal | New `PatientPrincipal`. `PrincipalType.PATIENT` becomes authoritative. **Not** an IAM `users` row. |
| 9 | Account ↔ MPI | One active `patient_accounts` row ↔ one canonical `patient_identities.id`. Link is UUID, never NIK/BPJS. |
| 10 | Patient permissions | New `patient.*` namespace. Do **not** grant `clinical.*` to patients. |
| 11 | Self-access | Requested identity must equal canonical(binding). UUID guessing → 404. |
| 12 | MPI merge | Authorize on canonical survivor; read expansion via cluster IDs. Rebind when unique; disable on account collision. |
| 13 | RETIRED | Deny login and self-access. |
| 14 | ANONYMOUS | **Not eligible** for Patient Mobile binding until identified to `ACTIVE`. |
| 15 | Tokens | Three audiences: platform, staff, patient. No token reuse across client types. |
| 16 | Same-org patient | Patient reads only resources with matching `organization_id`. |
| 17 | Multi-org patient | **SEPARATE FUTURE PDP DESIGN.** Not approved. |
| 18 | Future DB | `patient_accounts` + binding uniqueness; `role_permissions` strip; optional new bootstrap permission. |
| 19 | Migration | Forward-only after `0017`. Do not rewrite `0001`–`0017`. |
| 20 | API | Staff stay on existing prefixes. Future `/api/v1/platform` and `/api/v1/patient`. No `/api/v2`. |
| 21 | Audit | Bind, login, membership, operator actions, denied cross-tenant. No extra clinical provenance on patient **reads**. |
| 22 | Threats | See §26. Tenant header, UUID guess, operator PHI, wrong bind, stale merge, token reuse. |

Entitlement remains a **later** question. This foundation must work with no subscription, expired subscription, or free plan. Isolation does not turn off when billing changes.

---

## A. Tenant contract

### Canonical boundary

**`organization_id` is the canonical MVP tenant identifier.**

Evidence: `organizations` already exist; every clinical table has `organization_id`; staff APIs require `X-Organization-Id`; PDP org-scopes `ORG_SCOPED_PERMISSIONS`; Hospital/Clinic are `OrganizationType` values.

A generic `Tenant` abstraction is **not** created. Organization is sufficient for MVP.

`NETWORK` remains a type label only. Hospital groups / parent-child orgs are **DEFERRED**. No implicit tenant inheritance. Hospital A ≠ Hospital B. Clinic A ≠ Clinic B.

### Tenant lifecycle

Organization `ACTIVE` / `INACTIVE` already exist. Inactive tenant: staff memberships must not authorize new clinical writes (future service rule). Existing clinical rows are **not** deleted. Subscription status, when it exists later, must not drop isolation: a cancelled tenant is still isolated; it is not world-readable.

### Tenant-scoped vs platform-scoped

| Tenant-scoped | Platform-scoped |
|---|---|
| Facilities | Organization **create** (onboarding) |
| Staff memberships with `organization_id` set | `PLATFORM_ADMIN` users (`organization_id` NULL membership) |
| Clinical facts | Permission / role catalog |
| Org identifiers, MRNs | Future plans, invoices, AI **cost** metadata (no PHI) |
| MPI identifiers that carry `organization_id` | System health |

MPI **person** UUID is platform-wide. **Clinical facts** about that person are tenant-scoped. That split is frozen and remains.

---

## B. Staff / organization access contract

### Principal chain

```
JWT (staff audience)
  → users.subject
  → Principal (PrincipalType.STAFF | PRACTITIONER as today)
  → organization_memberships (ACTIVE)
  → role_permissions
  → X-Organization-Id must ∈ principal.organization_ids
  → optional X-Facility-Id must pass actor_facility_ids
  → permission action
  → Wave1PolicyPDP
  → resource.organization_id == request org
```

Forbidden as the authorization source: `if role == "DOCTOR"`, `if role == "ADMIN"`. Roles only group permissions.

A worker gains access **only** by an ACTIVE membership in that organization (plus permission). No ad-hoc org bypass for staff.

### Facility

- `facilities.organization_id` is NOT NULL. A facility belongs to **exactly one** organization.
- A user may hold many memberships (many orgs, many facilities).
- Membership `facility_id = NULL` → organization-wide. Existing PDP: empty `actor_facility_ids` means all facilities **in the already-authorized organization**, never all facilities on the platform.
- Clinical facts keep optional `facility_id` as frozen. Organization-scoped without facility remains valid.

### Healthcare Web dependency (do not build)

This contract is **required** before Healthcare Web. One app. Workspaces:

| Workspace | Existing role / permission |
|---|---|
| Registration | `REGISTRAR` |
| Clinician (doctor/nurse undifferentiated) | `CLINICIAN` |
| Organization admin | `ORG_ADMIN` (tenant, not platform) |
| Identity / MPI | `IDENTITY_OFFICER` |
| Read-only audit | `AUDITOR` |
| Nurse vs doctor split | DEFERRED (permission bundles later) |
| Pharmacy | DEFERRED (new permissions, same app) |

UI must not substitute PDP.

---

## C. Platform operator contract (Option C)

### Problem (repository)

1. `ROLE_PERMISSIONS[PLATFORM_ADMIN] = CATALOG_PERMISSIONS` includes every `clinical.*` and `mpi.*`.
2. `Wave1PolicyPDP`: if `iam.platform` ∈ scopes **and** the action is in scopes, allow **without** org isolation (`pdp.wave1.platform_scope`).
3. `authorize()` hardcodes `PrincipalType.STAFF`.
4. Frozen clinical/MPI services: `principal.has_platform_scope` → identity/encounter visible across orgs. Reached only **after** a clinical/MPI action is authorized.
5. Tests: `seed_actor(PLATFORM_ADMIN)` uses `organization_id=NULL` membership; clinical integration tests expect PLATFORM_ADMIN **201 create** and **200 read** (e.g. family-history, allergy, procedure, immunization, device, AE, consent, hardening files). `test_wave1_organization.py` correctly uses PLATFORM_ADMIN to create orgs.

### Options evaluated

| Option | Verdict |
|---|---|
| A. Keep role, only strip clinical from seed | Insufficient alone: `iam.platform` still skips org isolation if a clinical permission is re-added; MPI PHI remains if `mpi.*` kept. |
| B. New `PLATFORM_OPERATOR` role | Extra role ambiguity; frozen tests and memberships use `PLATFORM_ADMIN`; still must strip the old role. |
| **C. Split catalog + keep `PLATFORM_ADMIN` + authorize wrapper** | **Chosen.** Least PHI, lowest rename risk, PDP file untouched. |
| D. Rewrite Wave1PolicyPDP | **Forbidden** this program: PDP is frozen. |

### Chosen semantics

Keep role code **`PLATFORM_ADMIN`**.

Forward migration (future, not now) **deletes** `role_permissions` rows that assign `clinical.*` and `mpi.*` to `PLATFORM_ADMIN`. Application catalog `ROLE_PERMISSIONS` is updated to match so seed and runtime agree.

Retained (platform-scoped): `iam.platform`, `iam.user.provision`, `iam.user.read`, `org.organization.create`, `org.organization.read`.

Bootstrap rule (service, not PDP rewrite): platform operator may assign **`ORG_ADMIN` or `PLATFORM_ADMIN` only**. Must not assign `CLINICIAN`, `REGISTRAR`, `IDENTITY_OFFICER`, or `AUDITOR` (those are tenant-admin operations). This replaces unconstrained `iam.membership.manage` for operators.

**Authorize wrapper** (new code around frozen PDP, future implementation):

```
if action starts with clinical. or mpi.:
    if iam.platform in scopes and actor has no org membership for the request org:
        DENY platform_clinical_forbidden
        (do not call Wave1PolicyPDP)
staff with org membership → Wave1PolicyPDP unchanged
```

Wave1PolicyPDP unit tests that evaluate the frozen function directly remain valid. HTTP/integration tests that expect PLATFORM_ADMIN clinical 201 **must be updated in the implementation wave** to 403; CLINICIAN paths stay frozen. That is a compatibility change, not a silent weakening of clinical invariants.

### Platform Admin Web (do not build)

Depends on this contract.

Safe **before** subscription/billing: create/list organizations, provision platform users, health, platform audit of operator actions.

**Not** safe: clinical routes, MPI identity browse, assigning CLINICIAN to self.

Break-glass / support impersonation: **DEFERRED / REQUIRES SEPARATE SECURITY DESIGN.** Unused `emergency_access_id` is not activated here.

Principle: **platform ownership ≠ automatic clinical access.**

---

## D. Patient principal contract

### Representation

`PrincipalType.PATIENT` is authoritative.

Patients are **not** `users` + `organization_memberships`. Mixing them with staff would allow accidental CLINICIAN membership.

Future `PatientPrincipal`:

- `account_id`
- `subject` (IdP `sub`, not NIK)
- `patient_identity_id` (bound row)
- `canonical_patient_identity_id` (resolved at request time)
- `status`
- `permission_codes` from `patient.*` only

Staff `Principal` remains for Healthcare Web.

A person who is both staff and patient: **DEFERRED** (separate subjects).

### Binding (account ↔ MPI)

| Rule | Contract |
|---|---|
| Link | `patient_accounts.patient_identity_id` → `patient_identities.id` |
| Cardinality | One active account per identity; one identity per active account |
| Multiple identities per account | **Forbidden** |
| Identifier | UUID only. Never NIK/BPJS as FK |
| Staff arbitrary attach | **Forbidden** for MVP |
| Verification | Binding requires identity `ACTIVE` + out-of-band proof later; MVP contract: no bind to ANONYMOUS/MERGED/RETIRED |
| Proofing product | READY FOR SEPARATE DESIGN (not this pass) |

### Canonical resolution (merge)

Frozen clinical rows are **not** rewritten.

At each patient request:

1. Load binding identity B.
2. Canonical-walk B (`surviving_identity_id`, max 8 hops) — reuse MPI walk rules.
3. If canonical is `ACTIVE`, authorize as that UUID.
4. If B is `MERGED` and walk succeeds, **rebind** to survivor when the survivor has no other account; **always** authorize using the survivor.
5. If survivor already has a different account → **disable both accounts**, deny login, audit `PATIENT_ACCOUNT_MERGE_COLLISION`. Support rebind is deferred.
6. Read model (later) may include cluster member IDs (`MERGED_IN`) when querying facts so history on pre-merge UUIDs remains visible. That is query expansion, not a new fact table and not a grant to other patients.

Unmerge restoring B: if account rebound to Y, do not automatically point back to B. **DEFERRED** (support). Dynamic walk still works if binding left on B and B becomes ACTIVE.

### Lifecycle

| Status | Login | Self-access |
|---|---|---|
| ACTIVE | Allow if account ACTIVE | Allow self + same-org |
| MERGED | Resolve then as survivor | As survivor |
| RETIRED | Deny | Deny (not a dead-row browser) |
| Unknown UUID | 404 | 404 |
| ANONYMOUS | **Not eligible to bind** | N/A |

Anonymous emergency identities remain clinical-only until `identify` → ACTIVE or merge into an ACTIVE survivor.

### Self-access

```
authenticated PatientPrincipal
  → canonical_id = resolve(binding)
  → requested_patient_id must == canonical_id
  → X-Organization-Id required and must exist
  → resource.organization_id == request org
  → resource.patient_identity_id ∈ {canonical} ∪ cluster-historical IDs of that person
```

Patient must not list arbitrary patient UUIDs. Cross-org aggregation **DENY**. Guessing another patient’s UUID or another org: **404** (same existence-hiding as staff cross-org).

### Purpose

`PATIENT_ACCESS` **shall** be the required `X-Purpose` on patient self-service APIs.

It is context/audit only. It does **not** grant access. Staff presenting `PATIENT_ACCESS` without a patient principal still need staff permissions (and typically will use `TREATMENT` / `REGISTRATION`).

### Permissions

Do **not** assign `clinical.condition.read` (or any `clinical.*` / `mpi.*`) to patients.

MVP namespace (catalog additions in a future migration):

| Code | Intent |
|---|---|
| `patient.account.read` | Own account metadata |
| `patient.record.read` | Own same-org clinical projection (later read model) |

Do not explode into `patient.medication.read` until the read-model design. Coarse `patient.record.read` is the capability permission. Patient PDP grants it only for self + same org.

### Tokens

| Client | Audience (conceptual) | Principal | Org in token? | Patient id in token? |
|---|---|---|---|---|
| Platform Admin | `platform` | `PLATFORM_ADMIN` | No | No |
| Healthcare Web | `staff` | STAFF | No (header) | No |
| Patient Mobile | `patient` | PATIENT | No (header) | **No** — load from binding by `sub` |

Do not choose an IdP product. Existing JWT validator already checks issuer, audience, expiry, subject. Future settings add allowed audiences per route class. Reject a staff token on `/api/v1/patient/*` and a patient token on `/api/v1/clinical/*`.

Language preference must not appear in the PDP.

### Read model / provenance

No `patient_conditions` / `patient_medications` / `patient_labs` / `patient_histories`. Reads project frozen facts.

Patient **read** does not write `clinical_provenances`. Future patient-authored facts need their own domain contract.

---

## Wave1PolicyPDP extension point

Do **not** modify `wave1_pdp.py`.

Intended future shape:

```
authorize()
  ├─ unprovisioned → existing deny
  ├─ principal_type PATIENT → PatientSelfAccessPDP (new)
  ├─ action clinical.* or mpi.* AND platform operator → DENY wrapper
  └─ else → Wave1PolicyPDP.evaluate (frozen)
```

`PolicyDecisionPoint` protocol already allows a composing implementation. Entitlement, when designed, is a **second** check after authorization, never inside Wave1PolicyPDP.

---

## Isolation matrix

ALLOW / DENY / NOT YET DESIGNED (NYD).

| Actor \ resource | Platform metadata | Hosp A config | Clinic B config | Patient A clinical (org A) | Patient B clinical (org A) | Cross-org clinical | Billing meta (future) | AI cost meta (future) |
|---|---|---|---|---|---|---|---|---|
| Platform operator | ALLOW | ALLOW | ALLOW | **DENY** | **DENY** | **DENY** | NYD (then ALLOW non-PHI) | NYD (then ALLOW non-PHI) |
| Hospital A admin | DENY | ALLOW | DENY | ALLOW read (existing `clinical.*.read`) | ALLOW read if in org A | DENY | DENY | DENY |
| Hospital A clinician | DENY | DENY (org read only as today) | DENY | ALLOW per `clinical.*` | ALLOW if org A + permission | DENY | DENY | DENY |
| Hospital A registrar | DENY | org/facility read | DENY | Encounter create/read; not full chart | same | DENY | DENY | DENY |
| Clinic B admin | DENY | DENY | ALLOW | DENY | DENY | DENY | DENY | DENY |
| Clinic B clinician | DENY | DENY | org read | DENY | DENY | DENY | DENY | DENY |
| Patient A | DENY | DENY | DENY | ALLOW self + org A only | DENY | DENY | DENY | DENY |
| Patient B | DENY | DENY | DENY | DENY | ALLOW self + that org | DENY | DENY | DENY |

---

## Threat model

| Threat | Mitigation |
|---|---|
| Tenant ID tampering (`X-Organization-Id`) | Staff: must be in `organization_ids`. Patient: org must match resource; else 404. Operator: no clinical. |
| Patient UUID guessing | Self-equality on canonical id; else 404 |
| Staff Hospital A → Hospital B | Existing PDP org check; no new bypass |
| Operator browsing PHI | Strip `clinical.*`/`mpi.*`; wrapper deny |
| Account bound to wrong MPI | No staff attach; 1:1; proofing later |
| Stale id after merge | Request-time canonical walk; rebind; cluster read expansion |
| Facility-scope bypass | Unchanged PDP; empty list is org-wide only |
| Privilege escalation (operator → CLINICIAN) | Operator cannot assign clinical roles |
| Forged principal type | Server-side type from loader, not client claim |
| Token reuse across clients | Distinct audiences; route-class rejection |
| Support impersonation | Not implemented; deferred separate design |

Inherited P2 (not fixed here): DENIED audit rollback; historical clinical `patient_identity_id` non-rewrite (handled by cluster expansion); same-org UUID read (retained for staff; not used as a fake patient multi-org grant).

---

## Database preview (do not create)

### 1. `patient_accounts`

| | |
|---|---|
| Purpose | Patient login principal |
| Owner | new `patient_access` module (not `clinical`) |
| Columns | `id` UUID PK; `subject` TEXT UNIQUE NOT NULL; `patient_identity_id` UUID NOT NULL; `status` ACTIVE/DISABLED; timestamps |
| FK | `patient_identity_id` → `patient_identities.id` ON DELETE RESTRICT |
| Uniqueness | `subject`; `patient_identity_id` (one active bind) |
| Lifecycle | Create on verified bind; disable on RETIRED/collision; no DELETE |
| Security | `subject` is IdP sub. No NIK/BPJS columns |

### 2. `role_permissions` rows for `PLATFORM_ADMIN`

Delete assignments where permission like `clinical.%` or `mpi.%`. Not a table rewrite. `0001`–`0017` untouched.

### 3. Permissions catalog rows

Insert `patient.account.read`, `patient.record.read`. Optional later `org.tenant.bootstrap` if bootstrap must not reuse `iam.membership.manage`. Prefer service-level assignable-role constraint first to avoid extra catalog churn.

No tenancy metadata table. No subscription tables. No extra columns on frozen clinical tables.

---

## Migration preview (not `0018` now)

When implementation is approved as its own pass:

1. Additive migration after `0017` (whatever number is then next).
2. Do not rewrite `0001`–`0017`.
3. Strip PLATFORM_ADMIN clinical/MPI grants.
4. Add `patient_*` tables and `patient.*` permissions.
5. Align `ROLE_PERMISSIONS` in `catalog.py` with the database.
6. **Do not** edit `wave1_pdp.py`.
7. Update **only** tests that assert PLATFORM_ADMIN clinical success so they expect 403; add new tests for patient self-access and operator deny. Do not weaken CLINICIAN/org isolation tests.
8. Re-run grants script if new tables need `app_dml` (inherited P3: grants outside Alembic remains).

---

## API preview (no routes now)

| Area | Boundary |
|---|---|
| Staff clinical | Existing `/api/v1/clinical` — staff tokens only |
| Staff IAM/org/MPI | Existing `/api/v1/iam`, `/organizations`, `/mpi` |
| Operator | Future `/api/v1/platform` — platform audience; no PHI list APIs |
| Patient | Future `/api/v1/patient` — patient audience; self only |

No `/api/v2/`. No `/fhir/`. Patient clients must not call `/clinical` write or staff list endpoints.

---

## Audit (future)

| Event | Metadata (no PHI values) |
|---|---|
| `PATIENT_ACCOUNT_BOUND` | account_id, identity_id, actor if any |
| `PATIENT_ACCOUNT_DISABLED` | reason (RETIRED, COLLISION, ADMIN) |
| `PATIENT_LOGIN` / denied | account_id, reason |
| `PATIENT_SELF_ACCESS` success optional | resource_type, org, not note text |
| Membership assign/revoke | as today + operator bootstrap |
| `PLATFORM_ACTION` | action, target org id |
| Denied cross-tenant | reason, policy (inherited denial-audit P2 still applies) |

---

## Subscription and AI boundaries

Subscription FK may later hang off `organizations.id`. Isolation remains if there is no plan, a free plan, or expiry.

AI Gateway later consumes: staff principal → org → permission → **then** entitlement → gateway. No keys, models, or calls in this phase.

---

## Classification

| Capability | Class |
|---|---|
| Organization-as-tenant | **APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN** |
| Operator least privilege (Option C) | **APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN** |
| Patient principal + binding + self-access | **APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN** |
| Patient same-org limitation | **APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN** |
| `patient.*` permissions | **APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN** |
| Patient medical-record read model | READY FOR SEPARATE DESIGN |
| Healthcare Web | READY FOR SEPARATE DESIGN (blocked on implementing this contract first) |
| Platform Admin Web | READY FOR SEPARATE DESIGN (blocked on operator least privilege) |
| Identity proofing UX | READY FOR SEPARATE DESIGN |
| Patient cross-org record | DEFERRED (separate PDP) |
| Break-glass / support impersonation | DEFERRED (separate security design) |
| Hospital groups | DEFERRED |
| Subscription / entitlement | DEFERRED |
| AI / appointment / notifications / pharmacy / emergency | DEFERRED / OUT OF SCOPE this foundation |
| `Tenant` table, `patient_histories`, `clinical.*` for patients, Wave1PolicyPDP rewrite, `/api/v2` | FORBIDDEN |

---

## Implementation scope when a later pass is approved

In scope then: `patient_accounts`, catalog/role_permission updates, authorize dispatcher, Patient PDP, audience checks, tests for deny/self/merge, docs.

Out of scope then unless a new contract: frontends, read-model API completeness, subscription, AI, scheduling, `0018` as a **clinical** fact migration, Wave1PolicyPDP edits, frozen clinical column changes.
