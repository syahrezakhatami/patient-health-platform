# Manual Vital Signs — Provider Review Candidate

**Kind:** ENGINEERING REVIEW CANDIDATE RECORD  
**Date:** 2026-09-04  
**Canonical candidate tag:** `manual-vital-signs-provider-review-candidate-v1`

> **SUPERSEDED FOR HUMAN REVIEW.**  
> This tag remains immutable historical evidence at `cabfea6a63e3f27825df5f0a104a3278e1665f2b`.  
> It must **not** receive provider clinical-safety approval.  
> Human review must use `manual-vital-signs-provider-review-candidate-v2`.  
> Reason: UI unit-binding defect — displayed unit could fall back to the first catalog entry while `measurementKey` was empty or unmatched.

This record identifies an **immutable engineering review candidate** that was published and then found unsafe for clinical-safety sign-off. It is **not** provider registration, production release, site activation, clinical approval, or a final capability freeze.

The candidate remains **production-dark**.

Resolved candidate SHA is the commit the tag peels to after publication. This file does not embed a self-referential SHA.

---

## Candidate purpose

Give a human provider clinical-safety reviewer an unambiguous software pointer:

- exact source tree
- exact Alembic head
- exact planned feature identity
- exact provider catalog
- complete technical evidence package
- explicit residual risks

without implying that the capability is registered, clinically approved, or available in production.

---

## Identity

| Field | Value |
|-------|-------|
| Parent / source baseline | `39909b44a1bad737839b9267a068d8bb0fa0b389` |
| Candidate tag | `manual-vital-signs-provider-review-candidate-v1` |
| Resolved candidate SHA | **from tag after publication** |
| Alembic | `current == heads == 20260814_0021` (down `20260814_0020`, one head) |
| Migration 0022 | **NOT CREATED** |
| Planned feature ID | `manual_vital_signs_write` |
| Planned feature version | `1.0.0` |
| `governance_required` | `true` |
| Provider catalog | `manual-vitals-mvp-v1` |
| Production registration | **ABSENT** |
| Production availability | **DISABLED / FAIL-CLOSED** |

---

## Intended use (narrow)

Manual entry and recording of a bounded set of vital-sign / anthropometric measurements into the existing Observation clinical record for an identified patient and Encounter, governed per organization.

Exact catalog:

| Key | LOINC | UCUM |
|-----|-------|------|
| `heart_rate` | 8867-4 | `/min` |
| `respiratory_rate` | 9279-1 | `/min` |
| `body_temperature` | 8310-5 | `Cel` |
| `body_weight` | 29463-7 | `kg` |
| `body_height` | 8302-2 | `cm` |

Terminology authority: server-owned immutable application catalog. Site and client cannot submit arbitrary LOINC/UCUM.

---

## Exclusions

- Blood Pressure write
- SpO2 write
- BMI computation/write
- Pain score, GCS, free-form terminology
- Unit conversion
- Clinical interpretation / normal ranges / decision support
- Correction / amend / EIE UI
- Temperature site or method (oral, axillary, tympanic, rectal)
- AI clinical implementation
- Clinical Note behavior change

---

## Production-dark proof (required candidate behavior)

Without test governance fixtures:

| Surface | Result |
|---------|--------|
| Dedicated GET write context | `available=false`, `measurements=[]` |
| Dedicated POST | DENIED |
| Generic staff Observation POST `category=VITAL_SIGNS` | DENIED (`vital_signs_requires_governed_route`) |
| Healthcare Web form | Hidden / unusable |

Test fixtures that temporarily register `manual_vital_signs_write` are **not** production seed. Migrations `0020` and `0021` insert **zero** provider capability rows.

---

## Lock / TOCTOU safety model (implemented)

Manual Vitals mutation lock order in `ManualVitalsService.create_measurement`:

1. Encounter (`FOR UPDATE`)
2. Provider capability (`FOR UPDATE`)
3. Organization governance profile header / active pointer (`FOR UPDATE`)
4. Organization feature activation (`FOR UPDATE`)
5. Idempotency claim + clinical mutation + audit/provenance (same transaction)

