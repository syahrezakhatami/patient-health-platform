# Organization governance profile — architecture design

**Date:** 2026-08-28 (provider registry / kill-switch consistency correction)
**Kind:** ARCHITECTURE DESIGN ONLY — not implementation
**Baseline HEAD:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)
**Alembic:** `20260814_0019` (head today)

```
ORGANIZATION GOVERNANCE PROFILE DESIGN = COMPLETE
FINAL PRE-IMPLEMENTATION CONTRACT = COMPLETE
PROVIDER REGISTRY / KILL-SWITCH CONSISTENCY = COMPLETE
IMPLEMENTATION = NOT STARTED
```

Not legal advice. Not authorization to create migration `20260814_0020` or modify production code.

---

## 1. Migration sequencing

| Item | Value |
|---|---|
| Current head | `20260814_0019` |
| Planned OGP migration | **`20260814_0020_organization_governance_foundation`** (NOT CREATED) |
| Parent | `20260814_0019` |
| Observation write migration | **`UNASSIGNED`** (idempotency required when implemented) |
| One-head invariant | **YES** — linear chain only |

```
20260814_0019 → 20260814_0020 (OGP) → (future Observation revision from then-current head)
```

---

## 2. Clinical Note non-regression (frozen)

### 2.1 Zero runtime dependency on first OGP deploy

OGP infrastructure deployment **alone** must **not** add any new runtime dependency to:

- Clinical Note Write
- Clinical Chart / Clinical Read
- Patient Lookup
- MPI
- Any other frozen clinical capability

**Frozen rule:** The Clinical Note create / draft update / finalize request path **must not query** during first OGP implementation:

- `provider_capabilities`
- `organization_governance_profiles`
- `organization_feature_activations`
- deployment gate tables
- governance resolver for `clinical_note_write`

### 2.2 Clinical Note registry and runtime status

| Field | `clinical_note_write` |
|---|---|
| Production registry entry | **NONE** |
| OGP runtime dependency on note routes | **NONE** |
| Runtime resolver invoked on note routes | **NO** |
| Governance metadata on note audit | **NO** (defer until governed capability exists) |
| Behavior vs frozen contract | **UNCHANGED** |

Existing behavior remains: entitlement (if any) + PDP + org/facility + patient safety + frozen Note Write contracts.

**Do not** fix registry/runtime inconsistency by adding `provider_capabilities` lookup to Clinical Note routes. Clinical Note is frozen.

### 2.3 Future Clinical Note onboarding (deferred)

If Clinical Note is ever brought under provider capability enforcement, require a dedicated **Clinical Note Governance Onboarding Design** covering: non-regression, existing organizations, provider state, site activation requirements, audit impact, availability, failure behavior, deployment rollout. **No silent onboarding** through OGP infrastructure alone.

---

## 3. Provider capability registry

### 3.1 Decision: DATABASE-BACKED

Emergency suspend/restore without application deploy. Platform admin mutates `provider_state` via governed API **for registered production capabilities only**.

### 3.2 Design contradiction resolved (false kill-switch)

**Prior defect:** Production seed included `clinical_note_write` as `AVAILABLE` while Clinical Note routes explicitly **do not** consume provider registry state. Suspending that row would have **zero runtime effect** — a false kill-switch / misleading operational assurance.

**Correction:** Migration `0020` creates registry **infrastructure only**. **No production capability rows** are seeded.

```
INITIAL PRODUCTION CAPABILITY SEED = EMPTY
```

A registry row must **not** claim enforceable provider state unless the corresponding runtime capability **actually consumes** provider state decisions.

### 3.3 Initial production seed (migration `0020`)

| Rule | Value |
|---|---|
| **Production seed** | **EMPTY** — zero `INSERT` rows into `provider_capabilities` |
| `clinical_note_write` | **NOT registered** |
| `manual_vital_signs_write` | **NOT registered** — deferred |
| AI capabilities | **NOT registered** |
| ORM startup seed | **FORBIDDEN** |

