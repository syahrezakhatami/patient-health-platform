# Observation / Vital Signs write workflow — design approval gate

**Date:** 2026-08-27 (reconciled 2026-08-28 post-OGP)
**Kind:** DESIGN APPROVAL — multi-gate status after OGP reconciliation
**Baseline HEAD:** `d449ffed6bd314edac3964f1c6c69bb51955a8db` (`organization-governance-profile-foundation-frozen`)
**Parent OGP:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)
**Software capability parent:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Alembic:** `current == heads == 20260814_0020` (exactly one head)
**Observation migration:** **UNASSIGNED** (planned `20260814_0021`; idempotency **REQUIRED WHEN IMPLEMENTED**)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize production registration, site activation, or implementing Observation/Vital Signs writes in this pass.

---

## Verdict (multi-gate)

```
OBSERVATION / MANUAL VITAL SIGNS
PROVIDER-vs-SITE GATE RECONCILIATION = COMPLETE

MANUAL VITAL SIGNS ENGINEERING DESIGN =
APPROVED FOR IMPLEMENTATION

PROVIDER PRODUCTION REGISTRATION =
PENDING PROVIDER RELEASE / CLINICAL SAFETY GATE

SITE ACTIVATION =
PENDING SITE CLINICAL / TERMINOLOGY APPROVAL
```

Reconciliation record: `docs/gates/observation-vital-signs-provider-site-gate-reconciliation.md`

Sources:

- `docs/architecture/observation-vital-signs-write-workflow-design.md`
- `docs/architecture/vital-signs-terminology-candidate-catalog.md`
- `docs/gates/vital-signs-terminology-human-approval.md`
- `docs/gates/organization-governance-profile-final-freeze.md`

```
TERMINOLOGY CANDIDATE CATALOG = READY FOR HUMAN DECISION
SITE-APPROVED TERMINOLOGY ENTRIES = 0
PROVIDER CLINICAL SAFETY REVIEW = PENDING
```

Candidate LOINC/UCUM / SATUSEHAT research **does not** imply site clinical approval or provider production registration.

**Source versions:** LOINC release **2.83** (2026-08-19). LOINC FHIR TS may report **2.82** until updated — do not conflate. Provider engineering subset uses SATUSEHAT national-profile units for HR/RR (`/min`).

---

## 1. Baseline

| Item | Result |
|---|---|
| HEAD | `d449ffed6bd314edac3964f1c6c69bb51955a8db` |
| Tag | `organization-governance-profile-foundation-frozen` |
| Branch | `main` == `origin/main` |
| Alembic | `20260814_0020` (OGP); Observation **UNASSIGNED** |
| Provider registry | **EMPTY** — no `manual_vital_signs_write` |
| Production code | unchanged by design/reconciliation docs |

---

## 2. Three independent gates

| Gate | Question | Status |
|---|---|---|
| **A. Provider engineering** | May engineering implement/test? | **APPROVED FOR IMPLEMENTATION** |
| **B. Provider release** | May provider register production capability? | **PENDING** — provider clinical safety review |
| **C. Site activation** | May Organization X activate/use? | **PENDING** — 0 site-approved entries |

**Frozen principle:** `SITE APPROVAL != PROVIDER SOFTWARE IMPLEMENTATION APPROVAL`

Engineering may proceed under Gate A while Gates B and C remain pending, provided fail-closed OGP path and non-registration constraints are honored.

---

## 3. Exact decisions (technical contract)

