# Manual Vital Signs — Implementation Gate

## Baseline

- **HEAD:** `39909b44a1bad737839b9267a068d8bb0fa0b389`
- **OGP frozen tag:** `organization-governance-profile-foundation-frozen` → `d449ffed6bd314edac3964f1c6c69bb51955a8db`
- **Alembic head after this pass:** `20260814_0021` (down_revision `20260814_0020`)
- **Single head:** yes

## Migration 0021

- **Revision:** `20260814_0021_clinical_observation_write_idempotency`
- **Table:** `clinical_observation_write_idempotency`
- **Scope:** DDL only; no provider seed, no GRANT in Alembic
- **Dev grants:** `backend/scripts/grant_dev_privileges.sql` — `app_dml` SELECT+INSERT only

## Provider registry (production-dark)

- **Production migration seed:** none
- **`manual_vital_signs_write`:** not registered by migration
- **Runtime without site activation:** GET write context `available=false`; POST deny (403)

## Static catalog

- **Location:** `backend/app/modules/clinical/domain/vital_signs_catalog.py`
- **Version:** `manual-vitals-mvp-v1`
- **Entries:** `heart_rate`, `respiratory_rate`, `body_temperature`, `body_weight`, `body_height`
- **Deferred:** BP, SpO2

## OGP policy schema v2

- **Models:** `GovernancePolicyDocumentV2`, `ManualVitalSignsPolicy` in `policy_schema.py`
- **Block:** `manual_vital_signs.catalog_version` + `approved_measurements` (unique, catalog-bound)
- **V1 compatibility:** unchanged; absent block → Manual Vitals deny

## Approval scope fingerprint

- **Implementation:** `backend/app/modules/clinical/domain/manual_vitals_approval.py`
- **Format:** `{catalog_version}#sha256:{64-hex}` over canonical sorted JSON payload

## API routes

- **GET** `/api/v1/organizations/{org_id}/clinical/manual-vitals/measurements` — effective write context
- **POST** same path — create measurement (`expected_patient_identity_id`, `encounter_id`, `measurement_key`, `value`, `effective_at` + `Idempotency-Key`)

## Backend service

- **Service:** `ManualVitalsService` — OGP fail-closed, subset enforcement, approval binding, Decimal validation, idempotency, encounter/patient/facility safety
- **Observation shape:** FINAL `VITAL_SIGNS` NUMERIC; server-owned LOINC/UCUM
- **Idempotency replay:** re-checks current auth, provider/site readiness, and approved measurement subset

## Healthcare Web

- **Form:** `apps/healthcare-web/src/chart/vitals/ManualVitalForm.tsx` in Observations section
- **Gating:** server write context + `clinical.observation.create`; hidden when unavailable
- **PHI:** memory-only values; mutation `retry=false`, `gcTime=0`

## Tests

- **Unit:** `tests/unit/test_manual_vitals_domain.py` (28)
- **Integration foundation:** `tests/integration/test_manual_vitals_foundation.py` (9)
- **Integration hardening / closure:** `tests/integration/test_manual_vitals_hardening.py` (22)
- **Integration security / clinical-safety:** `tests/integration/test_manual_vitals_security_hardening.py` (39)
- **Frontend:** `apps/healthcare-web/src/chart/vitals/manual-vital-write.test.tsx` (8)

## Quality gates (regression closure pass)

| Gate | Result |
|------|--------|
| ruff check | PASS |
| mypy app | PASS |
| backend full suite | 588 passed |
| frontend typecheck | PASS |
| frontend tests | 190 passed |
| frontend build | PASS |
| OpenAPI POST schema bounded | PASS |
| migration roundtrip 0021 | PASS |

## Quality gates (security / clinical-safety hardening pass)

| Gate | Result |
|------|--------|
| ruff check | PASS |
| mypy app | PASS |
| backend full suite | 627 passed |
| frontend typecheck | PASS |
| frontend tests | 192 passed |
| frontend build | PASS |
| OpenAPI `--check` | PASS |
| migration roundtrip 0021 | PASS (unchanged) |

## Findings

- **P0:** 0
- **P1:** 0
- **P2:** inherited `DENIED`-audit rollback; generic Observation OGP boundary (documented, pre-existing API)
- **P3:** correction UI, BP, SpO2, rate limiting — deferred
- **PROVIDER_RELEASE_GATE:** provider clinical safety review pending
- **SITE_ACTIVATION_GATE:** site approved vital entries = 0

## Regression closure

See `manual-vital-signs-implementation-regression-closure.md` for full evidence matrix.

**MANUAL VITAL SIGNS IMPLEMENTATION REGRESSION CLOSURE = COMPLETE**

## Security / clinical-safety hardening

See `manual-vital-signs-security-clinical-safety-hardening.md` for adversarial matrix and boundary analysis.

**MANUAL VITAL SIGNS SECURITY / CLINICAL-SAFETY HARDENING = COMPLETE**

**MANUAL VITAL SIGNS = ENGINEERING HARDENED / READY FOR PROVIDER RELEASE REVIEW**