Primary key: UUID surrogate. **`UNIQUE (feature_id)`**.

After registration, `feature_id`, `feature_version`, `governance_required`, `frozen_release_tag` are **immutable** — material change requires new capability/version workflow (future pass).

### 3.4 Kill-switch terminology

| Term | Meaning |
|---|---|
| **Kill-switch capable infrastructure** | OGP tables, resolver, platform API — established by migration `0020` |
| **Kill-switch enforced feature** | A production capability whose runtime **queries** registry state and denies on `SUSPENDED`/`RETIRED` |

Until a production capability consumes provider state, **no clinical capability** may be claimed as governed by the OGP kill switch. Platform Admin UI must **not** display e.g. "Clinical Note suspended" when Clinical Note is not OGP-enforced.

### 3.5 `governance_required` semantics

`governance_required` controls whether **organization/site governance gates** are required — **not** whether provider registry enforcement exists.

For every **registered production** capability:

| Layer | Rule |
|---|---|
| Provider state enforcement | **MANDATORY** — runtime must consume `provider_state` |
| `governance_required = false` | Provider state applies; **site/deployment governance does not** |
| `governance_required = true` | Provider state **and** site/deployment governance both apply |

`governance_required = false` is **not** proof that provider enforcement is absent — it means site governance is not required. Enforcement is proven by **runtime integration**, not by this flag alone.

### 3.6 Provider registry enforcement contract (future resolver)

| Registry condition | Resolver behavior |
|---|---|
| Row **absent** for `feature_id` | Capability **not governed through OGP registry** — no global deny |
| `AVAILABLE` | Provider layer permits evaluation to continue |
| `SUSPENDED` | **`DENIED_PROVIDER`** |
| `RETIRED` | **`DENIED_PROVIDER`** (permanent for that row) |

**Missing-row non-regression:** Absence from `provider_capabilities` must **not** globally deny arbitrary existing application features. Only code paths **explicitly integrated** with the registry query a specific `feature_id`.

Therefore: Clinical Note **not registered** + Clinical Note **not integrated** = **unchanged frozen behavior**.

### 3.7 Future production registration rule

A production feature may enter `provider_capabilities` only when its implementation contract explicitly defines:

- `feature_id`, `feature_version`
- Provider state enforcement (runtime integration)
- `governance_required`
- Required deployment gates
- Required site approvals
- Entitlement relationship
- Failure behavior
- Audit behavior

No speculative capability registration.

**Manual Vitals:** may become first production registration as `manual_vital_signs_write` only after terminology/site approval, Observation design unblock, implementation/hardening, and runtime OGP enforcement — **not now**.

Business `feature_version` uses semver capability identity + optional `frozen_release_tag` binding — **not** git SHA as sole version.

### 3.8 Provider state machine

| From | To | Result |
|---|---|---|
| `AVAILABLE` | `SUSPENDED` | Legal — audit once |
| `SUSPENDED` | `AVAILABLE` | Legal — audit once |
| `AVAILABLE` | `RETIRED` | Legal — terminal — audit once |
| `SUSPENDED` | `RETIRED` | Legal — terminal — audit once |
| `AVAILABLE` | `AVAILABLE` | **200 idempotent no-op** — no audit |
| `SUSPENDED` | `SUSPENDED` | **200 idempotent no-op** — no audit |
| `RETIRED` | *any* | **409 invalid_transition** |

**`RETIRED` is terminal.** Material return requires new capability/version row — not resurrection.

### 3.9 Provider required gates (metadata)

Normalized `provider_capability_required_gates` (capability_id, gate_type) for queryable resolver config. Populated only when a capability is registered — **empty after initial migration**.

For capabilities with `governance_required=false`: provider state still enforced; site/deployment gates **not** required at resolver. For `governance_required=true`: both provider state and site/deployment gates apply.

