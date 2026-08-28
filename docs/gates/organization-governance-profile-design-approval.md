# Organization governance profile — design approval gate

**Date:** 2026-08-28 (provider registry / kill-switch consistency correction)
**Kind:** DESIGN APPROVAL GATE ONLY — not implementation
**Baseline HEAD:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)
**Alembic:** `20260814_0019` (head today)

```
ORGANIZATION GOVERNANCE PROFILE DESIGN = COMPLETE
FINAL PRE-IMPLEMENTATION CONTRACT = COMPLETE
PROVIDER REGISTRY / KILL-SWITCH CONSISTENCY = COMPLETE
IMPLEMENTATION = NOT STARTED
MIGRATION 0020 = NOT CREATED
```

---

## 1. Baseline verification

| Check | Result |
|---|---|
| HEAD | `c3590dd142f60a79aed3d4f042ff1c505cb2371c` |
| `main == origin/main` | **YES** |
| Tag `provider-governance-foundation-frozen` | Points to HEAD |
| Alembic `current == heads` | **`20260814_0019`** |
| Migration `0020` exists | **NO** |
| Production code changes | **NONE** |
| Uncommitted docs | OGP design + approval; Observation design/gate (migration UNASSIGNED correction only) |

---

## 2. Migration decisions (frozen)

| Item | Value |
|---|---|
| **OGP MIGRATION** | **`20260814_0020_organization_governance_foundation`** |
| Parent | `20260814_0019` |
| **OBSERVATION MIGRATION** | **UNASSIGNED** |
| One linear Alembic head | **YES** |

---

## 3. Clinical Note (frozen)

| Decision | Value |
|---|---|
| **CLINICAL NOTE REGISTRY ENTRY** | **NONE** |
| **CLINICAL NOTE OGP RUNTIME DEPENDENCY** | **NONE** |
| **CLINICAL NOTE BEHAVIOR** | **UNCHANGED** |
| Note create/update/finalize queries OGP tables | **NO** |
| Clinical Note audit schema change | **NO** (defer until governed capability) |
| Fix contradiction via note-path integration | **FORBIDDEN** — Clinical Note frozen |

---

## 4. Provider registry

| Decision | Value |
|---|---|
| **PROVIDER REGISTRY** | **DATABASE-BACKED** |
| **INITIAL PRODUCTION CAPABILITY SEED** | **EMPTY** |
| Migration `0020` provider seed | **NONE** — infrastructure only |
| `clinical_note_write` registered | **NO** |
| `manual_vital_signs_write` registered | **NO** — **DEFERRED** |
| AI capabilities registered | **NO** — **DEFERRED** |
| ORM startup seed | **FORBIDDEN** |

### Provider enforcement semantics

| Decision | Value |
|---|---|
| **PROVIDER STATE ENFORCEMENT REQUIRED FOR REGISTERED FEATURES** | **YES** |
| **GOVERNANCE_REQUIRED** | **SITE-GOVERNANCE REQUIREMENT FLAG, NOT PROVIDER-ENFORCEMENT FLAG** |
| `governance_required=false` | Provider state enforced; site/deployment governance not required |
| `governance_required=true` | Provider state + site/deployment governance both required |
| **MISSING PROVIDER REGISTRY ROW** | **NO EFFECT ON NON-INTEGRATED EXISTING CAPABILITIES** |
| Kill-switch capable infrastructure | OGP migration `0020` |
| Kill-switch enforced feature | Only when runtime consumes registry state |

### Future registration (deferred)

| Capability | Status |
|---|---|
| **MANUAL VITALS PRODUCTION REGISTRATION** | **DEFERRED** — after Observation unblock + implementation |
| **AI PRODUCTION REGISTRATION** | **DEFERRED** |
| **CLINICAL NOTE ONBOARDING** | Requires dedicated onboarding design — no silent registration |

---

## 5. Provider state transitions

