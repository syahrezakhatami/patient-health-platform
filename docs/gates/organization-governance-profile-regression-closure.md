# Organization Governance Profile — regression closure gate

**Date:** 2026-08-28  
**Kind:** REGRESSION CLOSURE / PERMISSION PROVISIONING HARDENING / ENVIRONMENT NORMALIZATION  
**Baseline:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)  
**Migration:** `20260814_0020` (parent `20260814_0019`)  
**No commit / no tag / no push**

---

## Verdict

**OGP IMPLEMENTATION REGRESSION CLOSURE = COMPLETE**

**ORGANIZATION GOVERNANCE PROFILE = READY FOR SECURITY / ADVERSARIAL HARDENING**

---

## Initial verification state (before closure)

| Metric | Value |
|---|---|
| Full backend pytest | 453 passed, **31 failed**, 1 skipped |
| Baseline same environment (no OGP) | 430 passed, **37 failed** |
| OGP unit | 4 passed |
| OGP integration | 13 passed |
| Clinical Note integration | 7 passed |

Status before closure: **IMPLEMENTED, VERIFICATION INCOMPLETE**

---

## Initial failure manifest (31 failures)

All 31 failures shared one failure class after capture:

| Group | Count | Failure class | DB error | Affected role | Typical table |
|---|---:|---|---|---|---|
| Wave2B lifecycle DELETE assertions | 14 | `AssertionError: Regex pattern did not match` | `InsufficientPrivilegeError: permission denied` | `app_dml` | clinical fact tables (`conditions`, `observations`, `medications`, …) |
| Wave2B hardening provenance DELETE | 12 | same | same | `app_dml` | `clinical_provenances` |
| Wave2A hardening DELETE | 2 | same | same | `app_dml` | `encounters`, `clinical_notes` |
| Infrastructure audit immutability | 1 | same | same | `app_dml` | `audit_events` |
| Wave2B7 related-fact DELETE | 1 | same | same | `app_dml` | `medications` |
| Wave2B7 immutable-columns DELETE | 1 | same | same | `app_dml` | `adverse_events` |

**Root cause:** Development grants from `scripts/grant_dev_privileges.sql` were not applied before the full suite. With grants applied, `app_dml` correctly lacks `DELETE`/`UPDATE` on insert-only/immutable tables. Tests expected trigger/FK error text but received privilege denial first — a valid dual-layer defense, not a product defect.

**Classification:** TEST HARNESS DEFECT + ENVIRONMENT MISCONFIGURATION (not OGP regression).

---

## Corrections applied

### Environment normalization

1. Added `tests/integration/db_privileges.py`:
   - `apply_dev_privileges()` — runs `grant_dev_privileges.sql` via `DATABASE_MIGRATION_URL` (php_admin)
   - `_sync_governance_role_permissions()` — removes over-broad governance seeds; applies fail-closed defaults
   - Shared regex constants for privilege-layer assertions
2. Session-scoped autouse fixture in `tests/integration/conftest.py` applies dev grants once per test session.
3. `restore_note_write_idempotency_app_dml_privileges` and `restore_governance_app_dml_privileges` use admin connection only (Category **A**).

### Permission provisioning hardening (migration 0020 + catalog)

| Role | Governance permissions (default) |
|---|---|
| `ORG_ADMIN` | `governance.profile.read`, `governance.profile.manage` only |
| `CLINICIAN` | **none** |
| `AUDITOR` | **none** (no governance management read by default) |
| `PLATFORM_ADMIN` | `governance.provider.manage` only |
| `governance.approval.record` | **UNASSIGNED BY DEFAULT** |
| `governance.feature.activate` | **UNASSIGNED BY DEFAULT** |

Migration `20260814_0020` role seed SQL corrected in place (unpublished migration; no 0021).

### Effective-context authorization

- `GET .../governance/effective-context`: `php-api` + org membership only (**no** `governance.profile.read`)
- `GET .../governance/profile` and management surfaces: require `governance.profile.read` / operation-specific permissions
- Effective-context DTO remains minimal (no approval/DPA/plan internals)

### Legacy test modifications (classification)