---

## 4. Site feature activation state machine

`NOT_CONFIGURED` = **no row** (fail-closed only when `governance_required=true`).

| From | To | Legal? |
|---|---|---|
| *(no row)* | `PENDING_APPROVAL` | **YES** — create activation row |
| `PENDING_APPROVAL` | `APPROVED` | **YES** — required evidence satisfied |
| `PENDING_APPROVAL` | `RETIRED` | **YES** — withdraw before approval |
| `APPROVED` | `ACTIVE` | **YES** — explicit activation |
| `APPROVED` | `PENDING_APPROVAL` | **YES** — evidence invalidated / re-review |
| `APPROVED` | `RETIRED` | **YES** — approved but never activated, decommission |
| `ACTIVE` | `SUSPENDED` | **YES** — org self-suspend |
| `SUSPENDED` | `ACTIVE` | **YES** — resume if evidence still valid + provider available |
| `ACTIVE` | `RETIRED` | **YES** — terminal |
| `SUSPENDED` | `RETIRED` | **YES** — terminal |
| `ACTIVE` | `APPROVED` | **NO** — use `SUSPENDED` or `RETIRED` |
| `RETIRED` | *any* | **NO** — **409** |

**`APPROVED` ≠ `ACTIVE`:** approval provenance is evidence rows — not activation state.

### 4.1 Repeated transition commands

| Command | Current state | Result |
|---|---|---|
| Activate | `ACTIVE` | **200** same state — **no duplicate audit** |
| Suspend | `SUSPENDED` | **200** idempotent — no audit |
| Approve (transition) | `APPROVED` | **200** idempotent if already `APPROVED` and no new evidence command |
| Record approval evidence | duplicate idempotency key | **Replay** — see §8 |

Concurrent transitions: `SELECT FOR UPDATE` on activation row — one wins, other **409** `conflict`.

Mutable rows carry `row_version` (integer) — clients send `expected_row_version` on transition commands.

---

## 5. Governance admin idempotency (REQUIRED)

Prior "NOT REQUIRED" is **superseded** for append-only admin commands.

```
GOVERNANCE ADMIN IDEMPOTENCY = REQUIRED
```

### 5.1 Scope

| Operation | Idempotency |
|---|---|
| Create profile version (DRAFT) | **Required** — `Idempotency-Key` |
| Publish profile version | **Required** — `Idempotency-Key` |
| Record approval evidence | **Required** — `Idempotency-Key` |
| Site feature state transition | **`expected_row_version`** (+ optional key) |
| Deployment gate update | **`expected_row_version`** |
| Provider capability suspend/restore | **`expected_row_version`** |

Do **not** reuse `clinical_note_write_idempotency`.

### 5.2 Planned table: `governance_admin_idempotency`

Included in **`20260814_0020`** design (not created in this pass):

| Column | Purpose |
|---|---|
| `id` | UUID PK |
| `scope_type` | `ORGANIZATION` \| `PLATFORM` |
| `organization_id` | nullable — null for platform scope |
| `actor_id` | UUID |
| `operation` | e.g. `GOVERNANCE_PROFILE_VERSION_CREATE`, `GOVERNANCE_APPROVAL_EVIDENCE_RECORD` |
| `idempotency_key` | client header |
| `request_fingerprint` | SHA-256 canonical JSON |
| `resource_type` | e.g. `PROFILE_VERSION`, `APPROVAL_EVIDENCE` |
| `resource_id` | UUID of created resource |
| `created_at` | timestamptz |

**Unique:** `(scope_type, organization_id, actor_id, operation, idempotency_key)` (NULLS NOT DISTINCT where supported, or separate partial indexes per scope).

Insert-only for `app_dml`. Replay re-checks auth + org scope + permission before returning stored `resource_id`.

### 5.3 Fingerprints (canonical JSON → SHA-256)

