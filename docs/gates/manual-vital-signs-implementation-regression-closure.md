# Manual Vital Signs — Implementation Regression Closure

## Baseline

- **Git baseline:** `39909b44a1bad737839b9267a068d8bb0fa0b389`
- **OGP frozen tag:** `organization-governance-profile-foundation-frozen` → `d449ffed6bd314edac3964f1c6c69bb51955a8db`
- **Alembic head:** `20260814_0021` (down_revision `20260814_0020`, single head)
- **Migration 0022:** not created
- **Working tree:** uncommitted (no commit/tag/push in this pass)

## Scope of diff vs baseline

All changes belong to Manual Vitals backend, migration `0021`, OGP policy v2, grant script, Healthcare Web, tests, and gate docs. No unrelated capability.

## Test helper review

| Helper | Classification | Usage |
|--------|----------------|-------|
| `seed_governance_actor` | **MULTI-ORG SECURITY FIXTURE** | Creates governance actor in a **new** organization (OGP cross-org tests) |
| `seed_governance_actor_for_organization` | **SUCCESS-PATH SAME-ORG FIXTURE** | Adds governance permissions to an **existing** clinician organization (Manual Vitals site activation) |

Cross-org Manual Vitals tests construct independent organizations explicitly. Success-path helpers do **not** globally force all governance actors into the clinician organization.

## Migration 0021

| Check | Result |
|-------|--------|
| Static: DDL only, no GRANT, no provider seed | PASS (`test_migration_0021_ddl_only_without_provider_seed_or_grants`) |
| Fresh install through head on repository PostgreSQL | PASS (Alembic at `20260814_0021`; table present) |
| Roundtrip `0021 → 0020 → 0021` | PASS (`test_zz_migration_0021_downgrade_upgrade_roundtrip`) |
| Table recreated after re-upgrade | PASS |
| Constraints/trigger/index present | PASS (`uq_clinical_observation_write_idempotency_scope`, immutability trigger) |

## DB privileges (`scripts/grant_dev_privileges.sql`)

| Table | `app_dml` privileges |
|-------|----------------------|
| `clinical_observation_write_idempotency` | `SELECT`, `INSERT` only |

Verified in `test_observation_idempotency_app_dml_privileges`. No UPDATE/DELETE/TRUNCATE.

## Provider production registry

| Check | Result |
|-------|--------|
| Migration `0021` seeds `provider_capabilities` | **None** |
| Migration `0020` production seed for `manual_vital_signs_write` | **None** |
| Fresh migration chain design | Empty registry at install |
| Test DB after integration fixtures | May contain synthetic `manual_vital_signs_write` row from `seed_manual_vitals_provider` (immutable trigger prevents delete); OGP empty-registry tests run before Manual Vitals tests in full suite |

## Production-dark behavior (no site activation)

| Case | HTTP | Body / effect |
|------|------|----------------|
| GET write context | `200` | `{ available: false, catalog_version: null, feature_version: null, measurements: [] }` |
| POST measurement | `403` | `manual_vital_signs_unavailable`; 0 new observations; 0 new idempotency rows |

## Production-dark frontend

| Case | Result |
|------|--------|
| Write context unavailable | Form hidden (`test_production_dark` / `hides the form when manual vitals are unavailable`) |
| Server subset only | UI exposes exactly backend-returned measurement keys (`subset context` test) |

## Real PostgreSQL concurrency / idempotency

| Scenario | Result |
|----------|--------|
| Same key, same payload (concurrent) | 1 observation, 1 idempotency row, 1 `OBSERVATION_CREATED` audit (`test_concurrent_same_key_exact_row_counts`) |
| Same key, `1.0` then `1.00` (same `effective_at`) | Replay; same observation id |
| Same key, `72` then `73` | `409 idempotency_key_conflict`; 1 observation |
| Different keys (concurrent) | 2 distinct observations |
| Replay after permission revoked | `403` (no replay) |
| Replay after provider `SUSPENDED` | `403` |
| Replay after site policy excludes measurement | `403` (replay re-validates approved subset) |
| Replay after profile republish excluding prior measurement | `403` |

