# Manual Vital Signs — Provider Release Readiness

**Date:** 2026-08-30  
**Kind:** PROVIDER RELEASE EVIDENCE PACKAGE  
**Implementation baseline:** `39909b44a1bad737839b9267a068d8bb0fa0b389` (uncommitted working tree)  
**Alembic:** `current == heads == 20260814_0021` (down `20260814_0020`, exactly one head)  
**Migration 0022:** NOT CREATED

---

## Verdict (two distinct gates)

### A. Technical provider release evidence

```
MANUAL VITAL SIGNS
TECHNICAL PROVIDER RELEASE EVIDENCE = COMPLETE

MANUAL VITAL SIGNS =
READY FOR HUMAN PROVIDER CLINICAL SAFETY REVIEW
```

### B. Human provider clinical safety review

```
PROVIDER CLINICAL SAFETY REVIEW = PENDING HUMAN SIGN-OFF

PROVIDER RELEASE REGISTRATION = BLOCKED UNTIL HUMAN SIGN-OFF

PROVIDER REGISTRATION ELIGIBILITY = BLOCKED
```

No genuine human clinical-safety approval evidence exists in the repository. Engineering pass does **not** fabricate reviewer identity, credentials, or approval date.

---

## 1. Release identity

| Field | Value |
|-------|-------|
| Capability (planned) | `manual_vital_signs_write` |
| Feature version (planned) | `1.0.0` |
| `governance_required` | `true` |
| Provider catalog version | `manual-vitals-mvp-v1` |
| Production registry | **EMPTY** |
| Real production availability | **DISABLED / FAIL-CLOSED** |
| Site approved vital entries | **0** |
| Site activation | **PENDING** |

---

## 2. Intended use

Manual entry and recording of a bounded set of vital-sign / anthropometric measurements into the existing **Observation** clinical record for an **identified patient** and **Encounter**, with server-authoritative terminology, tenant isolation, audit/provenance, idempotent write protection, and organization-governed activation.

**Exact provider-supported subset:**

| Key | LOINC | UCUM | Display |
|-----|-------|------|---------|
| `heart_rate` | 8867-4 | `/min` | beats/min |
| `respiratory_rate` | 9279-1 | `/min` | breaths/min |
| `body_temperature` | 8310-5 | `Cel` | Cel |
| `body_weight` | 29463-7 | `kg` | kg |
| `body_height` | 8302-2 | `cm` | cm |

Catalog: static immutable module `backend/app/modules/clinical/domain/vital_signs_catalog.py`.

---

## 3. Intended user

Authenticated **staff** with organization context, `clinical.observation.create`, and effective OGP activation (plus patient/encounter/facility domain checks). Site determines clinical role assignment via permissions and SOP — software does not encode profession-specific role gates.

---

## 4. Intended environment

Hospital, clinic, Puskesmas / fasyankes deployments supported by shared platform governance. Tenant grain: **Organization**. Facility: subordinate authorization context.

---

## 5. Explicit exclusions (non-intended use)

| Exclusion | Status |
|-----------|--------|
| Blood Pressure write | **DEFERRED** — paired/atomic semantics unresolved |
| SpO2 write | **DEFERRED** |
| BMI computation/write | Not supported |
| Pain score, GCS, other vitals | Not in catalog |
| Generic free-form terminology | Rejected |
| Unit conversion | Not supported |
| Clinical interpretation / normal ranges | **Explicit product boundary — not provided** |
| Diagnostic recommendation / decision support | Not supported |
| Autonomous clinical action | Not supported |
| Batch “Save All” | Not supported |
| Correction / amend / EIE UI | **DEFERRED** (backend amend/EIE exists; UI not exposed) |
| Temperature site/method (oral, axillary, etc.) | **Not captured in MVP** |
| AI clinical implementation | **NOT STARTED** |
| Clinical Note workflow changes | **UNCHANGED** |

---

## 6. Temperature limitation

- LOINC `8310-5` with canonical unit `Cel`
- Does **not** capture measurement site or method
- UI must use generic label only — must not imply oral/axillary/tympanic/rectal semantics
- Classification: **product semantic/usability limitation** — residual risk for human reviewer

---

## 7. Release claim boundaries

### Provider MAY claim (source-supported)

- Bounded Manual Vitals recording workflow for five measurements
- Per-organization governed activation (OGP)
- Server-authoritative terminology and units
- Patient / Encounter / facility safeguards
- Idempotent write protection with semantic fingerprint
- Audit and provenance on successful mutation
- Tenant isolation and cross-org concealment
- Production fail-closed until provider registration + site activation
- Generic public Observation `VITAL_SIGNS` write reservation (security correction)

### Provider MUST NOT claim

- Clinically validated diagnostic interpretation
- Medical-device or regulatory certification
- Universal clinical approval across all sites
- Normal-range or abnormal-value validation
- Error-free operation
- BP or SpO2 support
- Correction UI in Healthcare Web MVP

---

## 8. Governance model

### Three gates (frozen)

