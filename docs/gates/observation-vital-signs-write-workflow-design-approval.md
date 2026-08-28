# Observation / Vital Signs write workflow — design approval gate

**Date:** 2026-08-27
**Kind:** DESIGN APPROVAL — blocked pending terminology human approval
**Verdict:** OBSERVATION / VITAL SIGNS WRITE DESIGN = **BLOCKED**
**BLOCKED BY:** **VITAL SIGNS TERMINOLOGY HUMAN APPROVAL** (ingestion 2026-08-27: **0** fully APPROVED entries; encounter/timing product policies still PENDING)
**Baseline HEAD:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Parent:** `3157ad9947f3f46d084df84982ee3b370f1c1a29` (`clinical-chart-ui-frozen`)
**Alembic:** `current == heads == 20260814_0019` (exactly one head)
**Migration `0020`:** REQUIRED (designed; **not created**)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize implementing Observation/Vital Signs writes.

Sources:

- `docs/architecture/observation-vital-signs-write-workflow-design.md`
- `docs/architecture/vital-signs-terminology-candidate-catalog.md`
- `docs/gates/vital-signs-terminology-human-approval.md`

```
TERMINOLOGY CANDIDATE CATALOG = READY FOR HUMAN DECISION
TERMINOLOGY HUMAN APPROVAL = PENDING
```

Candidate LOINC/UCUM research **does not** change this verdict to APPROVED.

**Source versions:** LOINC release **2.83** (2026-08-19). LOINC FHIR TS may report **2.82** until updated — do not conflate. HR/RR units: **DECISION REQUIRED** (`{beats}/min` / `{breaths}/min` etc.; not auto `/min`).

---

## 1. Baseline

| Item | Result |
|---|---|
| HEAD | `c55d259180c4864b56ea40e4c24833c9cd438d68` |
| Tag | `clinical-note-write-frozen` |
| Branch | `main` == `origin/main` |
| Migration `0020` | **absent** |
| Production code | unchanged by design docs |

---

## 2. Exact decisions (non-terminology + terminology status)

| Decision | Value |
|---|---|
| VITAL TERMINOLOGY SOURCE | **C — human product/clinical approval still missing** |
| VITAL CATALOG VERSION | **UNASSIGNED / PENDING FIRST APPROVAL** |
| VITAL CATALOG | **Zero APPROVED entries**; six CANDIDATEs in evidence package; HR/RR unit **DECISION REQUIRED** |
| CATALOG ENFORCEMENT | Static application-owned immutable catalog (future); server-enforced; frontend UX only |
| CODE/UNIT VALIDATION | SERVER ENFORCED (when approved entries exist) |
| AUTOMATIC UNIT CONVERSION | **NO** |
| NORMAL-RANGE VALIDATION | **NO** |
| BLOOD PRESSURE | **DEFERRED** |
| ENCOUNTER REQUIRED | **YES** (product contract; not falsely claimed as SATUSEHAT statute alone) |
| ENCOUNTER STATUSES | `IN_PROGRESS` = `VENDOR_SAFETY_DEFAULT` allow; `CANCELLED`/`ENTERED_IN_ERROR` = reject; **`PLANNED`/`FINISHED` = `SITE_CLINICAL_POLICY` (PENDING site/product human sign-off)** — not universally hard-coded allow |
| PATIENT CONTEXT PRECONDITION | `expected_patient_identity_id`; encounter binding; same-person; 404 / RETIRED 409 |
| FACILITY MATRIX | Note-like A/A allow; A/B 409; absent + B-only 403 |
| VALUE TYPE | NUMERIC |
| NUMERIC STORAGE | Numeric(14,4) / Decimal |
| FORM MODEL | ONE MEASUREMENT AT A TIME |
| COMMAND MODEL | SINGLE |
| CREATE-ONLY MVP | YES / FINAL |
| CORRECTION UI | DEFERRED |
| MEASUREMENT TIME | `effective_at` required = `VENDOR_SAFETY_DEFAULT` (not falsely SATUSEHAT-mandatory); `recorded_at` server; backdating = `SITE_CLINICAL_POLICY`; future skew = site/technical policy — **no invented 5-minute national rule** |
| IDEMPOTENCY | `clinical_observation_write_idempotency`; replay re-checks auth + catalog |
| NEW BACKEND ROUTES | NONE |
| MIGRATION 0020 | REQUIRED — idempotency only, **not** terminology |
| MIGRATION 0020 CONTENT | `clinical_observation_write_idempotency` (+ insert-only / unique scope / deferred FK) |
| POST-WRITE INVALIDATION | observations + timeline + summary (`recent_vitals`) |

---

## 3. Findings

### Provider foundation severity

| Sev | Finding |
|---|---|
| **P0** | None in published baseline |
| **P1 provider-foundation unresolved** | None — capability blocked by site gate, not global P1 |
| **P2** | Inherited DENIED-audit rollback |
| **P3** | Free-string units; index gaps; grants outside Alembic |

### Gate types (capability blockers — not global P1)

| Gate | Finding |
|---|---|
| **`SITE_APPROVAL_PENDING`** | No human-approved vital catalog (0 APPROVED entries) — **primary blocker** |
| **`SITE_APPROVAL_PENDING`** | Observation write design blocked pending site/clinical/product sign-off |
| **Capability design gap** | Observation create same-person / facility / idempotency gaps vs Note Write — addressed in design, not implemented |

**Not P2:** historical patient_identity_id non-rewrite (frozen MPI invariant).

---

## 4. Unblock criteria

≥1 entry in `vital-signs-terminology-human-approval.md` with:

PRODUCT MVP INCLUSION = APPROVED
CLINICAL SEMANTIC APPROVAL = APPROVED
FINAL ENTRY STATUS = APPROVED

Then amend this gate with exact approved rows and set:

`OBSERVATION / VITAL SIGNS WRITE DESIGN = APPROVED FOR IMPLEMENTATION`
(for the approved subset only)

Engineering must not self-unblock.

---

## 5. Explicit non-actions

No production code. No migration `0020`. No commit / tag / push. No invented APPROVED terminology.
