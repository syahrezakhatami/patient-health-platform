# Healthcare software provider governance baseline

**Date:** 2026-08-28
**Kind:** PROVIDER GOVERNANCE FOUNDATION — design / policy only
**Baseline HEAD:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Alembic:** `20260814_0019` (no `0020`)
**Hardening gate:** `docs/gates/provider-governance-hardening-gate.md`

This document is:

- a **provider baseline** for shared platform governance
- **not** legal advice
- **not** a customer SOP
- **not** certification (ISO / HIPAA / SOC 2 / SaMD)
- **not** an authorization to implement Observation writes, AI clinical features, or migration `0020`

**Platform posture:** software/SaaS provider serving hospitals, clinics, Puskesmas, and other fasyankes, with a shared clinical core and organization-specific policy profiles.

---

## 1. Scope

Reusable governance for:

| Layer | Meaning |
|---|---|
| A. PROVIDER / VENDOR GOVERNANCE | Secure product, platform controls, deny-by-default |
| B. HEALTHCARE FACILITY / SITE GOVERNANCE | Local SOP, staffing, clinical activation |
| C. JOINT CONTRACTUAL / REGULATORY GOVERNANCE | DPA, roles, shared incident/breach duties |
| D. AI-SPECIFIC GOVERNANCE | Use-case registry, oversight, regulatory gate |
| E. CLINICAL SAFETY GOVERNANCE | Wrong-patient prevention, immutable facts, correction |
| F. INTEROPERABILITY / TERMINOLOGY GOVERNANCE | SATUSEHAT mappings, versioned catalogs |

---

## 2. Authority classification (required labels)

Every material rule uses **exactly one** primary classification:

| Code | Meaning |
|---|---|
| `LEGAL_REQUIRED` | Applicable law/regulation obligation (scope-dependent) |
| `NATIONAL_INTEROPERABILITY_PROFILE` | SATUSEHAT / national exchange mapping evidence |
| `VENDOR_SAFETY_DEFAULT` | Provider product safety default (may be stricter than law) |
| `SITE_CLINICAL_POLICY` | Facility clinical SOP / medical governance |
| `SITE_ADMINISTRATIVE_POLICY` | Facility IT/admin configuration |
| `JOINT_CONTRACTUAL_CONTROL` | Contract / DPA / shared control |
| `AI_REGULATORY_GATE` | AI/SaMD applicability assessment required |
| `DEFERRED` | Explicitly not decided / not in scope yet |

Vendor must **not** encode facility policy as universal national law.

---

## 3. Authority hierarchy

1. Applicable Indonesian law / regulation (`LEGAL_REQUIRED`)
2. National interoperability profiles (`NATIONAL_INTEROPERABILITY_PROFILE`)
3. Contract / DPA (`JOINT_CONTRACTUAL_CONTROL`)
4. Provider safety defaults (`VENDOR_SAFETY_DEFAULT`)
5. Site clinical / administrative policy (`SITE_*`)
6. Deferred items remain inactive (`DEFERRED`)

AI intended uses with medical purpose: `AI_REGULATORY_GATE` before production activation.

---

## 4. Governance gate types (non-severity)

Use alongside P0/P1/P2/P3 — **do not force all pending work into software severity labels**:

| Gate | Meaning |
|---|---|
| `DEPLOYMENT_GATE` | Per-customer contractual/privacy/role evidence required before go-live |
| `SITE_APPROVAL_PENDING` | Named site/clinical/product human approval missing |
| `AI_ACTIVATION_GATE` | AI regulatory + TEVV + site acceptance required |
| `LEGAL_REVIEW_PENDING` | Counsel interpretation outstanding — not automatically a defect |

---

## 5. Legal review status

```
LEGAL_REVIEW = NOT_REQUIRED | PENDING | COMPLETE | ESCALATION_REQUIRED
```

Pending counsel rows are **not** automatically software defects.