**Profile version create:** `organization_id`, `schema_version`, canonical `policy_document`, `effective_at`, `reason`.

**Approval evidence record:** `organization_id`, `feature_id`, `provider_feature_version`, `approval_type`, `scope`, `decision_by_name`, `approval_date`, `artifact_reference`, `approver_role_category`.

No ambiguous string concatenation. No document bodies. No PHI.

### 5.4 Ambiguous retry scenario (mandatory)

Admin records clinical approval → server commits → connection drops → admin retries **same** `Idempotency-Key` + fingerprint:

**Expected:** one evidence row, one audit event, **200** with same resource id.

Without idempotency-key: **must not** create duplicate evidence.

---

## 6. Profile version lifecycle

### 6.1 Status values

| Status | Meaning |
|---|---|
| `DRAFT` | Created, not yet effective |
| `PUBLISHED` | Immutable effective version candidate |
| `SUPERSEDED` | Replaced by newer published version |

### 6.2 Commands (separate — no hidden partial publish)

1. **CreateProfileVersion** → row `DRAFT` (idempotent)
2. **PublishProfileVersion** → `DRAFT` → `PUBLISHED`, set `active_published_version_id` atomically (idempotent)

No single command that silently create+publishes without explicit publish in MVP.

### 6.3 Active profile resolution

Query: latest `PUBLISHED` version where `effective_at <= now()` for profile; tie-break **highest `version_number`**.

No background scheduler. Future `effective_at` becomes active when time passes and next read occurs.

**Constraint:** `UNIQUE (organization_governance_profile_id, version_number)`.

### 6.4 Cyclic FK creation order (migration-safe)

1. Create `organization_governance_profiles` (`active_published_version_id` **nullable**, no FK yet)
2. Create `organization_governance_profile_versions` (`profile_id` → profiles)
3. Add FK `profiles.active_published_version_id` → `versions.id`

### 6.5 Active pointer integrity

Enforcement (DB trigger + service):

- `active_published_version_id` references version belonging to **same** `profile_id`
- version `organization_id` matches profile `organization_id`
- version `status = PUBLISHED`

Plain FK to `version.id` alone is **insufficient** without composite/trigger guard.

### 6.6 Immutability

Published version rows: **INSERT-only** (trigger blocks UPDATE/DELETE).

`organization_id`, `profile_id` on versions: **immutable** after insert.

---

## 7. Approval evidence

Append-only `governance_approval_evidence`.

| Field | Notes |
|---|---|
| `decision_by_name` | External approver (clinical authority) |
| `recorded_by_user_id` | Platform user who recorded evidence |
| `expires_at` | Optional — resolver treats expired required evidence as unsatisfied |
| `status` | `APPROVED` \| `REJECTED` \| `WITHDRAWN` |

**Revocation:** new append-only **`WITHDRAWN`** or **`SUPERSEDED`** evidence row referencing `supersedes_evidence_id` — **never** UPDATE original row in place.

Bindings immutable: `organization_id`, `feature_id`, `provider_feature_version`, `governance_profile_version_id`, `approval_type`, `scope`.

---

## 8. Deployment gates (MVP)

### 8.1 Gate types (provider-defined catalog)

| `gate_type` | MVP |
|---|---|
| `CONTROLLER_PROCESSOR_ASSESSMENT` | YES |
| `DPA` | YES |

No free-text gate names.

### 8.2 Gate states

| State | Meaning |
|---|---|
| `NOT_ASSESSED` | Default |
| `PENDING` | In progress |
| `SATISFIED` | Complete |
| `NOT_APPLICABLE` | Explicit N/A |
| `EXPIRED` | Was satisfied; expired |

### 8.3 Storage

| Table | Role |
|---|---|
| `organization_deployment_gate_states` | Current state per (org, gate_type) — **UPDATE** allowed with `row_version` |
| Audit event | Each change → `GOVERNANCE_DEPLOYMENT_GATE_CHANGED` |

