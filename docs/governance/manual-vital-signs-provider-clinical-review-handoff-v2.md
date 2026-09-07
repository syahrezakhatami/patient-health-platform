# Manual Vital Signs — Human Provider Clinical Safety Review Handoff (Candidate v2)

**Kind:** HUMAN REVIEW ENTRY POINT — engineering package lock
**Date:** 2026-09-08
**This document does not record a clinical decision.**

```
ENGINEERING REVIEW CANDIDATE =
manual-vital-signs-provider-review-candidate-v2

PROVIDER CLINICAL SAFETY REVIEW =
PENDING HUMAN SIGN-OFF

PROVIDER REGISTRATION =
BLOCKED

SITE ACTIVATION =
PENDING
```

The next step is **not** another Cursor engineering pass.
The next step is an **actual human** provider clinical-safety review of the candidate below.
Cursor / engineering must **not** perform, simulate, or invent that approval.

---

## 1. Candidate the reviewer must use

| Field | Value |
|-------|-------|
| Candidate tag | `manual-vital-signs-provider-review-candidate-v2` |
| Candidate SHA | `0d1882d287df3108a797fe6957fb21761ce80cdd` |
| Feature ID | `manual_vital_signs_write` |
| Feature version | `1.0.0` |
| Provider catalog | `manual-vitals-mvp-v1` |
| Alembic | `20260814_0021` (down `20260814_0020`) |
| Migration 0022 | **NOT CREATED** |
| Production registry | **EMPTY** — capability **NOT REGISTERED** |
| Production availability | **DISABLED / FAIL-CLOSED** |
| Site-approved vital entries | **0** |

Verify locally:

```bash
git rev-parse manual-vital-signs-provider-review-candidate-v2^{}
# expected: 0d1882d287df3108a797fe6957fb21761ce80cdd
```

Handoff documentation commits **after** this SHA, if any, do **not** change candidate code and must **not** move this tag.

---

## 2. Superseded candidate (do not approve)

| Field | Value |
|-------|-------|
| Tag | `manual-vital-signs-provider-review-candidate-v1` |
| SHA | `cabfea6a63e3f27825df5f0a104a3278e1665f2b` |
| Status | **NOT ELIGIBLE FOR HUMAN APPROVAL** |
| Reason | MV-UI-001 — displayed unit could fall back to catalog position while `measurementKey` was empty or unmatched |

v1 remains immutable historical evidence. Do not move or amend it.

---

## 3. Intended use (narrow)

Manual entry and recording of **five** bounded vital-sign / anthropometric measurements into the existing **Observation** clinical record for an **identified patient** and **Encounter**, governed per organization.

| Key | LOINC | Canonical UCUM | UI display unit |
|-----|-------|----------------|-----------------|
| `heart_rate` | 8867-4 | `/min` | `beats/min` |
| `respiratory_rate` | 9279-1 | `/min` | `breaths/min` |
| `body_temperature` | 8310-5 | `Cel` | `Cel` |
| `body_weight` | 29463-7 | `kg` | `kg` |
| `body_height` | 8302-2 | `cm` | `cm` |

Terminology is **server-owned**. The client submits `measurement_key`, `value`, `effective_at`, Encounter, and expected patient only. The server derives LOINC/UCUM. No unit conversion.

Full statement: `docs/governance/manual-vital-signs-provider-clinical-safety-review.md` §A.1.

---

## 4. Explicit exclusions

| Item | Status |
|------|--------|
| Blood Pressure write | **DEFERRED** |
| SpO2 write | **DEFERRED** |
| BMI | **NOT IN MVP** |
| Clinical normal/abnormal interpretation | **NOT IMPLEMENTED** |
| Diagnostic recommendation | **NOT IMPLEMENTED** |
| Automatic clinical decision support | **NOT IMPLEMENTED** |
| Temperature site/method (oral, axillary, tympanic, rectal, ear, etc.) | **NOT CAPTURED** — generic 8310-5 + Cel only |
| Correction / amend / EIE UI (Healthcare Web) | **DEFERRED** |
| AI | **NOT IMPLEMENTED** |

---

## 5. Correction pathway (residual limitation)

| Layer | Status |
|-------|--------|
| Backend Observation | `ClinicalService.amend_observation` and `mark_observation_entered_in_error` exist (Wave 2B.2a Observation APIs) |
| Manual Vitals Healthcare Web | **Create-only** — no amend/EIE/correction controls |

