# Manual Vital Signs — Provider Clinical Safety Review

**Date:** 2026-08-30 (candidate binding 2026-09-04)  
**Kind:** PROVIDER RELEASE GATE — human decision record template  
**Feature:** `manual_vital_signs_write` @ `1.0.0`  
**Provider catalog:** `manual-vitals-mvp-v1`  
**Engineering review candidate tag:** `manual-vital-signs-provider-review-candidate-v2`  
**Superseded candidate (not for approval):** `manual-vital-signs-provider-review-candidate-v1` @ `cabfea6a63e3f27825df5f0a104a3278e1665f2b`  
**Implementation baseline:** `39909b44a1bad737839b9267a068d8bb0fa0b389`  
**Alembic:** `20260814_0021`

This document separates **engineering evidence** (prepared by implementation/review pass) from **human clinical review decision** (requires genuine attributable sign-off).

Software does **not** cryptographically verify medical qualifications of reviewers.

---

## Part A — Engineering evidence (COMPLETE)

### A.1 Intended use (narrow)

Manual entry and recording of a **bounded set** of vital-sign / anthropometric measurements into the existing **Observation** clinical record for an **identified patient** and **Encounter**, governed per organization through OGP.

**Provider-supported measurement keys (exact five):**

| Key | LOINC | Canonical unit |
|-----|-------|----------------|
| `heart_rate` | 8867-4 | `/min` |
| `respiratory_rate` | 9279-1 | `/min` |
| `body_temperature` | 8310-5 | `Cel` |
| `body_weight` | 29463-7 | `kg` |
| `body_height` | 8302-2 | `cm` |

Terminology authority: server-owned immutable application catalog (`vital_signs_catalog.py`). Site and client cannot submit arbitrary LOINC/UCUM.

### A.2 Intended user (software authority model)

Authenticated **staff** with:

- valid organization context
- `clinical.observation.create`
- effective OGP activation (provider AVAILABLE, site ACTIVE, policy, approval, gates)
- domain safety checks (patient, encounter, facility)

Software does **not** encode medical profession role requirements (e.g. “nurse only”). Site assigns grants and SOP.

### A.3 Intended environment

Hospital, clinic, Puskesmas / healthcare-facility deployment to the extent supported by provider governance and product scope. Tenant grain: **Organization**. Facility: subordinate context.

### A.4 Explicit non-intended use

- No Blood Pressure write
- No SpO2 write
- No BMI computation/write
- No pain score, GCS, or other vitals outside the five keys
- No generic free-form terminology
- No unit conversion
- No clinical normal/abnormal interpretation or diagnostic recommendation
- No decision support or autonomous clinical action
- No batch “Save All”
- No correction/amend/EIE UI in this release
- No temperature measurement-site or method claim
- No AI clinical implementation

### A.5 Governance model summary

| Layer | Requirement |
|-------|-------------|
| Provider registration | `manual_vital_signs_write` @ `1.0.0`, `governance_required=true` — **NOT registered yet** |
| Provider state | AVAILABLE required |
| Deployment gates | `CONTROLLER_PROCESSOR_ASSESSMENT`, `DPA` (privacy/deployment prerequisites — not clinical approval) |
| Site activation | Feature ACTIVE + effective policy + approved subset + `CLINICAL_GOVERNANCE` approval evidence |
| Production-dark today | Dedicated GET `available=false`; POST deny; generic `VITAL_SIGNS` deny |

Gate classification (frozen): Manual Vitals provider clinical review = **`PROVIDER_RELEASE_GATE`**. Site terminology/clinical activation = **`SITE_APPROVAL_PENDING`**.

### A.6 Engineering control verification

| Area | Evidence status |
|------|-----------------|
| Hazard register | `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md` |
| Security boundary closure | `docs/gates/manual-vital-signs-final-security-boundary-closure.md` |
| Implementation + regression | `docs/gates/manual-vital-signs-implementation-gate.md`, `...-regression-closure.md` |
| Security hardening | `docs/gates/manual-vital-signs-security-clinical-safety-hardening.md` |
| Pre-implementation contract | `docs/gates/manual-vital-signs-final-preimplementation-contract.md` |