History via audit + optional future event table — **do not** silently overwrite without audit.

Deployment gate changes **do not** create new profile version in MVP (normalized state row update).

---

## 9. Policy schema v1 (bounded JSONB)

Validated by Pydantic before persist. PostgreSQL JSONB + optional CHECK on `schema_version`.

```yaml
schema_version: 1
encounter_status_policy:
  planned: DENY | ALLOW      # default DENY
  finished: DENY | ALLOW     # default DENY
backdating_policy:
  allowed: false | true
  reason_required: true
  max_past_offset: null | string   # ISO-8601 duration; null = unset
late_documentation_policy:
  finished_encounter_write_allowed: false | true
  reason_required: true
  secondary_approval_required: false | true
correction_policy:
  allowed_initiator_permissions: [string]   # PDP codes
  reason_required: true
  secondary_approval_required: false | true
```

No rule engine. No speculative future settings beyond first governed capability needs.

---

## 10. Authorization & audiences

### 10.1 Permission infrastructure (existing)

- Codes in `Permission` StrEnum (`backend/app/modules/authorization/domain/catalog.py`)
- Seeded via Alembic `INSERT INTO permissions`
- Runtime assignment from `role_permissions` — not hardcoded role names
- Org-scoped actions use `ORG_SCOPED_PERMISSIONS` in Wave1PolicyPDP

### 10.2 New permission codes (planned migration `0020` seed)

| Code | Purpose | Scope |
|---|---|---|
| `governance.profile.read` | Read OGP + effective context (management detail) | ORG |
| `governance.profile.manage` | Create/version/publish profile; deployment gate updates | ORG |
| `governance.approval.record` | Record approval evidence (**separate from manage**) | ORG |
| `governance.feature.activate` | Transition site activation ACTIVE/SUSPENDED/RETIRED | ORG |
| `governance.provider.manage` | Provider capability suspend/restore/retire | PLATFORM |

**No RBAC role-name authorization.** Approval role category remains evidence metadata only.

Separation prevents one `profile.manage` holder from silently self-recording clinical approval **and** activating without `approval.record` + `feature.activate` grants where org policy requires.

Add to `ORG_SCOPED_PERMISSIONS`: all except `governance.provider.manage`.

Platform permission requires `iam.platform` **and** `governance.provider.manage` — still **no clinical PHI access**.

### 10.3 Token audiences (frozen config)

| Surface | Audience | Dependency |
|---|---|---|
| `/api/v1/organizations/{id}/governance/...` | **`php-api`** | `require_staff_audience` |
| `/api/v1/platform/governance/...` | **`php-platform`** | new `require_platform_audience` (or explicit `auth.audience == php-platform`) + `iam.platform` |

Defaults from `Settings`: `auth_audience=php-api`, `auth_platform_audience=php-platform`.

### 10.4 Organization isolation

Governance management requires org membership + `X-Organization-Id` match per frozen product-access rules. Cross-org UUID → **403/404** per existing convention — not oracle.

Platform admin suspend **does not** grant patient search, chart read, or clinical mutation.

---

## 11. Policy resolution (conjunctive)

All required layers must pass. Any deny → deny.

Resolver is invoked **only** on routes explicitly integrated with a registered `feature_id`. Non-integrated frozen capabilities (e.g. Clinical Note) **never** invoke the resolver.

### 11.1 Request evaluation order (disclosure-safe)

For an **OGP-integrated** route with registered `feature_id`:

```
1. Authenticate
2. Resolve organization + verify membership
3. Provider hard invariants (code)
4. Provider capability row lookup:
     absent -> not OGP-governed (route must not reach here unless integrated)
     SUSPENDED/RETIRED -> DENIED_PROVIDER
     AVAILABLE -> continue
5. If governance_required=true:
     entitlement
     deployment gates (per capability metadata)
     site activation + site policy
6. PDP permission
7. Domain clinical safety
```