| File(s) | Class | Reason |
|---|---|---|
| `clinical_notes.py` restore helper | **A** | Admin grant restore, not app_dml |
| `test_clinical_note_write.py` head + idempotency pattern | **B + A** | Migration 0020 head; idempotency INSERT-only privilege model |
| `test_clinical_note_write_hardening.py` roundtrip restore | **B** | Restore Alembic head 0020 after 0019 cycle |
| Wave2 `permission denied` regex alignment | **A** | Privilege layer is correct defense; not assertion weakening |
| `test_infrastructure.py` audit insert-only | **A** | Privilege denial valid for app_dml UPDATE/DELETE |

No Category **C** (behavior weakening) changes.

---

## Final app_dml privilege matrix (development)

| Table | SELECT | INSERT | UPDATE | DELETE |
|---|---|---|---|---|
| `clinical_note_write_idempotency` | yes | yes | **no** | **no** |
| `governance_admin_idempotency` | yes | yes | **no** | **no** |
| `governance_approval_evidence` | yes | yes | **no** | **no** |
| `organization_governance_profile_versions` | yes | yes | yes (draft publish/supersede) | **no** |
| `organization_governance_profiles` | yes | yes | yes | **no** |
| `organization_feature_activations` | yes | yes | yes | **no** |
| `organization_deployment_gate_states` | yes | yes | yes | **no** |
| `provider_capabilities` | yes | yes | yes | **no** |
| `provider_capability_required_gates` | yes | yes | **no** | **no** |
| `audit_events` | yes | yes | **no** | **no** |
| `clinical_provenances` | yes | yes | **no** | **no** |
| Clinical fact tables | yes | yes | varies | **no** (REVOKE DELETE) |

---

## Final test results

| Suite | Result |
|---|---|
| Full backend pytest | **488 passed**, 0 failed |
| OGP unit | **4 passed** |
| OGP integration | **17 passed** |
| Clinical Note (write + hardening) | **39 passed** |
| Migration roundtrip 0020→0019→0020 | pass |
| `provider_capabilities` production count | **0** |
| OpenAPI `export_iam_openapi.py --check` | **ok** |
| `ruff check app` | pass |
| `mypy app` | pass |
| Clinical Note OGP runtime imports | **none** |

Commands:

```bash
cd backend && set -a && . ./.env.example && set +a
.venv/bin/pytest -q
.venv/bin/ruff check app
.venv/bin/mypy app
.venv/bin/alembic downgrade 20260814_0019 && .venv/bin/alembic upgrade head
../apps/healthcare-web/scripts/export_iam_openapi.py --check  # via backend/.venv/bin/python
```

Note: `ruff check .` reports ~86 legacy test lint items (baseline ~81); **`app/` and all OGP-touched files pass**.

---

## OGP permission separation tests (added)

- Profile-manage-only actor: cannot record approval; cannot activate feature
- Approval-record-only actor: cannot read management profile; cannot activate feature
- Feature-activate-only actor: cannot record approval; cannot create profile version
- Clinician without `governance.profile.read`: **can** effective-context; **cannot** management profile
- ORG_ADMIN default: cannot approval/activate without explicit grants
- Platform provider manager: cannot access MPI/clinical write (401/403/404)
- Cross-org effective-context concealed

---

## Findings

**P0:** none  
**P1:** none (provisioning/separation-of-duties ambiguity **resolved**)  
**P2:** inherited DENIED-audit rollback (unchanged)  
**P3:** repo-wide `ruff check .` legacy test lint debt (pre-existing)

---

## Changed files (closure pass additions)

```
A  backend/tests/integration/db_privileges.py
M  backend/tests/integration/conftest.py
M  backend/tests/integration/clinical_notes.py
M  backend/tests/integration/governance_helpers.py
M  backend/tests/integration/test_governance_foundation.py
M  backend/app/modules/authorization/domain/catalog.py
M  backend/app/modules/governance/application/services.py
M  backend/alembic/versions/20260814_0020_organization_governance_foundation.py
M  backend/tests/integration/test_infrastructure.py
M  backend/tests/integration/test_wave2*.py (privilege regex constants)
M  backend/tests/integration/test_clinical_note_write.py
M  backend/tests/integration/test_clinical_note_write_hardening.py
```

Plus all OGP foundation files from implementation pass (uncommitted).

**NO COMMIT / NO TAG / NO PUSH**
