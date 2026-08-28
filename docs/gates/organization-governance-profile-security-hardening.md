# Organization Governance Profile — security / adversarial hardening gate

**Date:** 2026-08-28  
**Kind:** SECURITY HARDENING — not freeze  
**Baseline:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)  
**Migration:** `20260814_0020` (parent `20260814_0019`)  
**Regression closure:** `docs/gates/organization-governance-profile-regression-closure.md`  
**No commit / no tag / no push**

---

## Verdict

**OGP SECURITY / ADVERSARIAL HARDENING = COMPLETE**

**ORGANIZATION GOVERNANCE PROFILE = READY FOR FINAL FREEZE VERIFICATION**

---

## Pre-hardening baseline

| Check | Result |
|---|---|
| Full backend pytest | 488 passed, 0 failed |
| Alembic head | `20260814_0020` (one head) |
| Production provider registry | 0 rows (no clinical/observation seed) |

---

## Attack categories executed

| Family | Result |
|---|---|
| AUTH / TENANT / IDOR | Cross-org matrix (7 endpoints), resource UUID publish attack, membership required |
| AUDIENCE | `php-api` rejected on platform API; `php-platform` rejected on org API |
| PERMISSION / SOD | Single-permission principals; ORG_ADMIN lacks approval/activate by default |
| IDEMPOTENCY | Cross-actor, cross-org, cross-operation, fingerprint conflict, current-auth replay (403 after revoke) |
| CONCURRENCY | Same-key profile create (PostgreSQL) |
| STATE_MACHINE | Provider + activation illegal/no-op edges (parametrized) |
| POLICY / INPUT | Extra fields, enum tampering, `extra=forbid`, gate type spoofing, feature_id injection |
| ORACLE | Effective-context key safety (no denial/DPA/approval internals) |
| DB_PRIVILEGE | `app_dml` cannot UPDATE idempotency rows |
| PROVIDER | Synthetic suspend deny; missing row = NOT_REGISTERED; governance_required fail-closed |
| CLINICAL_BOUNDARY | Platform admin cannot access MPI/clinical note create |
| OPENAPI | No DELETE on governance routes |
| MIGRATION | Roundtrip 0020→0019→0020 verified |

---

## Security defects found and fixed

### SEC-001 (P1): Approval evidence status enum mapping

| Field | Detail |
|---|---|
| Attack | `POST .../governance/approvals` after successful record |
| Expected | 200 with status string |
| Actual | 500 `AttributeError: 'str' object has no attribute 'value'` |
| Root cause | `_map_evidence` stored raw DB string instead of `ApprovalEvidenceStatus` |
| Fix | `backend/app/modules/governance/infrastructure/repositories.py` — map `ApprovalEvidenceStatus(row.status)` |
| Regression | `test_idempotency_cross_operation_no_replay` |

---

## Final quality gates

| Check | Result |
|---|---|
| Full backend pytest | **528 passed, 0 failed** |
| OGP unit | 4 passed |
| OGP integration (foundation) | 17 passed |
| OGP security adversarial | **40 passed** (parametrized cases counted as individual tests) |
| Clinical Note | all pass (included in full suite) |
| Migration roundtrip | pass |
| OpenAPI `--check` | pass |
| `ruff check app` | pass |
| `mypy app` | pass (149 files) |
| Clinical Note OGP imports | **none** |

---

## Authorization contracts (verified)

| Surface | Contract |
|---|---|
| Effective-context | `php-api` + org membership only; no `governance.profile.read` |
| Management profile | `governance.profile.read` + org context |
| ORG_ADMIN default | `governance.profile.read`, `governance.profile.manage` only |
| CLINICIAN / AUDITOR default | no governance permissions |
| approval.record / feature.activate | unassigned by default |
| Platform provider manage | `php-platform` + `governance.provider.manage`; no clinical/MPI |

---

## Idempotency scope (verified)

- Same actor/org/operation/key/fingerprint → replay
- Fingerprint mismatch → 409
- Cross-actor same key → distinct resources
- Cross-org same actor/key → distinct resources
- Cross-operation same key → distinct resources (no cross-replay)
- Permission revoked before replay → 403 (current auth checked first)

---

## DB privileges (verified)

| Table | app_dml |
|---|---|
| `governance_admin_idempotency` | SELECT, INSERT (UPDATE denied) |
| `governance_approval_evidence` | SELECT, INSERT |
| `clinical_note_write_idempotency` | SELECT, INSERT (unchanged frozen model) |

---

## Findings

| Severity | Item |
|---|---|
| **P0** | none |
| **P1** | none remaining (SEC-001 fixed) |
| **P2** | inherited DENIED-audit rollback |
| **P3** | approval withdrawal API deferred; rate-limiting not governance-specific |

---

## Changed files (this pass)

```
M  backend/app/modules/governance/infrastructure/repositories.py
A  backend/tests/integration/test_governance_security_hardening.py
A  docs/gates/organization-governance-profile-security-hardening.md
M  docs/gates/organization-governance-profile-implementation-gate.md
```

---

## Status declarations

**PROVIDER CAPABILITY PRODUCTION REGISTRY = EMPTY**

**REAL CLINICAL CAPABILITY OGP ENFORCEMENT = NONE**

**CLINICAL NOTE OGP RUNTIME DEPENDENCY = NONE**

**CLINICAL NOTE BEHAVIOR = UNCHANGED**

**OBSERVATION / VITAL SIGNS WRITE = BLOCKED**

**OBSERVATION MIGRATION = UNASSIGNED**

**AI CLINICAL IMPLEMENTATION = NOT STARTED**

**FRONTEND GOVERNANCE UI = NOT IMPLEMENTED**

**NO COMMIT / NO TAG / NO PUSH**