| From | To | Result |
|---|---|---|
| `AVAILABLE` | `SUSPENDED` | Legal |
| `SUSPENDED` | `AVAILABLE` | Legal |
| `AVAILABLE` | `RETIRED` | Legal |
| `SUSPENDED` | `RETIRED` | Legal |
| `AVAILABLE` | `AVAILABLE` | **200 idempotent no-op** |
| `SUSPENDED` | `SUSPENDED` | **200 idempotent no-op** |
| `RETIRED` | *any* | **409 invalid_transition** |

| Decision | Value |
|---|---|
| **RETIRED TERMINAL** | **YES** |
| **REPEATED TRANSITION (same state)** | **200 idempotent no-op — no duplicate audit** |

---

## 6. Site activation state transitions

| From | To | Legal? |
|---|---|---|
| *(no row)* | `PENDING_APPROVAL` | YES |
| `PENDING_APPROVAL` | `APPROVED` | YES |
| `PENDING_APPROVAL` | `RETIRED` | YES |
| `APPROVED` | `ACTIVE` | YES |
| `APPROVED` | `PENDING_APPROVAL` | YES (re-review) |
| `APPROVED` | `RETIRED` | YES |
| `ACTIVE` | `SUSPENDED` | YES |
| `SUSPENDED` | `ACTIVE` | YES |
| `ACTIVE` | `RETIRED` | YES |
| `SUSPENDED` | `RETIRED` | YES |
| `ACTIVE` | `APPROVED` | **NO** |
| `RETIRED` | *any* | **NO** |

| Decision | Value |
|---|---|
| **APPROVED ≠ ACTIVE** | **YES** — approval is evidence; activation is org enablement |
| **RETIRED TERMINAL** | **YES** |
| **REPEATED TRANSITION (ACTIVE→activate)** | **200 idempotent no-op — no duplicate audit** |

---

## 7. Admin concurrency & ambiguous retry

| Decision | Value |
|---|---|
| **ADMIN MUTATION CONCURRENCY** | `SELECT FOR UPDATE` + `row_version` / `expected_row_version`; one authoritative transition |
| **GOVERNANCE ADMIN IDEMPOTENCY** | **REQUIRED** |
| **IDEMPOTENT OPERATIONS (same-state transition)** | Provider/site repeated same-state → **200 no-op** |
| **IDEMPOTENCY TABLE** | **`governance_admin_idempotency`** (planned in `0020`) |
| **Idempotency required for** | Profile version create; profile version publish; approval evidence record |
| **Versioned row protection** | Feature activation, deployment gates, provider capability — **`expected_row_version`** |
| **Ambiguous retry (evidence)** | Same `Idempotency-Key` + fingerprint → **one evidence row, one audit, 200 replay** |

---

## 8. Authorization & audiences

| Decision | Value |
|---|---|
| **ORGANIZATION GOVERNANCE AUDIENCE** | **`php-api`** (`require_staff_audience`) |
| **PLATFORM GOVERNANCE AUDIENCE** | **`php-platform`** + `iam.platform` |
| **Platform admin clinical authority** | **NONE** — suspend does not grant PHI/clinical access |
| **Organization isolation** | Membership + org context required — UUID alone insufficient |
| **RBAC role names as authority** | **FORBIDDEN** — permission codes only |

### Permission codes (planned `0020` seed)

| Decision | Exact code |
|---|---|
| **READ PERMISSION** | **`governance.profile.read`** |
| **PROFILE MANAGE PERMISSION** | **`governance.profile.manage`** |
| **APPROVAL RECORD PERMISSION** | **`governance.approval.record`** |
| **FEATURE ACTIVATE PERMISSION** | **`governance.feature.activate`** |
| **PROVIDER CAPABILITY MANAGE PERMISSION** | **`governance.provider.manage`** |

Approval recording and feature activation are **separated** from generic profile management.

---

## 9. Profile version & active pointer

