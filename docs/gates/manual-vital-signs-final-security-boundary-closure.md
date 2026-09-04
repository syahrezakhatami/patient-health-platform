# Manual Vital Signs — Final Security Boundary Closure

## Status

**MANUAL VITAL SIGNS FINAL SECURITY BOUNDARY CLOSURE = COMPLETE**

**MANUAL VITAL SIGNS = ENGINEERING HARDENED / READY FOR PROVIDER RELEASE REVIEW**

## Starting red result (closure entry)

| Metric | Count |
|--------|------:|
| Passed | 615 |
| Failed | 15 |
| Errors | 3 |
| Skipped | 1 |

Database role: `app_dml` (`TEST_DATABASE_URL=postgresql+asyncpg://app_dml:app_dml_dev_only@127.0.0.1:5433/php_dev`)

Alembic head at entry: `20260814_0021`

## Failure manifest (closure entry)

Primary failure themes at entry (not an exhaustive node list — resolved before final green):

| Primary category | Representative failures | Root cause |
|------------------|-------------------------|------------|
| **A — Expected security contract change** | Wave 2B suites using generic `POST /observations` with `VITAL_SIGNS` | Public generic staff create of `VITAL_SIGNS` now returns **403** `vital_signs_requires_governed_route` by design |
| **D — Test harness / cleanup defect** | `test_wave2b2a_hardening::test_observation_provenance_fk_and_app_dml_immutability` | Fixture switched to `_generic_exam_observation` (category `EXAM`); immutability assertion still updated category to `EXAM` (no-op, trigger not raised) |
| **D — Test harness** | Clinical read / hardening filters expecting seeded `VITAL_SIGNS` via generic route | Tests updated to seed `EXAM` observations and filter accordingly |
| **G — Unrelated / flaky** | `test_iam_shell_context_hardening::test_success_reads_do_not_audit_or_write_provenance` (intermittent under long runs) | Order-sensitive; passes in isolation and in consecutive full-suite runs after harness fixes |

No failures classified **B** (reservation implementation defect), **C** (locking defect), **E** (privilege drift), or **F** (migration drift) at final verification.

Static migration check (`test_migration_0021_ddl_only_without_provider_seed_or_grants`): **PASS** — `down_revision = 20260814_0020`, single head, no GRANT, no provider seed.

## Generic Observation block layer

| Layer | Role |
|-------|------|
| FastAPI router `POST /api/v1/clinical/observations` | Delegates to application service only |
| **`ClinicalService.create_observation()`** | **Authoritative public staff write boundary** — rejects `ObservationCategory.VITAL_SIGNS` with **403** after `authorize()` |
| Repository / ORM / DB trigger | Unrestricted for trusted internal construction |

This is the narrowest shared public-command boundary: all externally callable generic staff mutation paths route through `create_observation()`.

## Generic Observation caller inventory

| Caller | Classification |
|--------|----------------|
| `app/api/v1/clinical.py::create_observation` | **PUBLIC STAFF API** — reservation enforced |
| `ManualVitalsService.create_measurement` → `ObservationModel(...)` directly | **INTERNAL CLINICAL WORKFLOW** — not via `create_observation()` |
| Integration tests `_generic_exam_observation`, `_heart_rate` helpers | **INTEGRATION** — `_heart_rate` expects 403 on generic route |
| Wave 2B lifecycle / hardening tests (updated) | **INTEGRATION** — use `EXAM` for generic create; dedicated rejection test for `VITAL_SIGNS` |

No alternate public application-service entry bypasses the reservation.

## SECURITY COMPATIBILITY CORRECTION

**Wave 2B.2a public write behavior change (intentional):**

- **Before:** `POST /api/v1/clinical/observations` with `category=VITAL_SIGNS` succeeded for staff with `clinical.observation.create`.
- **After:** Same request returns **403** `vital_signs_requires_governed_route`.
- **Reason:** Same actor could bypass Manual Vitals OGP (GENERIC-OBS-001, P1).
- **Unchanged:** Historical `VITAL_SIGNS` reads, amend, entered-in-error; non-vital generic create (`EXAM`, `OTHER`).

## Same-actor proof

`test_production_dark_both_routes_fail_closed` and `test_generic_vital_signs_staff_create_blocked_without_ogp` use the **same clinician** (`clinical.observation.create` + Manual Vitals route):

| Route | Production-dark result |
|-------|------------------------|
| Dedicated Manual Vitals POST | **403** `manual_vital_signs_unavailable` |
| Generic POST + `VITAL_SIGNS` | **403** `vital_signs_requires_governed_route` |

## Manual Vitals internal write preserved

Dedicated Manual Vitals POST with full test governance creates `Observation` with `category=VITAL_SIGNS` via `ObservationModel` persistence (not `create_observation()`). Verified in foundation and boundary-closure suites.

## Provider / site / profile TOCTOU lock model

**Manual Vitals mutation lock order** (`create_measurement`):

1. `encounters` — `FOR UPDATE` (via `_visible_encounter`)
2. `provider_capabilities` — `FOR UPDATE` (by `feature_id`)
3. `organization_governance_profiles` — `FOR UPDATE` (active pointer)
4. `organization_feature_activations` — `FOR UPDATE` (org + feature)
5. Idempotency claim + clinical write + audit (same transaction)

**Provider transition** (`transition_provider_capability`): locks `provider_capabilities` only.