---

## 6. Control record schema

Every material control includes:

| Field | Description |
|---|---|
| `control_id` | Stable ID (REG-/PRIV-/SEC-/CLIN-/TERM-/AI-/SITE-/OPS-) |
| `title` | Short name |
| `authority` | Source regulation / contract / profile |
| `classification` | Primary authority label |
| `requirement` | What must be true |
| `owner` | Provider / site / joint |
| `applicability` | Hospital / clinic / Puskesmas / deployment / use case |
| `evidence` | Artifact for PASS |
| `test_method` | Governance test ID |
| `status` | Current state |
| `exceptions` | Waivers if any |
| `review_trigger` | Event-driven review |

**Evidence rule:** PASS requires evidence — not merely that this document exists.

---

## 7. Core control registry (summary)

| control_id | title | classification | owner | test_method | status |
|---|---|---|---|---|---|
| REG-001 | RME enablement (Permenkes 24/2022) | `LEGAL_REQUIRED` | Provider + site | REGULATORY_TRACEABILITY_TEST | SOURCE VERIFIED |
| PRIV-001 | Health data = specific personal data | `LEGAL_REQUIRED` | Joint | PRIVACY_RESPONSIBILITY_TEST | SOURCE VERIFIED |
| PRIV-002 | Controller/processor per deployment | `JOINT_CONTRACTUAL_CONTROL` | Joint | PRIVACY_RESPONSIBILITY_TEST | **DEPLOYMENT_GATE** |
| SEC-001 | Security for health data processing | `LEGAL_REQUIRED` + `VENDOR_SAFETY_DEFAULT` | Provider | CLINICAL_SAFETY_CONTROL_TEST | Partial |
| CLIN-001 | Deny-by-default authorization | `VENDOR_SAFETY_DEFAULT` | Provider | CLINICAL_SAFETY_CONTROL_TEST | Design |
| CLIN-002 | No silent clinical overwrite | `VENDOR_SAFETY_DEFAULT` | Provider | CLINICAL_SAFETY_CONTROL_TEST | Design |
| CLIN-003 | Expected-patient binding | `VENDOR_SAFETY_DEFAULT` | Provider | CLINICAL_SAFETY_CONTROL_TEST | Implemented (Note Write) |
| TERM-001 | SATUSEHAT vitals national profile | `NATIONAL_INTEROPERABILITY_PROFILE` | Provider | INTEROPERABILITY_CONFORMANCE_TEST | Evidence only |
| TERM-002 | Terminology lifecycle to ACTIVE | `VENDOR_SAFETY_DEFAULT` | Provider + site | SITE_GO_LIVE_EVIDENCE_TEST | **SITE_APPROVAL_PENDING** |
| AI-001 | SE 9/2023 ethics alignment | `AI_REGULATORY_GATE` | Provider | AI_REGULATORY_APPLICABILITY_TEST | Reference |
| AI-002 | Permenkes 11 per-use-case class | `AI_REGULATORY_GATE` | Provider + reviewer | AI_REGULATORY_APPLICABILITY_TEST | NOT_ASSESSED |
| AI-003 | AI use-case registry | `VENDOR_SAFETY_DEFAULT` | Provider | AI_REGULATORY_APPLICABILITY_TEST | NOT STARTED |
| AI-004 | TEVV before clinical AI activation | `VENDOR_SAFETY_DEFAULT` | Provider + clinical | AI_TECHNICAL_EVALUATION_TEST | NOT STARTED |
| AI-005 | Autonomous clinical AI prohibited by default | `VENDOR_SAFETY_DEFAULT` + `AI_REGULATORY_GATE` | Provider | AI_REGULATORY_APPLICABILITY_TEST | Policy |
| SITE-001 | Puskesmas site profile | `SITE_CLINICAL_POLICY` | Site | SITE_GO_LIVE_EVIDENCE_TEST | Design |
| OPS-001 | Waiver governance | `VENDOR_SAFETY_DEFAULT` | Provider governance | OPERATIONAL_TABLETOP_TEST | Design |