| Decision | Value |
|---|---|
| **PROFILE VERSION MUTABILITY** | **IMMUTABLE** after publish |
| **Version lifecycle** | `DRAFT` → `PUBLISHED` (separate create + publish commands) |
| **PROFILE ACTIVE POINTER** | `organization_governance_profiles.active_published_version_id` |
| **ACTIVE POINTER SAME-PROFILE ENFORCEMENT** | DB trigger: version.profile_id = profile.id AND version.status = PUBLISHED AND org match |
| **Cyclic FK resolution** | Create profiles (nullable pointer) → versions → add pointer FK |
| **Profile `organization_id` immutability** | **YES** (trigger) |

---

## 10. Approval evidence

| Decision | Value |
|---|---|
| **APPROVAL EVIDENCE MUTABILITY** | **APPEND ONLY** |
| Revocation | New **`WITHDRAWN`/`SUPERSEDED`** row — never in-place update |
| Expired evidence | Resolver treats as unsatisfied; historical row retained |
| Duplication on retry | Prevented by **`governance_admin_idempotency`** |

---

## 11. Deployment gates & policy

| Decision | Value |
|---|---|
| **DEPLOYMENT GATE TYPES** | **`CONTROLLER_PROCESSOR_ASSESSMENT`**, **`DPA`** |
| **DEPLOYMENT GATE STATES** | **`NOT_ASSESSED`**, **`PENDING`**, **`SATISFIED`**, **`NOT_APPLICABLE`**, **`EXPIRED`** |
| Gate mutation | Normalized state row **UPDATE** + audit event — **not** new profile version |
| **POLICY SCHEMA V1** | `schema_version: 1`; `encounter_status_policy`; `backdating_policy`; `late_documentation_policy`; `correction_policy` |

---

## 12. DTO contracts

| Surface | Contract |
|---|---|
| Effective context (clinical) | Minimal: `governed_features[]`, safe policy subset — **no** internal denial enums, approver names, DPA, plan internals |
| Management (governance actors) | Rich metadata + `row_version` — no PHI |
| Internal denial codes | Resolver-only — map to safe external errors |

---

## 13. Planned migration `0020` schema (design only)

| **MVP TABLES** | Purpose |
|---|---|
| `provider_capabilities` | Registry + state |
| `provider_capability_required_gates` | Required gate metadata per capability |
| `organization_governance_profiles` | Profile header + active pointer |
| `organization_governance_profile_versions` | Immutable published policy versions |
| `organization_feature_activations` | Site activation state |
| `organization_deployment_gate_states` | Current deployment gate state |
| `governance_approval_evidence` | Append-only approval records |
| `governance_admin_idempotency` | Admin idempotency replay |

**APP_DML:** SELECT + INSERT on evidence/versions/idempotency; SELECT + INSERT + UPDATE on state rows/pointers/provider_state. **No DELETE.**

**Triggers:** immutability on published versions and evidence; binding immutability on org/feature/profile FKs.

---

## 14. MVP APIs (future — not implemented)

| **MVP APIs** | |
|---|---|
| GET | `/api/v1/organizations/{org_id}/governance/effective-context` |
| GET | `/api/v1/organizations/{org_id}/governance/profile` |
| POST | `/api/v1/organizations/{org_id}/governance/profile/versions` |
| POST | `/api/v1/organizations/{org_id}/governance/profile/versions/{id}/publish` |
| POST | `/api/v1/organizations/{org_id}/governance/approvals` |
| POST | `/api/v1/organizations/{org_id}/governance/features/{feature_id}/transition` |
| PUT | `/api/v1/organizations/{org_id}/governance/deployment-gates/{gate_type}` |
| GET | `/api/v1/platform/governance/capabilities` |
| POST | `/api/v1/platform/governance/capabilities/{feature_id}/transition` |

Platform list endpoint returns **empty** immediately after migration — no invented capabilities.

No DELETE endpoints. Typed command DTOs only (`extra = forbid`).

---

## 15. Test strategy (implementation)

| Scenario | Expected |
|---|---|
| Zero provider rows after production migration | **YES** |
| Clinical Note routes independent of OGP | **YES** |
| Synthetic `test_governed_feature` in fixtures only | **YES** |
| Provider `SUSPENDED` / `RETIRED` on synthetic | **`DENIED_PROVIDER`** |
| Missing profile + `governance_required=true` | Deny |
| All gates satisfied on synthetic | Effective available |