**Targeted Manual Vitals suites (implementation pass):** 81 passed  
**Full backend (`app_dml`):** 633 passed, 0 failed, 0 errors, 1 skipped  
**Frontend (candidate v1):** 192 passed  
**Frontend (unit-binding v2):** 200 passed; typecheck/build PASS  
**Quality gates:** ruff, mypy, OpenAPI, typecheck, build — PASS

v1 is **not** eligible for human approval. Human review uses `manual-vital-signs-provider-review-candidate-v2` after publication.

### A.7 Resolved security findings

| ID | Initial | Final |
|----|---------|-------|
| GENERIC-OBS-001 | P1 — same actor bypass via generic Observation | **RESOLVED** — 403 at `ClinicalService.create_observation()` |
| MV-TOCTOU-001 | P1 risk — stale governance commit | **RESOLVED** — row-lock recheck |
| MV-UI-001 | UI semantic — unit from catalog `[0]` while `measurementKey` empty | **RESOLVED in v2** — exact key lookup; v1 not eligible for approval |

SECURITY COMPATIBILITY CORRECTION: public generic Observation `VITAL_SIGNS` write changed from Wave 2B.2a baseline. Historical read/amend/EIE unchanged.

### A.8 Residual risks requiring human judgment

1. **Correction UI deferred** — backend amend/EIE exists; Healthcare Web create-only
2. **Temperature semantic limitation** — generic 8310-5 without site/method
3. **No clinical normal-range validation** — abnormal values may be recorded if technically valid
4. **Canonical unit workflow** — user must match displayed unit; no conversion
5. **Site SOP dependencies** — patient verification, role assignment, backdating policy
6. **BP / SpO2 deferred** — must not be claimed in release

### A.9 Severity summary (engineering)

| Severity | Count |
|----------|------:|
| P0 | 0 |
| P1 | 0 (historical P1 resolved) |
| P2 | 1 — inherited DENIED-audit rollback (platform) |
| P3 | 4 — rate limit deferred; correction UI deferred; BP/SpO2 deferred; IAM test flake (non-MV) |

---

## Part B — Human clinical review decision (PENDING)

> **Do not complete this section without genuine human evidence.**  
> Cursor / engineering pass must not invent reviewer identity, credentials, dates, or approval.

### B.1 Minimum evidence fields (required at sign-off)

| Field | Value |
|-------|-------|
| Review decision | **PENDING** — `APPROVED` / `APPROVED_WITH_CONDITIONS` / `REJECTED` / `PENDING` |
| Reviewer name / identifier | **PENDING** |
| Reviewer role / function | **PENDING** |
| Reviewer qualification / authority evidence (org-supplied; not cryptographically verified by software) | **PENDING** |
| Review date | **PENDING** |
| Reviewed candidate tag | `manual-vital-signs-provider-review-candidate-v2` — **PENDING human attestation of tag used** |
| Resolved candidate SHA | **PENDING** — reviewer records the commit the candidate tag peels to |
| Reviewed feature ID | `manual_vital_signs_write` |
| Reviewed feature version | `1.0.0` |
| Reviewed provider catalog version | `manual-vitals-mvp-v1` |
| Reviewed Alembic | `20260814_0021` |
| Reviewed intended use | See Part A.1 — **PENDING human attestation** |
| Reviewed exclusions | See Part A.4 — **PENDING human attestation** |
| Reviewed hazard / residual-risk list | `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md` — **PENDING human attestation** |
| Accepted conditions / limitations | **PENDING** |
| Evidence / document reference | **PENDING** |

### B.2 Conditions (if APPROVED_WITH_CONDITIONS)

| Condition | Classification | Status |
|-----------|----------------|--------|
| _(none recorded)_ | PRE-REGISTRATION / PRE-SITE-ACTIVATION / OPERATIONAL | **PENDING** |

### B.3 Review outcome record

```
PROVIDER CLINICAL SAFETY REVIEW = PENDING HUMAN SIGN-OFF

No genuine human provider clinical-safety approval evidence exists in the repository at the time of this engineering evidence pass.
```

---

## Part C — Gate linkage

| Gate | Status |
|------|--------|
| A — Provider engineering | **COMPLETE** (implementation + hardening + boundary closure) |
| B — Provider release (`PROVIDER_RELEASE_GATE`) | **PENDING HUMAN SIGN-OFF** |
| C — Site activation | **PENDING** (0 site-approved vital entries) |

Registration migration `0022` remains **NOT CREATED** until Gate B human sign-off and separate controlled registration stage.