| Decision | Value |
|---|---|
| VITAL TERMINOLOGY — national evidence | SATUSEHAT subset PASS — `NATIONAL_INTEROPERABILITY_PROFILE` |
| VITAL TERMINOLOGY — site activation | **0 SITE_APPROVED entries** |
| PROVIDER VITAL CATALOG VERSION (proposed) | `manual-vitals-mvp-v1` |
| PROVIDER CLINICAL SAFETY REVIEW | **PENDING** |
| CATALOG ENFORCEMENT | Static application-owned immutable catalog; server-enforced; frontend UX only |
| CODE/UNIT VALIDATION | SERVER ENFORCED |
| AUTOMATIC UNIT CONVERSION | **NO** |
| NORMAL-RANGE VALIDATION | **NO** |
| BLOOD PRESSURE WRITE | **DEFERRED** (terminology evidence PASS; workflow deferred) |
| SpO₂ | **DEFERRED** |
| ENGINEERING SUBSET | HR `8867-4` `/min`; RR `9279-1` `/min`; Temp `8310-5` `Cel`; Weight `29463-7` `kg`; Height `8302-2` `cm` |
| OGP FEATURE ID | `manual_vital_signs_write` — **not registered** |
| OGP `governance_required` | `true` when registered |
| ENCOUNTER REQUIRED | **YES** |
| ENCOUNTER STATUSES | `IN_PROGRESS` allow; `CANCELLED`/`ENTERED_IN_ERROR` reject; `PLANNED`/`FINISHED` = `SITE_CLINICAL_POLICY` (fail closed by default) |
| PATIENT CONTEXT PRECONDITION | `expected_patient_identity_id`; encounter binding; same-person; 404 / RETIRED 409 |
| FACILITY MATRIX | Note-like A/A allow; A/B 409; absent + B-only 403 |
| VALUE TYPE | NUMERIC |
| NUMERIC STORAGE | Numeric(14,4) / Decimal |
| FORM MODEL | ONE MEASUREMENT AT A TIME |
| COMMAND MODEL | SINGLE |
| CREATE-ONLY MVP | YES / FINAL |
| CORRECTION UI | DEFERRED |
| MEASUREMENT TIME | `effective_at` required; `recorded_at` server; backdating = `SITE_CLINICAL_POLICY` |
| IDEMPOTENCY | `clinical_observation_write_idempotency`; replay re-checks auth + catalog + OGP |
| NEW BACKEND ROUTES | NONE |
| OBSERVATION WRITE MIGRATION | **UNASSIGNED** — planned `20260814_0021` |
| POST-WRITE INVALIDATION | observations + timeline + summary (`recent_vitals`) |

---

## 4. Findings

### Provider foundation severity

| Sev | Finding |
|---|---|
| **P0** | None |
| **P1** | None — site activation pending is **not** a provider software P1 |
| **P2** | Inherited DENIED-audit rollback |
| **P3** | Free-string units (pre-hardening); index gaps; grants outside Alembic; correction UI deferred; BP/SpO₂ deferred |

### Gate-classified pending (not global P1)

| Gate | Finding |
|---|---|
| **`PROVIDER_RELEASE_GATE`** | Provider clinical safety review **PENDING** — blocks production registration |
| **`SITE_ACTIVATION_GATE`** | 0 site-approved vital entries — blocks organization activation |
| **Capability design gap** | Observation create same-person / facility / idempotency / OGP gaps vs Note Write — addressed in design, not implemented |

**Not P2:** historical patient_identity_id non-rewrite (frozen MPI invariant).

---

## 5. Gate B unblock criteria (provider production registration)

Before registering `manual_vital_signs_write` as provider `AVAILABLE`:

- provider clinical safety review completed (named qualified reviewer — not invented)
- provider-supported catalog version frozen (`manual-vitals-mvp-v1` or successor)
- security hardening + adversarial tests pass
- explicit provider release acceptance

Engineering must not self-register production capability.

---

## 6. Gate C unblock criteria (site activation)

Per organization, before Manual Vitals runtime activation:

- site clinical approval evidence (OGP approval record — server-resolved)
- site terminology approval bound to feature + catalog version + subset
- site encounter/time policies configured where required
- deployment gates satisfied per capability contract
- entitlement + `clinical.observation.create`

≥1 **SITE_APPROVED** measurement subset for the organization. Human approval gate history preserved; no invented approver names/dates.

---

## 7. Explicit non-actions

No production code. No Observation write migration. No provider capability registration. No frozen capability tag. No invented APPROVED site terminology.

Historical note: pre-OGP verdict `BLOCKED BY VITAL SIGNS TERMINOLOGY HUMAN APPROVAL` conflated site activation with engineering readiness. Post-OGP reconciliation supersedes that single-blocker model without erasing human-approval gate history.