| Gate | Question | Status |
|------|----------|--------|
| A — Engineering | May engineering implement/test? | **COMPLETE** |
| B — Provider release | May provider register production capability? | **PENDING HUMAN SIGN-OFF** |
| C — Site activation | May Organization X activate/use? | **PENDING** (0 approved entries) |

### Site activation prerequisites (after provider registration)

Provider AVAILABLE → entitlement → deployment gates (`CONTROLLER_PROCESSOR_ASSESSMENT`, `DPA`) → site feature ACTIVE → effective policy → approved measurement subset → `CLINICAL_GOVERNANCE` approval evidence → actor permission → patient/encounter/facility safety.

Deployment gates are **privacy/deployment prerequisites**, not clinical approval evidence.

---

## 9. Hazard summary

Full register: `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md` (21 hazards MV-H-001 … MV-H-021).

Human-review disposition for all hazards: **PENDING HUMAN REVIEW**.

Key residual risks for human reviewer:

1. Correction pathway — create-only UI; backend amend/EIE not exposed in Healthcare Web
2. Temperature semantic limitation
3. No abnormal-value rejection by design
4. Canonical-unit workflow dependency on operator
5. Site SOP for patient verification and role assignment

---

## 10. Resolved engineering findings

| ID | Classification | Summary |
|----|----------------|---------|
| GENERIC-OBS-001 | P1 → **RESOLVED** | Generic public staff Observation `VITAL_SIGNS` bypass; fixed at `ClinicalService.create_observation()` |
| MV-TOCTOU-001 | P1 → **RESOLVED** | Governance row-lock recheck before mutation |
| MV-REG-001 | Test defect | `row_version` helper loop — fixed |
| MV-REG-002 | Test defect | Idempotency replay policy re-check — fixed |
| MV-REG-003 | Security compatibility | Wave 2B tests updated for intentional generic `VITAL_SIGNS` prohibition |
| MV-REG-004 | P3 test reliability | IAM shell flaky read-audit test — one occurrence; non-MV |

---

## 11. Technical release evidence matrix

| Requirement | Implementation | Test / evidence | Status | Residual risk |
|-------------|----------------|-----------------|--------|---------------|
| Tenant isolation | Org-scoped principal; DB bindings | `test_cross_org_manual_vitals_concealed`, `test_encounter_cross_org_denies` | PASS | Site credential policy |
| Patient safety | Expected patient; encounter binding; same-person | `test_wrong_patient_matrix`, merge/RETIRED tests | PASS | Selection SOP |
| MPI | Historical id preserved; canonical resolution | `test_merged_identity_persists_historical_patient` | PASS | — |
| Facility | Frozen matrix; encounter/header rules | `test_facility_matrix` | PASS | Site assignment |
| Encounter policy | Status matrix + site policy | `test_encounter_status_matrix` | PASS | PLANNED/FINISHED site-dependent |
| Catalog | Static five keys | `vital_signs_catalog.py`; spoofing tests | PASS | — |
| Units | Server canonical UCUM | Catalog; no client unit field | PASS | User must match displayed unit |
| Decimal | Decimal/Numeric(14,4) | Domain + integration boundary tests | PASS | Valid extreme values allowed |
| Timestamps | `effective_at` + server `recorded_at` | Naive reject; timezone replay | PASS | Backdating = site policy |
| Idempotency | Key + semantic fingerprint | Concurrent same-key tests | PASS | — |
| OGP stack | Provider/site/profile/gates/approval | Foundation + hardening + security suites | PASS | — |
| Provider kill-switch | Row lock + SUSPENDED deny | TOCTOU + suspend tests | PASS | — |
| Site suspension | Activation lock + deny | Site TOCTOU tests | PASS | — |
| Generic bypass | Application service reservation | `test_generic_vital_signs_staff_create_blocked_without_ogp` | **RESOLVED** | Compatibility correction documented |
| Audit/provenance | Atomic with mutation | `test_success_audit_and_provenance_metadata`; rollback test | PASS | Platform P2 denied-audit separate |
| Frontend PHI | Memory-only; no storage | Source + race tests | PASS | Shared workstation |
| Production-dark | Unregistered provider | `test_production_dark_*`, boundary closure | PASS | — |
| Migration 0021 | Idempotency table DDL | Static + roundtrip tests | PASS | 0022 not created |
| DB privileges | app_dml SELECT/INSERT only on idempotency | `test_observation_idempotency_app_dml_privileges` | PASS | — |
| Frontend context races | Late-response guards | `manual-vital-write.test.tsx` | PASS | — |
| Abnormal values | No interpretation layer | Design boundary — no range tests | BY DESIGN | Human reviewer judgment |
| Correction UI | Deferred | Backend amend exists; no MV UI | DEFERRED | Operational SOP |

---

## 12. TOCTOU safety model

Manual Vitals mutation lock order: encounter → provider capability → org profile header → feature activation → idempotency + write.

Accepted orderings:

- T1 holds lock, commits write, then T2 SUSPENDED — **valid**
- T2 SUSPENDED first, T1 subsequently denies — **valid**
- Stale AVAILABLE write after committed SUSPENDED — **forbidden** (controlled)

Evidence: `test_manual_vitals_boundary_closure.py` (6 tests).

---

## 13. Production-dark proof (current — correct)

| Check | Result |
|-------|--------|
| Dedicated GET write context | `available=false`, `measurements=[]` |
| Dedicated POST | **403** deny |
| Generic staff POST + `VITAL_SIGNS` | **403** `vital_signs_requires_governed_route` |
| Healthcare Web form | Hidden when unavailable |
| Provider registry (clean migration design) | **0 rows**; `manual_vital_signs_write` absent |

---

## 14. Quality evidence (this pass)

| Gate | Result |
|------|--------|
| Targeted Manual Vitals suites | **81 passed** |
| Full backend (`app_dml`) | **633 passed**, 0 failed, 0 errors, 1 skipped |
| Frontend Vitest | **192 passed** |
| ruff check / format (app tests) | PASS |
| mypy app | PASS |
| OpenAPI `--check` | PASS |
| typecheck / build | PASS |
| Alembic `current == heads == 20260814_0021` | PASS |
| Migration static 0021 | PASS |
| Migration roundtrip 0021→0020→0021 | PASS (hardening suite) |

Prior note: one flaky `test_iam_shell_context_hardening::test_success_reads_do_not_audit_or_write_provenance` during an intermediate run; passes isolated; final release run green. Classified **P3** non-MV test reliability.

---

## 15. Findings severity

| Severity | Count | Notes |
|----------|------:|-------|
| P0 | 0 | |
| P1 | 0 | Historical P1 resolved (GENERIC-OBS-001, MV-TOCTOU-001) |
| P2 | 1 | Inherited DENIED-audit rollback (platform) |
| P3 | 4 | Rate limit deferred; correction UI deferred; BP/SpO2 deferred; IAM flake |

---

## 16. Human review requirement

Minimum sign-off fields defined in:  
`docs/governance/manual-vital-signs-provider-clinical-safety-review.md` Part B.

Until human evidence records **APPROVED** or release-acceptable equivalent:

- `manual_vital_signs_write` **MUST remain unregistered**
- Migration **0022 MUST NOT exist**

---

## 17. Eligibility for migration 0022

| Criterion | Status |
|-----------|--------|
| Technical evidence complete | **YES** |
| P0 = 0, P1 = 0 | **YES** |
| Human provider clinical safety review | **PENDING** |
| Eligible for 0022 creation | **NO** — blocked until Gate B human sign-off |
| Eligible for registration pass (separate stage) | **NO** — blocked until Gate B |

0022 creation is a **separate controlled stage** after human sign-off. Not performed in this pass.

---

## 18. Related documents

| Document | Purpose |
|----------|---------|
| `docs/gates/manual-vital-signs-provider-review-candidate-v2.md` | Current engineering review candidate (`manual-vital-signs-provider-review-candidate-v2`) |
| `docs/gates/manual-vital-signs-provider-review-candidate.md` | Historical v1 candidate — **not eligible for human approval** |
| `docs/gates/manual-vital-signs-final-preimplementation-contract.md` | Frozen implementation contracts |
| `docs/gates/manual-vital-signs-implementation-gate.md` | Implementation evidence |
| `docs/gates/manual-vital-signs-implementation-regression-closure.md` | Regression closure |
| `docs/gates/manual-vital-signs-security-clinical-safety-hardening.md` | Security hardening |
| `docs/gates/manual-vital-signs-final-security-boundary-closure.md` | Boundary closure |
| `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md` | Hazard register |
| `docs/governance/manual-vital-signs-provider-clinical-safety-review.md` | Human review template |
| `docs/gates/observation-vital-signs-write-workflow-design-approval.md` | Multi-gate design approval |
| `docs/governance/provider-clinical-safety-defaults.md` | CLIN-* control baseline |
| `docs/governance/healthcare-software-provider-governance-baseline.md` | Provider governance baseline |

---

## 19. Frozen status lines

```
PROVIDER CAPABILITY PRODUCTION REGISTRY = EMPTY

manual_vital_signs_write = NOT REGISTERED

REAL PRODUCTION MANUAL VITALS AVAILABILITY = DISABLED / FAIL-CLOSED

PROVIDER CLINICAL SAFETY REVIEW = PENDING HUMAN SIGN-OFF

PROVIDER RELEASE REGISTRATION = BLOCKED UNTIL HUMAN SIGN-OFF

SITE APPROVED VITAL ENTRIES = 0

SITE ACTIVATION = PENDING

MIGRATION 0021 = CREATED

MIGRATION 0022 = NOT CREATED

BLOOD PRESSURE WRITE = DEFERRED

SpO2 = DEFERRED

CORRECTION / AMEND / EIE UI = DEFERRED

CLINICAL NOTE = UNCHANGED

AI CLINICAL IMPLEMENTATION = NOT STARTED

NO COMMIT
NO TAG
NO PUSH
```