Accepted concurrency orderings:

- Write holds the safety lock and commits first; suspension becomes authoritative afterward — **valid**
- Suspension commits first; subsequent write resolves deny state and does **not** write — **valid**
- Stale AVAILABLE write after committed SUSPENDED — **forbidden**

---

## Technical evidence summary

See:

- `docs/gates/manual-vital-signs-implementation-gate.md`
- `docs/gates/manual-vital-signs-implementation-regression-closure.md`
- `docs/gates/manual-vital-signs-security-clinical-safety-hardening.md`
- `docs/gates/manual-vital-signs-final-security-boundary-closure.md`
- `docs/gates/manual-vital-signs-provider-release-readiness.md`

Candidate publication evidence (this freeze pass):

- targeted Manual Vitals / Observation / OGP / Clinical Note suites: **188 passed**
- full backend `app_dml` suite: **634 passed**, 0 failed, 0 errors
- frontend suite: **192 passed**
- ruff / mypy / OpenAPI / typecheck / build: **PASS**
- P0 = 0, P1 = 0

---

## Resolved findings

| ID | Classification | Status |
|----|----------------|--------|
| GENERIC-OBS-001 | Historical **P1** same-actor generic Observation `VITAL_SIGNS` OGP bypass | **RESOLVED** at `ClinicalService.create_observation()` with 403 `vital_signs_requires_governed_route` |
| MV-TOCTOU-001 | Historical **P1** stale governance commit risk | **RESOLVED** — row-lock recheck before mutation |
| MV-REG-001 | Test defect | `row_version` helper loop — fixed |
| MV-REG-002 | Test defect | Idempotency replay policy re-check — fixed |
| MV-REG-003 | Security compatibility correction | Public generic `VITAL_SIGNS` write prohibited vs Wave 2B.2a |
| MV-REG-004 | **P3** test reliability / non-Manual-Vitals | `test_iam_shell_context_hardening::test_success_reads_do_not_audit_or_write_provenance` — one flaky full-suite occurrence; isolated PASS; four subsequent full `app_dml` suites green |

SECURITY COMPATIBILITY CORRECTION: generic public Observation `VITAL_SIGNS` write changed from the prior Wave 2B.2a baseline. Historical `VITAL_SIGNS` reads, amend, and entered-in-error remain supported.

---

## Residual risks for human review

Hazard register: `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md`

Human-review disposition remains **PENDING** for all hazards.

Key residual risks:

1. Correction / amend / EIE UI deferred (backend Observation correction exists; Healthcare Web create-only)
2. Temperature semantic limitation (generic LOINC 8310-5, no site/method)
3. No clinical normal-range / abnormal-value rejection by design
4. Canonical-unit workflow: operator must enter the displayed unit
5. Site SOP dependencies (patient verification, role assignment, backdating)
6. Inherited platform P2: DENIED-audit rollback (not Manual Vitals mutation atomicity)

---

## Human-review documents

| Document | Role |
|----------|------|
| `docs/governance/manual-vital-signs-provider-clinical-safety-review.md` | Human decision template — **PENDING** |
| `docs/governance/manual-vital-signs-clinical-safety-hazard-register.md` | Hazard / control / evidence register |
| `docs/gates/manual-vital-signs-provider-release-readiness.md` | Technical release evidence package |

The reviewer must record the candidate tag `manual-vital-signs-provider-review-candidate-v1` and the resolved candidate SHA from that tag. Engineering must **not** fill human identity, credentials, dates, or approval outcome.

---

## Distinct verdicts (do not collapse)

```
ENGINEERING REVIEW CANDIDATE = PUBLISHED

PROVIDER CLINICAL SAFETY REVIEW = PENDING HUMAN SIGN-OFF

PROVIDER PRODUCTION REGISTRATION = BLOCKED
```

Do **not** call this candidate production-ready, clinically approved, provider-approved, site-approved, or a final frozen release.