Do **not** treat provider release as including a complete clinician correction workflow in Healthcare Web.

---

## 6. Resolved engineering findings

| ID | Historical severity | Status | Notes |
|----|---------------------|--------|-------|
| GENERIC-OBS-001 | P1 | **RESOLVED** | Generic staff Observation `category=VITAL_SIGNS` denied (`vital_signs_requires_governed_route`) |
| MV-TOCTOU-001 | P1 | **RESOLVED** | Mutation lock order: Encounter → Provider → Profile → Activation → idempotency / clinical mutation |
| MV-UI-001 | UI semantic (v1) | **RESOLVED in v2** | Unit from exact selected `measurement_key` only; v1 not eligible for approval |

Current engineering severity: **P0 = 0**, **P1 = 0**.

Inherited **P2:** DENIED-audit rollback (platform; not fixed in this handoff).

Documented **P3:** Manual Vitals-specific rate limiting deferred; correction UI deferred; BP deferred; SpO2 deferred; unrelated IAM test-reliability flake.

---

## 7. Hazard register

Do not treat this handoff as a substitute for the register.

Canonical register: `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md`

Engineering coverage includes MV-H-001 through MV-H-022 (wrong patient/tenant/facility/Encounter, terminology, unit, numeric, duplicate write, stale governance, kill-switch, site activation, approval forgery, generic Observation bypass, stale frontend context, PHI persistence, audit/provenance, time semantics, abnormal-but-valid values, correction pathway, temperature limitation, MV-UI-001 unit-binding).

**Human-review disposition for every hazard remains PENDING.** Engineering verification is not clinical acceptance.

---

## 8. Technical evidence (pointers)

| Document | Role |
|----------|------|
| `docs/gates/manual-vital-signs-provider-review-candidate-v2.md` | Candidate v2 freeze record |
| `docs/gates/manual-vital-signs-provider-review-candidate.md` | Historical v1 record — **not for approval** |
| `docs/gates/manual-vital-signs-provider-release-readiness.md` | Technical release evidence |
| `docs/gates/manual-vital-signs-security-clinical-safety-hardening.md` | Security hardening |
| `docs/gates/manual-vital-signs-final-security-boundary-closure.md` | Boundary closure |
| `docs/governance/manual-vital-signs-provider-clinical-safety-review.md` | Decision template (Part B **PENDING**) |

Handoff-lock frontend evidence (this pass, against Candidate v2 tree):

- targeted Manual Vitals frontend tests: **16 passed**
- full Healthcare Web suite: **200 passed**
- typecheck / build: **PASS**
- v1 → v2 backend/runtime/migration diff: **NONE**

---

## 9. Questions the human reviewer must evaluate

Engineering must **not** answer these.

**A.** Is the intended-use statement clinically acceptable?

**B.** Are the exact five measurements acceptable for this provider release?

**C.** Are the canonical units appropriate for intended manual entry?

**D.** Is generic `body_temperature` without measurement site/method acceptable for this MVP?

**E.** Is the absence of normal-range interpretation acceptable given the product is recording-only?

**F.** Is deferred Healthcare Web correction UI acceptable for provider release, or must a correction workflow be a pre-registration condition?

**G.** Are the patient / Encounter / facility safety controls acceptable?

**H.** Are the provider / site governance gates acceptable?

**I.** Are the documented residual risks acceptable?

**J.** Are any additional pre-registration conditions required?

---

## 10. Human decision (leave blank)

Allowed outcomes (repository-authoritative):

- `APPROVED`
- `APPROVED_WITH_CONDITIONS`
- `REJECTED`
- `PENDING`

Complete **Part B** of:

`docs/governance/manual-vital-signs-provider-clinical-safety-review.md`

Required reviewer-supplied fields (do not invent):

- review outcome
- reviewer name / identifier
- reviewer role / function
- qualification / authority evidence reference
- review date
- candidate tag (must be v2)
- candidate SHA (must be the peel of v2)
- feature ID / version
- catalog version
- reviewed intended use
- reviewed exclusions
- reviewed hazard register
- conditions / limitations
- evidence / document reference

Until that record exists with genuine human evidence:

```
PROVIDER CLINICAL SAFETY REVIEW = PENDING HUMAN SIGN-OFF
PROVIDER RELEASE REGISTRATION = BLOCKED
MIGRATION 0022 = NOT CREATED
SITE ACTIVATION = PENDING
```