Full regulatory detail: `indonesia-health-regulatory-applicability-matrix.md`.
Clinical defaults detail: `provider-clinical-safety-defaults.md`.

---

## 8. Responsibility model (RACI-style)

### 8.1 PROVIDER (vendor) owns

Secure SDLC; tenant isolation; authentication foundations; authorization **engine**; audit + provenance infrastructure; encryption/security controls; backup/restore capability; observability; vulnerability & dependency management; incident-response capability; terminology **implementation** of approved catalogs; model/version governance; AI Gateway controls; technical interoperability adapters; data minimization technical controls; subprocessor inventory.

### 8.2 FASYANKES (site) owns

Staff authorization **assignments**; clinical scope of practice; SOP clinical documentation; correction / late-documentation policy; workflow activation; **local** clinical terminology approval where required; AI clinical use approval; clinical escalation; staff training; go-live clinical acceptance.

### 8.3 JOINT

Controller/processor role assessment (`PRIV-002` · **`DEPLOYMENT_GATE`**); DPA; breach notification coordination; go-live evidence; retention schedules; SATUSEHAT operational onboarding; feature activation checklist; periodic governance review.

**Access control principle:** permissions (e.g. `clinical.observation.create`) are security authority — **not** role names. Site leadership configures grants per SOP. Vendor defaults remain **deny-by-default** (`CLIN-001`). Classification: `VENDOR_SAFETY_DEFAULT` + `SITE_ADMINISTRATIVE_POLICY`.

---

## 9. Clinical safety (summary)

See `docs/governance/provider-clinical-safety-defaults.md`.

- No silent clinical overwrite (`CLIN-002`)
- Auditable correction semantics (window/authority often `SITE_CLINICAL_POLICY`)
- Patient-context binding (`CLIN-003`); wrong-patient conceal; facility/encounter checks
- Technical validation ≠ clinical interpretation

---

## 10. Terminology governance

```
CANDIDATE
→ authoritative evidence
→ national interoperability mapping (if any)
→ provider engineering review
→ site clinical/product approval where required
→ APPROVED
→ versioned product catalog
→ implementation
→ change control
```

National mapping (`TERM-001`) ≠ site clinical approval (`TERM-002`). No frontend-only activation of terminology.

---

## 11. Privacy & security (summary)

Health data treated as specific personal data under UU 27/2022 (`PRIV-001`).

Provider requirements: inventory, purpose, minimization, access, retention, deletion, security, subprocessors, incidents, auditability, export/return, termination.

Per deployment: **CONTROLLER / PROCESSOR ROLE ASSESSMENT** (`PRIV-002` · `JOINT_CONTRACTUAL_CONTROL` · **`DEPLOYMENT_GATE`**) — do not assume a fixed PDP legal role. Vendor ≠ Processor universally.

Security maturity mapping: ISO/IEC 27001:2022 (`VOLUNTARY_ALIGNMENT`).
Privacy mapping: ISO/IEC 27701:2025 (`VOLUNTARY_ALIGNMENT`).
Healthcare quality alignment: ISO 7101 (`REFERENCE_FRAMEWORK`).
**No certification claimed.**

---

## 12. AI governance (summary)

See `docs/governance/ai-health-governance-policy.md`.

- Centralized AI Gateway only — no ad-hoc clinical→LLM calls
- Human oversight: AI does not auto-create authoritative clinical facts
- Use-case registry (`AI-003`) + regulatory applicability (`AI-002` · `AI_REGULATORY_GATE`)
- Default: `AI_REGULATORY_APPLICABILITY = NOT_ASSESSED` → activation **BLOCKED**
- Kill switch / fallback so core EMR works without AI
- Model & prompt change control; TEVV (`AI-004`) before clinical activation
- Autonomous clinical AI: prohibited by default (`AI-005`) — vendor default, not claimed as universal statute

