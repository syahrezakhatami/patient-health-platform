# Manual Vital Signs — Security / Clinical-Safety Hardening

## Status

**MANUAL VITAL SIGNS FINAL SECURITY BOUNDARY CLOSURE = COMPLETE**

**MANUAL VITAL SIGNS = ENGINEERING HARDENED / READY FOR PROVIDER RELEASE REVIEW**

See also: [manual-vital-signs-final-security-boundary-closure.md](./manual-vital-signs-final-security-boundary-closure.md)

## Baseline

| Item | Value |
|------|-------|
| Git baseline | `39909b44a1bad737839b9267a068d8bb0fa0b389` |
| Alembic head | `20260814_0021` (down_revision `20260814_0020`, single head) |
| Migration 0022 | not created |
| Post-closure backend | **633 passed / 0 failed / 0 errors / 1 skipped** (two consecutive full `app_dml` runs) |
| Post-closure frontend | **192 passed / 0 failed** |

## Security boundary corrections (closure pass)

### GENERIC-OBS-001 — RESOLVED (P1)

| Item | Detail |
|------|--------|
| Finding | Same staff actor (`php-api`, `clinical.observation.create`) could create heart-rate LOINC via `POST /api/v1/clinical/observations` with `category=VITAL_SIGNS` without OGP |
| Fix layer | `ClinicalService.create_observation()` — after `authorize()`, before identity/encounter work |
| Error | **403** `vital_signs_requires_governed_route` |
| Internal bypass | Manual Vitals writes `ObservationModel` directly; not affected |
| Compatibility | **SECURITY COMPATIBILITY CORRECTION** — public generic `VITAL_SIGNS` write prohibited; reads/amend/EIE unchanged |

Mandatory regression tests:

- Generic staff POST + `VITAL_SIGNS` → rejected
- Generic staff POST + `EXAM` → succeeds (frozen non-vital behavior)
- Manual Vitals dedicated POST (governed test site) → succeeds, creates `VITAL_SIGNS`
- Production-dark: same actor, dedicated POST denied; generic `VITAL_SIGNS` denied

### MV-TOCTOU-001 — RESOLVED (P1 hardening)

| Item | Detail |
|------|--------|
| Risk | Stale `AVAILABLE` provider / active site state committed after authoritative SUSPENDED |
| Fix | `_resolve_write_readiness_for_mutation()` — `FOR UPDATE` on provider capability, org profile header, feature activation; full layer re-resolution before idempotency claim |
| Lock order | encounter → provider → profile → activation |
| Evidence | `test_manual_vitals_boundary_closure.py` concurrent provider/site/profile races; provider row-lock barrier test |

Approval evidence: existence check only (immutable); no unnecessary lock.

## Generic Observation boundary (final)

**Conclusion:** Generic public staff `POST /api/v1/clinical/observations` **must not** create `VITAL_SIGNS`. Governed production path is Manual Vitals dedicated route only.

OpenAPI request schema still lists `VITAL_SIGNS` in category enum (read/historical models); runtime write rejection is semantic, documented here.

## Attack matrix (summary)

| Category | Result | Evidence |
|----------|--------|----------|
| AUTH / AUDIENCE | PASS | staff audience matrix |
| MULTI-ORG IDOR | PASS | cross-org concealed 404 |
| OGP BYPASS | PASS | forged approval, stale profile, gates, suspend mid-flow |
| GENERIC OBS BYPASS | **RESOLVED** | same-actor production-dark + `_heart_rate` rejection |
| PROVIDER TOCTOU | PASS | concurrent suspend + row lock barrier |
| SITE TOCTOU | PASS | concurrent activation suspend |
| PROFILE TOCTOU | PASS | concurrent republish race |
| IDEMPOTENCY / CONCURRENCY | PASS | hardening + boundary closure |
| PRODUCTION-DARK | PASS | unregistered provider fail-closed |
| MIGRATION / DB PRIV | PASS | 0021 roundtrip; app_dml SELECT/INSERT only on idempotency table |

## Quality gates (post-closure)

| Gate | Result |
|------|--------|
| ruff check app tests | PASS |
| ruff format --check app tests | PASS |
| mypy app | PASS |
| backend full suite (app_dml, ×2 consecutive) | 633 passed each |
| frontend tests | 192 passed |
| frontend typecheck / build | PASS |
| OpenAPI `--check` | PASS |
| Alembic single head 0021 | PASS |

## Findings severity

| Severity | Count | Notes |
|----------|-------|-------|
| P0 | 0 | |
| P1 | 0 | GENERIC-OBS-001 and MV-TOCTOU-001 resolved (listed above) |
| P2 | 1 | Inherited DENIED-audit rollback (platform, not Manual Vitals) |
| P3 | 3 | Manual Vitals rate limit deferred; correction UI deferred; BP/SpO2 deferred |

## Gates not passed (by design)

| Gate | State |
|------|-------|
| Provider Clinical Safety Review | PENDING |
| Provider release registration | NOT STARTED |
| Site approved vital entries | 0 |
| Site activation | PENDING |
| Migration 0022 | NOT CREATED |
| Commit / tag / push | NOT DONE |