## Cross-org / patient / facility / Encounter

| Matrix | Result |
|--------|--------|
| Org A actor → Org B GET/POST | `404` concealed |
| Org A approval with identical scope hash | Does **not** authorize Org B |
| Profile version binding (approval on v1, active v2) | `403` |
| Wrong patient on encounter | `404 not_found` |
| Merged MPI historical encounter | Write succeeds; persisted `patient_identity_id` = historical encounter identity |
| RETIRED identity | `409` |
| Facility match / mismatch / org-wide inherit | `200` with attributed facility / `403` on mismatch |
| Encounter: PLANNED allow/deny, IN_PROGRESS, FINISHED deny/late-doc allow, CANCELLED, EIE | Documented in `test_encounter_status_matrix` |

## Policy / catalog / Decimal / OpenAPI

| Check | Result |
|-------|--------|
| OGP v1 compatibility | Manual Vitals absent; deny |
| OGP full suite (with Manual Vitals tests ordered after) | PASS in full backend run |
| Five catalog entries exact | Unit tests |
| Approval scope `manual-vitals-mvp-v1#sha256:{64}` ≤ 128 chars | Unit + parametric per entry |
| Decimal boundaries / NaN / Inf / scale overflow | Unit tests |
| `effective_at` timezone canonicalization | Integration + unit fingerprint |
| POST extra fields (`loinc`, `unit`, …) | `422` |
| OpenAPI POST schema fields | `expected_patient_identity_id`, `encounter_id`, `measurement_key`, `value`, `effective_at` only |

## Audit / provenance

Successful Manual Vitals write records:

- **Recorder:** authenticated clinician (`recorder_id`)
- **Audit action:** `OBSERVATION_CREATED`
- **Metadata:** `feature_id`, `feature_version`, `catalog_version`, `measurement_key`, `governance_profile_version_id`, category/status
- **Provenance:** observation linked to provenance row
- **Atomicity:** forced audit INSERT denial → 0 committed observations, 0 idempotency rows

## Application DB role

Integration tests use `app_dml` (`test_app_dml_database_role_used`).

## Frontend server authority

`ManualVitalForm` renders only backend `measurements[]`; labels are i18n-only. Mutation `retry: false`. Query invalidation on success for observations/timeline/summary.

## Regression counts (this pass)

| Suite | Result |
|-------|--------|
| Backend full pytest | **588 passed**, 0 failed |
| Healthcare Web vitest | **190 passed**, 0 failed |
| Frontend typecheck | PASS |
| Frontend build | PASS |
| ruff check | PASS |
| mypy app | PASS (155 files) |
| OpenAPI manual vitals POST schema | PASS |
| Clinical Note tests | PASS (included in full backend) |
| Observation tests | PASS (included in full backend) |

## Findings classification

| Severity | Count | Notes |
|----------|-------|-------|
| **P0** | 0 | — |
| **P1** | 0 | — |
| **P2** | 1 (inherited) | `test_inherited_denied_audit_rollback_still_present` — product-access tenancy hardening; not introduced by Manual Vitals |
| **P3** | deferred scope | Correction/amend/EIE UI, BP workflow, SpO2, abuse/rate limiting |

## Release gates (not engineering defects)

| Gate | Status |
|------|--------|
| Provider clinical safety review | **PENDING** (`PROVIDER_RELEASE_GATE`) |
| Site clinical/termininology approval | **PENDING** (`SITE_ACTIVATION_GATE`) |

## Verdict

**MANUAL VITAL SIGNS IMPLEMENTATION REGRESSION CLOSURE = COMPLETE**

**MANUAL VITAL SIGNS = READY FOR SECURITY / CLINICAL-SAFETY HARDENING**

## Security hardening follow-up

Subsequent adversarial pass: `manual-vital-signs-security-clinical-safety-hardening.md`

- Backend: 627 passed ( +39 security tests )
- Frontend: 192 passed ( +2 stale-context / org-switch tests )
- P0/P1: 0 new defects