**Site transition** (`transition_feature_activation`): reads provider unlocked; locks `organization_feature_activations` only.

No inverted global order (provider before activation in Manual Vitals; site transition does not lock provider while holding activation).

Approval evidence: read-only list; no write lock (immutable rows).

**Safety model:** Manual Vitals holds provider row lock through governance re-resolution before commit. If provider SUSPENDED commits first (T2 wins provider lock), T1 re-reads SUSPENDED and denies. If T1 commits first while holding locks, write is valid (acceptable ordering per race interpretation rules).

**Deterministic concurrency evidence:** `test_manual_vitals_boundary_closure.py` — provider suspend, site suspend, profile republish races; `test_provider_row_lock_blocks_concurrent_suspend` (raw PostgreSQL `FOR UPDATE` barrier). **PASS**. No deadlocks observed in repeated runs.

## Test-state cleanup

| Area | Handling |
|------|----------|
| `app_dml` idempotency grants | `restore_clinical_observation_idempotency_app_dml_privileges` autouse in boundary/security suites |
| OGP governance grants | `restore_governance_app_dml_privileges` autouse |
| Provider registry | Synthetic test provider inserted by Manual Vitals helpers; OGP empty-registry tests run **before** Manual Vitals in full suite (documented ordering) |
| Migration head | Downgrade/upgrade tests finish at `20260814_0021` |

## Harness fixes (this closure pass)

| File | Fix |
|------|-----|
| `test_wave2b2a_hardening.py` | Category immutability assertion: `EXAM` → `OTHER` (meaningful change on EXAM-seeded row) |
| `manual-vital-write.test.tsx` | `waitFor` encounter options before `selectOptions` (async load race) |
| Multiple Wave 2B / clinical-read tests (prior pass) | Generic create uses `EXAM`; security rejection tests retain `_heart_rate` |
| Ruff format/import | `manual_vitals_service.py`, boundary closure, helper modules |

## Final verification

### Backend (app_dml, consecutive runs)

| Run | Result |
|-----|--------|
| Full suite #1 | **633 passed**, 0 failed, 0 errors, 1 skipped |
| Full suite #2 | **633 passed**, 0 failed, 0 errors, 1 skipped |
| Full suite #3 (post-format) | **633 passed**, 0 failed, 0 errors, 1 skipped |
| Full suite #4 (post-format) | **633 passed**, 0 failed, 0 errors, 1 skipped |

### Targeted suites

| Suite | Result |
|-------|--------|
| Manual Vitals boundary closure (6) | PASS |
| Manual Vitals security hardening (~39) | PASS |
| Wave 2B.2a Observation | PASS |
| OGP foundation + security hardening (57) | PASS |
| Clinical Note write + hardening (18) | PASS |

### Frontend

| Gate | Result |
|------|--------|
| Vitest | **192 passed** |
| typecheck | PASS |
| build | PASS |

### Quality gates

| Gate | Result |
|------|--------|
| `ruff check app tests` | PASS |
| `ruff format --check app tests` | PASS |
| `mypy app` | PASS |
| OpenAPI `export_iam_openapi.py --check` | PASS |

### Migration / DB

| Check | Result |
|-------|--------|
| Head `current == heads == 20260814_0021` | PASS |
| Migration 0022 | NOT CREATED |
| Static 0021 (no GRANT, no provider seed) | PASS |
| Roundtrip 0021 → 0020 → 0021 | PASS |
| `clinical_observation_write_idempotency` app_dml | SELECT, INSERT only |

## Findings severity (final)

| ID | Initial | Final |
|----|---------|-------|
| GENERIC-OBS-001 | P1 — same actor bypassed OGP via generic route | **RESOLVED** — reservation at `ClinicalService.create_observation()` |
| MV-TOCTOU-001 | P1 risk — stale AVAILABLE after SUSPENDED | **RESOLVED** — row-lock recheck before mutation; concurrency tests PASS |

| Severity | Count | Notes |
|----------|------:|-------|
| P0 | 0 | |
| P1 | 0 | Historical P1 above — resolved |
| P2 | 1 | Inherited DENIED-audit rollback (platform, not Manual Vitals) |
| P3 | 3 | Rate limit deferred; correction UI deferred; BP/SpO2 deferred |

## Frozen verdict lines

```
PROVIDER CAPABILITY PRODUCTION REGISTRY = EMPTY

manual_vital_signs_write = NOT REGISTERED

REAL PRODUCTION MANUAL VITALS AVAILABILITY = DISABLED / FAIL-CLOSED

GENERIC OBSERVATION VITAL_SIGNS BYPASS = RESOLVED

PROVIDER KILL-SWITCH TOCTOU = PASS

SITE ACTIVATION TOCTOU = PASS

MIGRATION 0021 = CREATED

MIGRATION 0022 = NOT CREATED

PROVIDER CLINICAL SAFETY REVIEW = PENDING

PROVIDER RELEASE REGISTRATION = NOT STARTED

SITE APPROVED VITAL ENTRIES = 0

SITE ACTIVATION = PENDING

BLOOD PRESSURE WRITE = DEFERRED

SpO2 = DEFERRED

CORRECTION / AMEND / EIE UI = DEFERRED

CLINICAL NOTE = UNCHANGED

AI CLINICAL IMPLEMENTATION = NOT STARTED

NO COMMIT
NO TAG
NO PUSH
```