For `governance_required=false` registered capabilities: steps 5 skipped; step 4 (provider state) **still applies**.

Internal denial codes (`DENIED_PROVIDER`, etc.) **not** returned to clinical clients — map to safe 403/404/409.

### 11.2 Effective context DTO (clinical read)

`GET /api/v1/organizations/{organization_id}/governance/effective-context`

```yaml
governed_features: []    # empty in MVP infra-only deploy
policy:
  encounter_status: { planned: DENY, finished: DENY }   # only if profile exists; else omit or defaults
```

Per governed feature (future):

```yaml
- feature_id: manual_vital_signs_write
  available: false
  feature_version: null
  # NO internal denial enum exposed to clinicians
```

**Omit** from clinical DTO: approver names, DPA, legal assessments, waivers, plan internals.

`clinical_note_write`: **omit** — not registered, not OGP-enforced, no runtime query.

### 11.3 Management DTO (authorized governance actors)

May include: profile version, activation state, approval evidence metadata, deployment gate states, `row_version` fields. No PHI.

---

## 12. Concurrency & locking

| Operation | Lock order |
|---|---|
| Publish profile version | `profiles` FOR UPDATE → version row |
| Feature transition | `organization_feature_activations` FOR UPDATE |
| Deployment gate update | `organization_deployment_gate_states` FOR UPDATE |
| Provider capability transition | `provider_capabilities` FOR UPDATE |

Deterministic order when multiple locks needed: **profile → activation → deployment → provider** (document to prevent deadlocks).

---

## 13. Audit events (planned names)

| Action | When |
|---|---|
| `GOVERNANCE_PROFILE_VERSION_CREATED` | DRAFT created |
| `GOVERNANCE_PROFILE_VERSION_PUBLISHED` | Published + pointer updated |
| `GOVERNANCE_APPROVAL_EVIDENCE_RECORDED` | Evidence appended |
| `GOVERNANCE_APPROVAL_EVIDENCE_WITHDRAWN` | Supersession/withdrawal recorded |
| `GOVERNANCE_FEATURE_ACTIVATION_CHANGED` | Site state transition |
| `GOVERNANCE_DEPLOYMENT_GATE_CHANGED` | Gate state update |
| `GOVERNANCE_PROVIDER_CAPABILITY_CHANGED` | Provider suspend/restore/retire (**registered capabilities only**) |

State mutation + success audit: **same transaction**. Audit failure rolls back mutation.

Provider capability state-change audits are meaningful **only for registered/enforced capabilities**. Synthetic test records do not become production audit artifacts.

**Clinical domain audit:** governance metadata (`governance_profile_version_id`, etc.) **deferred** until first `governance_required` capability ships — **no Clinical Note audit schema change** in OGP-only MVP.

---

## 14. Planned migration `0020` tables

| Table | Mutability (app_dml) |
|---|---|
| `provider_capabilities` | SELECT; UPDATE `provider_state`, `row_version` only |
| `provider_capability_required_gates` | SELECT; INSERT (on capability registration) |
| `organization_governance_profiles` | INSERT, SELECT, UPDATE pointer only |
| `organization_governance_profile_versions` | INSERT, SELECT only |
| `organization_feature_activations` | INSERT, SELECT, UPDATE state/`row_version` |
| `organization_deployment_gate_states` | INSERT, SELECT, UPDATE |
| `governance_approval_evidence` | INSERT, SELECT only |
| `governance_admin_idempotency` | INSERT, SELECT only |

No DELETE/TRUNCATE for `app_dml`. Grants in `grant_dev_privileges.sql` post-migration.

### 14.1 DB triggers

| Target | Rule |
|---|---|
| Published profile versions | Block UPDATE/DELETE |
| Approval evidence | Block UPDATE/DELETE |
| Activations | Block change to `organization_id`, `feature_id` |
| Provider capabilities | Block change to `feature_id`, `governance_required`, seed metadata |

