# Organization Governance Profile — final freeze

**Date:** 2026-08-28  
**Kind:** FINAL FREEZE / PUBLISH  
**Published parent SHA:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c`  
**Published parent tag:** `provider-governance-foundation-frozen`  
**Software capability parent:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)  
**Canonical freeze tag:** `organization-governance-profile-foundation-frozen`  
**Final commit SHA:** resolve via `git rev-parse organization-governance-profile-foundation-frozen`

---

## Verdict

**ORGANIZATION GOVERNANCE PROFILE FOUNDATION = FROZEN**

**ORGANIZATION GOVERNANCE PROFILE FOUNDATION = PUBLISHED**

**OGP SECURITY ASSURANCE = PASS WITH NO ACTIVE P0 / P1**

---

## Scope frozen

Organization Governance Profile backend foundation only:

- Migration `20260814_0020` (8 tables, triggers, five permission codes, **empty** provider seed)
- Provider capability registry infrastructure (production registry **empty**)
- Organization governance profile/version storage
- Deployment gate state, feature activation, approval evidence
- Governance admin idempotency
- Organization + platform management APIs
- Effective-context read API (minimal, no management permission)
- Governance resolver (not wired to any real clinical capability)
- Permission catalog additions with fail-closed default provisioning
- Development grant script updates
- Integration/unit/security tests

**Not included:** Observation, AI, frontend governance UI, Clinical Note OGP integration, facility overrides, Redis cache.

---

## Migration

| Item | Value |
|---|---|
| Revision | `20260814_0020` |
| Down revision | `20260814_0019` |
| Alembic heads | **1** (`20260814_0020`) |
| Production provider seed | **0 rows** |

### Tables (8)

1. `provider_capabilities`
2. `provider_capability_required_gates`
3. `organization_governance_profiles`
4. `organization_governance_profile_versions`
5. `organization_feature_activations`
6. `organization_deployment_gate_states`
7. `governance_approval_evidence`
8. `governance_admin_idempotency`

Fresh install and roundtrip (`0020 → 0019 → 0020`) verified.

---

## Provider registry semantics

- Production migration seeds **zero** provider capability rows
- Missing provider row does **not** globally deny existing application features
- Only explicitly integrated capabilities consult the resolver
- **Clinical Note is not OGP-enforced**

---

## Permissions

Codes: `governance.profile.read`, `governance.profile.manage`, `governance.approval.record`, `governance.feature.activate`, `governance.provider.manage`

### Default provisioning (frozen)

| Role | Governance permissions |
|---|---|
| ORG_ADMIN | `governance.profile.read`, `governance.profile.manage` |
| CLINICIAN | none |
| AUDITOR | none |
| PLATFORM_ADMIN | `governance.provider.manage` (+ existing `iam.platform`) |
| approval.record | **unassigned by default** |
| feature.activate | **unassigned by default** |

---

## Audiences & authorization

| Surface | Contract |
|---|---|
| Org governance APIs | `php-api` + staff org membership |
| `GET effective-context` | org membership only — **no** `governance.profile.read` |
| `GET profile` / management | `governance.profile.read` + operation permissions |
| Platform capabilities | `php-platform` + `governance.provider.manage` |
| Platform admin | no clinical/MPI permissions from provider manage |

---

## State machines

- **Provider:** AVAILABLE ↔ SUSPENDED → RETIRED (terminal); same-state no-op
- **Site activation:** NOT_CONFIGURED → PENDING_APPROVAL → APPROVED → ACTIVE ↔ SUSPENDED → RETIRED
- **Profile version:** DRAFT → PUBLISHED (immutable); active pointer same-profile DB defense
- **Deployment gates:** CONTROLLER_PROCESSOR_ASSESSMENT, DPA; states NOT_ASSESSED/PENDING/SATISFIED/NOT_APPLICABLE/EXPIRED

---

## Idempotency & concurrency

- Profile create, publish, approval record: Idempotency-Key required
- Scope: organization + actor + operation
- Current authorization checked on replay
- Real PostgreSQL same-key concurrency: one resource, one audit, one idempotency row

---

## DB privileges (app_dml)

| Table | Privileges |
|---|---|
| `governance_admin_idempotency` | SELECT, INSERT |
| `governance_approval_evidence` | SELECT, INSERT |
| `organization_governance_profile_versions` | SELECT, INSERT, UPDATE (draft publish) |
| State/header tables | SELECT, INSERT, UPDATE as required |
| `clinical_note_write_idempotency` | SELECT, INSERT (unchanged frozen model) |

No DELETE/TRUNCATE on governance tables.

---

## Security hardening

- Cross-org IDOR matrix: PASS
- Audience separation: PASS
- Permission separation-of-duties: PASS
- Effective-context oracle safety: PASS
- Policy schema bounded (v1, extra=forbid): PASS

### SEC-001 (resolved)

Approval evidence POST returned 500 due to raw string status in mapper. Fixed: `ApprovalEvidenceStatus(row.status)` in repository mapping. Regression tested.

---

## Quality gates (final)

| Check | Result |
|---|---|
| Full backend pytest | **528 passed, 0 failed** |
| OGP unit | 4 passed |
| OGP integration | 17 passed |
| OGP security adversarial | 40 passed |
| OpenAPI `--check` | pass |
| `ruff check app` | pass |
| `mypy app` | pass (149 files) |
| Migration roundtrip | pass |
| Clinical Note runtime OGP imports | **none** |
| Clinical Note functional regression | pass (included in full suite) |

---

## Lineage

```
clinical-note-write-frozen (c55d2591)
  → provider-governance-foundation-frozen (c3590dd1)
    → organization-governance-profile-foundation-frozen (<NEW SHA>)
```

---

## Post-freeze product status

| Capability | Status |
|---|---|
| Provider Governance Foundation | FROZEN |
| Organization Governance Profile Foundation | FROZEN |
| Clinical Note Write | FROZEN (independent of OGP) |
| Manual Vital Signs / Observation | BLOCKED |
| AI Clinical | NOT STARTED |
| Frontend Governance UI | NOT IMPLEMENTED |

---

## Findings

| Severity | Item |
|---|---|
| **P0** | none |
| **P1** | none (SEC-001 resolved) |
| **P2** | inherited DENIED-audit rollback |
| **P3** | approval withdrawal API deferred; governance rate-limiting deferred; facility overrides deferred; Redis cache deferred; governance admin UI deferred; AI runtime deferred |

---

## Gate documents

- Design: `docs/architecture/organization-governance-profile-design.md`
- Design approval: `docs/gates/organization-governance-profile-design-approval.md`
- Implementation: `docs/gates/organization-governance-profile-implementation-gate.md`
- Regression closure: `docs/gates/organization-governance-profile-regression-closure.md`
- Security hardening: `docs/gates/organization-governance-profile-security-hardening.md`
- **This freeze:** `docs/gates/organization-governance-profile-final-freeze.md`
