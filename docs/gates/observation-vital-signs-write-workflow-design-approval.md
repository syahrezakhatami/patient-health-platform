# Observation / Vital Signs write workflow — design approval gate

**Date:** 2026-08-27 (reconciled 2026-08-28; final contract 2026-08-28; integrity correction 2026-08-29)
**Kind:** DESIGN APPROVAL — multi-gate status + final pre-implementation contract
**Baseline HEAD:** `60eafc5b8454867722cf8738a0f636bb866d3350`
**Parent OGP frozen:** `d449ffed6bd314edac3964f1c6c69bb51955a8db` (`organization-governance-profile-foundation-frozen`)
**Software capability parent:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Alembic:** `current == heads == 20260814_0020` (exactly one head)
**Observation migration:** **`20260814_0021`** assigned (parent `20260814_0020`; **NOT CREATED**)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize production registration, site activation, or implementing Observation/Vital Signs writes in this pass.

---

## Verdict (multi-gate)

```
OBSERVATION / MANUAL VITAL SIGNS
PROVIDER-vs-SITE GATE RECONCILIATION = COMPLETE

MANUAL VITAL SIGNS ENGINEERING DESIGN =
APPROVED FOR IMPLEMENTATION

MANUAL VITAL SIGNS =
READY FOR IMPLEMENTATION

PROVIDER PRODUCTION REGISTRATION =
PENDING PROVIDER RELEASE / CLINICAL SAFETY GATE

SITE ACTIVATION =
PENDING SITE CLINICAL / TERMINOLOGY APPROVAL
```

Final contract: `docs/gates/manual-vital-signs-final-preimplementation-contract.md`

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
| HEAD | `60eafc5b8454867722cf8738a0f636bb866d3350` |
| Tag (OGP) | `organization-governance-profile-foundation-frozen` → `d449ffe` |
| Branch | `main` == `origin/main` |
| Alembic | `20260814_0020` (OGP); Manual Vitals **`20260814_0021` assigned, not created** |
| Provider registry | **EMPTY** — no `manual_vital_signs_write` |
| Production code | unchanged by design/contract docs |

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

## 3. Final pre-implementation contract (frozen)

| Decision | Value |
|---|---|
| **PROVIDER CATALOG** | STATIC APPLICATION-OWNED IMMUTABLE CATALOG |
| **PROVIDER CATALOG VERSION** | `manual-vitals-mvp-v1` |
| **PROVIDER ENTRY KEYS** | `heart_rate`, `respiratory_rate`, `body_temperature`, `body_weight`, `body_height` |
| **SITE SUBSET STORAGE** | versioned OGP governance policy (`GovernancePolicyDocumentV2`) |
| **OGP POLICY SCHEMA** | version **2** (v1 backward compatible; absent block = DENY) |
| **MANUAL VITALS POLICY BLOCK** | `manual_vital_signs.catalog_version` + `approved_measurements[]` |
| **APPROVAL EVIDENCE SUBSET BINDING** | reuse `scope` column — compact fingerprint + `governance_profile_version_id` (no new evidence table in 0021) |
| **APPROVAL CANONICAL PAYLOAD** | `{"catalog_version","approved_measurements"}` sorted keys; canonical JSON → SHA-256 |
| **APPROVAL SCOPE FORMAT** | `<catalog_version>#sha256:<64-lowercase-hex>` (max **92** chars; prior raw-key format **rejected** — 132 chars > 128) |
| **APPROVAL TYPE** | `CLINICAL_GOVERNANCE` (free string per frozen OGP) |
| **PROFILE VERSION BINDING** | exact `governance_profile_version_id` match — no silent carry in MVP |
| **MIGRATION 0021 DDL** | `clinical_observation_write_idempotency` only — **no provider seed, no GRANT in Alembic** |
| **GRANTS** | `grant_dev_privileges.sql` outside Alembic; idempotency table SELECT+INSERT only |
| **PRODUCTION REGISTRATION MECHANISM** | deterministic Alembic seed in **`20260814_0022`** (after Gate B) |
| **PROVIDER FEATURE VERSION** | `1.0.0` |
| **PROVIDER FEATURE ID** | `manual_vital_signs_write` — **NOT REGISTERED** |
| **REQUIRED DEPLOYMENT GATES** | `CONTROLLER_PROCESSOR_ASSESSMENT`, `DPA` (seeded at registration) |
| **MIGRATION 0021** | `clinical_observation_write_idempotency` only — **no provider seed** |
| **MIGRATION 0022** | provider registration seed — **only when Gate B passes** |
| **WRITE REQUEST TERMINOLOGY AUTHORITY** | SERVER CATALOG |
| **CLIENT SUPPLIES LOINC** | **NO** |
| **CLIENT SUPPLIES UNIT** | **NO** |
| **CLIENT SUPPLIES measurement_key** | **YES** |
| **WRITE DTO** | `{ expected_patient_identity_id, encounter_id, measurement_key, value, effective_at }` + Idempotency-Key |
| **PRODUCT ROUTES** | GET/POST `/organizations/{org_id}/clinical/manual-vitals/measurements` |
| **IDEMPOTENCY FINGERPRINT** | patient + encounter + measurement_key + canonical decimal + effective_at + catalog_version |
| **DECIMAL VALIDATION** | parse → reject NaN/Inf → precision check → reject scale > 4 → then canonicalize; **NO SILENT ROUNDING** |
| **DECIMAL FINGERPRINT** | `normalize()` plain decimal; `1`/`1.0`/`1.00` → `"1"`; `1.23456` → reject |

### Provider entry codes/units (exact)

| key | LOINC | unit_code |
|---|---|---|
| `heart_rate` | `8867-4` | `/min` |
| `respiratory_rate` | `9279-1` | `/min` |
| `body_temperature` | `8310-5` | `Cel` |
| `body_weight` | `29463-7` | `kg` |
| `body_height` | `8302-2` | `cm` |

### Remaining safety contracts

| Decision | Value |
|---|---|
| VITAL TERMINOLOGY — national evidence | SATUSEHAT subset — `NATIONAL_INTEROPERABILITY_PROFILE` |
| SITE-APPROVED ENTRIES | **0** |
| PROVIDER CLINICAL SAFETY REVIEW | **PENDING** |
| CATALOG ENFORCEMENT | server-enforced static catalog |
| AUTOMATIC UNIT CONVERSION | **NO** |
| NORMAL-RANGE VALIDATION | **NO** |
| BLOOD PRESSURE WRITE | **DEFERRED** |
| SpO₂ | **DEFERRED** |
| OGP `governance_required` | `true` when registered |
| ENCOUNTER REQUIRED | **YES** |
| ENCOUNTER STATUSES | IN_PROGRESS allow; CANCELLED/EIE reject; PLANNED/FINISHED site policy (fail closed default) |
| PATIENT / FACILITY | Note-like contracts |
| CREATE-ONLY MVP | FINAL |
| CORRECTION UI | DEFERRED |
| POST-WRITE INVALIDATION | observations + timeline + summary |

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

No production code. No Observation write migration created. No provider capability registration. No frozen capability tag. No invented APPROVED site terminology. No commit/tag/push in final contract pass.

Historical note: pre-OGP verdict `BLOCKED BY VITAL SIGNS TERMINOLOGY HUMAN APPROVAL` conflated site activation with engineering readiness. Post-OGP reconciliation supersedes that single-blocker model without erasing human-approval gate history.