No production clinical feature activation required to prove foundation.

---

## 16. Audit

| Event | |
|---|---|
| `GOVERNANCE_PROFILE_VERSION_CREATED` | |
| `GOVERNANCE_PROFILE_VERSION_PUBLISHED` | |
| `GOVERNANCE_APPROVAL_EVIDENCE_RECORDED` | |
| `GOVERNANCE_APPROVAL_EVIDENCE_WITHDRAWN` | |
| `GOVERNANCE_FEATURE_ACTIVATION_CHANGED` | |
| `GOVERNANCE_DEPLOYMENT_GATE_CHANGED` | |
| `GOVERNANCE_PROVIDER_CAPABILITY_CHANGED` | |

State + success audit: **atomic transaction**. Provider capability audits apply **only to registered capabilities**.

---

## 17. Observation & AI (unchanged hard stops)

| Item | Status |
|---|---|
| **OBSERVATION / VITAL SIGNS WRITE DESIGN** | **BLOCKED BY SITE / CLINICAL APPROVAL** |
| **OBSERVATION MIGRATION** | **UNASSIGNED** |
| **manual_vital_signs_write production registration** | **NO** |
| **AI CLINICAL IMPLEMENTATION** | **NOT STARTED** |

---

## 18. Design findings (P0–P3)

| Priority | Finding | Resolution |
|---|---|---|
| ~~**P0**~~ | ~~FALSE KILL-SWITCH ASSURANCE~~ (seeded `clinical_note_write` without runtime enforcement) | **RESOLVED** — empty production seed |
| **P0** | *(none remaining)* | — |
| **P1** | *(none introduced)* | — |
| **P2** | *(none introduced)* | — |
| **P1** (inherited) | Self-approve + activate without separation | Split permissions: `approval.record` vs `feature.activate` |
| **P1** (inherited) | Last-write-wins on mutable governance rows | **`expected_row_version`** |
| **P1** (inherited) | Cyclic FK on profile/version | Three-step migration order |
| **P2** (inherited) | Clinical audit schema churn before governed feature | Defer governance metadata on clinical audit |
| **P2** (inherited) | Effective-context oracle leakage | Minimal DTO |
| **P2** (inherited) | Platform admin PHI boundary | Frozen boundary |
| **P3** (inherited) | Policy schema sprawl | Bounded schema-v1 |
| **P3** (inherited) | Waivers / Redis / AI / facility | Deferred post-MVP |

Inherited DENIED-audit rollback behavior: **unchanged**.

---

## 19. Gate verdict

All placeholders exact. False kill-switch contradiction **resolved**. No registry row may claim enforcement without runtime integration.

```
ORGANIZATION GOVERNANCE PROFILE =
APPROVED FOR IMPLEMENTATION
```

**Scope of approval:** Design and planned migration `20260814_0020` contract only.

**Not approved in this gate:** Creating migration `0020`, backend/frontend changes, IAM/PDP production code changes, Clinical Note Write changes, Observation implementation, AI implementation, commit, tag, or push.

---

## 20. Final status block

```
OGP PROVIDER REGISTRY / KILL-SWITCH
DESIGN CONSISTENCY = COMPLETE

ORGANIZATION GOVERNANCE PROFILE
FINAL PRE-IMPLEMENTATION CONTRACT = COMPLETE

ORGANIZATION GOVERNANCE PROFILE =
APPROVED FOR IMPLEMENTATION

OBSERVATION / VITAL SIGNS WRITE DESIGN =
BLOCKED BY SITE / CLINICAL APPROVAL

OBSERVATION MIGRATION =
UNASSIGNED

MIGRATION 0020 =
NOT CREATED

AI CLINICAL IMPLEMENTATION =
NOT STARTED

NO COMMIT
NO TAG
NO PUSH
```
