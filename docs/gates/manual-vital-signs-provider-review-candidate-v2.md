# Manual Vital Signs — Provider Review Candidate v2

**Kind:** ENGINEERING REVIEW CANDIDATE RECORD  
**Date:** 2026-09-04  
**Canonical candidate tag:** `manual-vital-signs-provider-review-candidate-v2`

This candidate supersedes `manual-vital-signs-provider-review-candidate-v1` (`cabfea6a63e3f27825df5f0a104a3278e1665f2b`) for human provider clinical-safety review.

v1 remains an immutable historical tag. It must **not** receive provider clinical-safety approval because of a UI unit-binding defect (catalog-position fallback).

This is **not** provider registration, production release, site activation, or clinical approval. The candidate remains **production-dark**.

Resolved candidate SHA is the commit this tag peels to after publication.

---

## Why v2 exists

Candidate v1 displayed a unit via:

```text
selectedMeasurement = find(measurementKey) ?? measurements[0]
```

`measurementKey` is React state, initialized to `""` and only later set to the first catalog key in a `useEffect`. That allowed an intermediate (and reset) render to show the **first catalog unit** without an authoritative selected `measurement_key`.

Required invariant:

> DISPLAYED UNIT MUST ALWAYS CORRESPOND TO THE CURRENT AUTHORITATIVE SELECTED measurement_key.

v2 binds unit only by exact key lookup. No selected key → no unit. Submit uses the bound catalog object’s `measurement_key`, not an unmatched stale string.

---

## Verification (this candidate)

| Check | Result |
|-------|--------|
| Targeted vitals tests | 16 passed |
| Full frontend suite | 200 passed |
| `npm run typecheck` | PASS |
| `npm run build` | PASS |
| Migration 0022 | **NOT CREATED** |
| Provider registration | **ABSENT** |

---

## Identity

| Field | Value |
|-------|-------|
| Parent / source baseline | `39909b44a1bad737839b9267a068d8bb0fa0b389` |
| Superseded candidate | `manual-vital-signs-provider-review-candidate-v1` @ `cabfea6a63e3f27825df5f0a104a3278e1665f2b` |
| Candidate tag | `manual-vital-signs-provider-review-candidate-v2` |
| Resolved candidate SHA | **from tag after publication** |
| Alembic | `20260814_0021` (no 0022) |
| Planned feature ID | `manual_vital_signs_write` |
| Planned feature version | `1.0.0` |
| Provider catalog | `manual-vitals-mvp-v1` |
| Production registration | **ABSENT** |
| Production availability | **DISABLED / FAIL-CLOSED** |

---

## Human-review package

Reviewer must record:

- candidate tag: `manual-vital-signs-provider-review-candidate-v2`
- resolved SHA from that tag
- feature: `manual_vital_signs_write` @ `1.0.0`
- catalog: `manual-vitals-mvp-v1`
- Alembic: `20260814_0021`

Human decision fields remain **PENDING**. Do not invent approval.

See:

- `docs/governance/manual-vital-signs-provider-clinical-safety-review.md`
- `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md`
- `docs/gates/manual-vital-signs-provider-release-readiness.md`

---

## Distinct verdicts

```
ENGINEERING REVIEW CANDIDATE V1 = HISTORICAL / NOT ELIGIBLE FOR HUMAN APPROVAL

ENGINEERING REVIEW CANDIDATE V2 = PUBLISHED

PROVIDER CLINICAL SAFETY REVIEW = PENDING HUMAN SIGN-OFF

PROVIDER PRODUCTION REGISTRATION = BLOCKED
```