---

## 13. Site activation

Shared platform for hospital / clinic / Puskesmas — **no product fork**.
Organization-specific **Site Clinical Policy Profile** (design only; no DB yet): features, grants, encounter status policy, late-entry, correction, terminology version, AI use cases.

Profile is **server-controlled** — client cannot override safety/terminology/AI restrictions.

Puskesmas context under Permenkes 19/2024 (`SITE-001`); same core, separate policy profile.

Go-live: `docs/governance/fasyankes-clinical-go-live-approval-template.md`.

Site-governed examples (unless higher authority requires otherwise): PLANNED encounter documentation · FINISHED late entry · backdating · correction authority · permission assignment · AI activation · local workflow.

---

## 14. Evidence, tests, waivers, release

### Test types

| Test ID | Purpose |
|---|---|
| `REGULATORY_TRACEABILITY_TEST` | Official source + scope per regulation row |
| `INTEROPERABILITY_CONFORMANCE_TEST` | LOINC/UCUM / SATUSEHAT profile conformance |
| `CLINICAL_SAFETY_CONTROL_TEST` | Wrong-patient, deny-default, no silent overwrite |
| `PRIVACY_RESPONSIBILITY_TEST` | Controller/processor + DPA per deployment |
| `SITE_GO_LIVE_EVIDENCE_TEST` | Named site approvals before clinical activation |
| `OPERATIONAL_TABLETOP_TEST` | Incident / breach / rollback exercise |
| `AI_REGULATORY_APPLICABILITY_TEST` | Per-use-case classification before AI activation |
| `AI_TECHNICAL_EVALUATION_TEST` | TEVV artifacts for clinical AI |

### Waivers (`OPS-001`)

Fields: `control_id` · risk · reason · compensating_controls · owner · approver · created_at · expires_at · review_date.

No permanent anonymous waivers. High-risk controls (wrong-patient isolation, cross-tenant isolation, auth bypass, clinical auth bypass, terminology ambiguity, applicable AI regulatory class) — normally **no** open production waiver.

### Release gate (future clinical features)

P0=0; provider P1=0; required tests passed; regulatory applicability assessed where relevant; site policy defined; terminology approved where needed; security/privacy review; rollback; observability. Not a claim of zero bugs.

### Review triggers (event-driven — not calendar-only)

Regulatory change · SATUSEHAT profile change · terminology version · new facility type · new AI intended use · model/provider change · security incident · clinical near miss · major architecture change.

---

## 15. Severity model (provider foundation)

| Severity | Current provider-foundation status |
|---|---|
| **P0** | none |
| **P1 provider-foundation unresolved** | **none** (post-hardening) |
| **P2 inherited** | DENIED-audit rollback |
| **P3** | Site Clinical Policy Profile not persisted; voluntary ISO mapped not certified |

Capability blockers use **gate types**, not global P1:

- Observation / Vitals → `SITE_APPROVAL_PENDING`
- Controller/processor → `DEPLOYMENT_GATE`
- AI regulatory → `AI_ACTIVATION_GATE`

---

## 16. Related documents

| Doc | Purpose |
|---|---|
| `indonesia-health-regulatory-applicability-matrix.md` | Regulatory sources + control detail |
| `provider-clinical-safety-defaults.md` | Clinical safety defaults + CLIN-* IDs |
| `fasyankes-clinical-go-live-approval-template.md` | Site activation |
| `ai-health-governance-policy.md` | AI policy |
| `ai-use-case-regulatory-and-clinical-assessment-template.md` | Per-use-case gate |
| `docs/gates/provider-governance-assurance-gate.md` | Desk verification |
| `docs/gates/provider-governance-hardening-gate.md` | Hardening verification |
| Observation / Vital Signs design gates | Remain **BLOCKED** pending site human approval |