### 14.2 Waivers / Redis / AI / facility

**DEFERRED** in MVP.

---

## 15. MVP management API commands (future — not implemented)

All org routes: `require_staff_audience` + org membership + permission.

| Method | Path | Permission |
|---|---|---|
| GET | `/api/v1/organizations/{org_id}/governance/effective-context` | `governance.profile.read` |
| GET | `/api/v1/organizations/{org_id}/governance/profile` | `governance.profile.read` |
| POST | `/api/v1/organizations/{org_id}/governance/profile/versions` | `governance.profile.manage` + Idempotency-Key |
| POST | `/api/v1/organizations/{org_id}/governance/profile/versions/{id}/publish` | `governance.profile.manage` + Idempotency-Key |
| POST | `/api/v1/organizations/{org_id}/governance/approvals` | `governance.approval.record` + Idempotency-Key |
| POST | `/api/v1/organizations/{org_id}/governance/features/{feature_id}/transition` | `governance.feature.activate` + expected_row_version |
| PUT | `/api/v1/organizations/{org_id}/governance/deployment-gates/{gate_type}` | `governance.profile.manage` + expected_row_version |

Platform:

| Method | Path | Permission |
|---|---|---|
| GET | `/api/v1/platform/governance/capabilities` | `iam.platform` + `governance.provider.manage` |
| POST | `/api/v1/platform/governance/capabilities/{feature_id}/transition` | `iam.platform` + `governance.provider.manage` |

Immediately after production migration the capability list is **empty** — API must return empty list correctly without inventing rows.

**No DELETE endpoints.** No generic PATCH. DTOs: `extra = forbid`.

**No self-approval shortcut:** record approval and activate are **separate** commands.

---

## 16. Bootstrap & lazy profile

- **Lazy profile creation** on first governance management action
- No empty v1 for all orgs
- No fake approvals
- Empty governed feature set in effective-context until real activations exist

---

## 17. Test strategy (implementation)

Tests use **synthetic** capabilities in fixtures (e.g. `test_governed_feature`) — **not** production migration seed.

| Scenario | Expected |
|---|---|
| Zero rows after production migration seed | **YES** |
| Clinical Note routes independent of OGP | **YES** |
| Synthetic: no site profile, `governance_required=true` | Deny |
| Synthetic: provider `SUSPENDED` | **`DENIED_PROVIDER`** |
| Synthetic: provider `RETIRED` | **`DENIED_PROVIDER`** |
| Synthetic: provider `AVAILABLE` + site inactive | Deny |
| Synthetic: all gates satisfied | Effective available |

No production clinical feature must be activated to prove foundation correctness.

---

## 18. Threat model

| Threat | Mitigation |
|---|---|
| OGP breaks Clinical Note | No registry entry; no resolver on note path |
| False kill-switch assurance | Empty production seed; enforcement only when runtime integrated |
| Duplicate evidence on retry | `governance_admin_idempotency` |
| Duplicate profile versions on retry | Same idempotency table |
| Profile fail-open | Fail-closed **only** for integrated `governance_required=true` routes |
| Global deny from missing registry row | Only integrated routes query specific `feature_id` |
| Self-approve + activate | Separate permissions |
| Policy oracle to clinician | Generic errors only |
| Active pointer cross-profile | Trigger + composite checks |
| Last-write-wins | `expected_row_version` |
| Platform admin clinical access | Frozen PHI wrapper unchanged |
| UI shows suspended unenforced capability | Omit unregistered capabilities from operational kill-switch UI |

---

## 19. Related documents

- `docs/gates/organization-governance-profile-design-approval.md`
- `docs/governance/*` (authority hierarchy unchanged)
- `docs/architecture/observation-vital-signs-write-workflow-design.md` (BLOCKED; migration UNASSIGNED)
