# Provider governance hardening gate

**Date:** 2026-08-28
**Kind:** GOVERNANCE HARDENING VERIFICATION — evidence traceability / regulatory applicability
**Baseline HEAD:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Alembic:** `20260814_0019` only · **0020:** NOT CREATED
**Pass type:** GOVERNANCE HARDENING-ONLY — no production code · no commit · no tag · no push · no freeze

```
HEALTHCARE SOFTWARE PROVIDER GOVERNANCE FOUNDATION = HARDENED
PROVIDER GOVERNANCE ASSURANCE = PASS WITH DEPLOYMENT / SITE-SPECIFIC GATES
PROVIDER GOVERNANCE FOUNDATION = NOT YET FROZEN

OBSERVATION / VITAL SIGNS WRITE DESIGN = BLOCKED BY SITE/CLINICAL APPROVAL
AI CLINICAL IMPLEMENTATION = NOT STARTED
MIGRATION 0020 = NOT CREATED
```

This gate is **not** legal advice, **not** certification, and **not** a claim of full regulatory compliance.

---

## 1. Baseline verification

| Item | Expected | Result |
|---|---|---|
| HEAD | `c55d259180c4864b56ea40e4c24833c9cd438d68` | **PASS** |
| Tag | `clinical-note-write-frozen` | **PASS** |
| Branch | `main` == `origin/main` | **PASS** |
| Alembic heads | `20260814_0019` exactly one head | **PASS** (19 migration files; no `0020`) |
| Production code changed | No | **PASS** — working tree is docs-only |
| Backend / frontend / PDP / MPI / Clinical Read modified | No | **PASS** |

---

## 2. Files reviewed / hardened (this pass)

### Governance (created or updated)

| Path | Action |
|---|---|
| `docs/governance/healthcare-software-provider-governance-baseline.md` | Hardened — control registry, gate types, waiver model |
| `docs/governance/indonesia-health-regulatory-applicability-matrix.md` | Hardened — official source snapshots, applicability columns |
| `docs/governance/provider-clinical-safety-defaults.md` | Hardened — stable control IDs |
| `docs/governance/fasyankes-clinical-go-live-approval-template.md` | Hardened — expanded evidence checklist |
| `docs/governance/ai-health-governance-policy.md` | Hardened — AI applicability enum; Permenkes 11 scope correction |
| `docs/governance/ai-use-case-regulatory-and-clinical-assessment-template.md` | Hardened — default NOT_ASSESSED / BLOCKED |
| `docs/gates/provider-governance-assurance-gate.md` | Updated — verdict + severity/gate corrections |
| `docs/gates/provider-governance-hardening-gate.md` | **Created** — this document |

### Observation / terminology (consistency review — no unblock)

| Path | Status |
|---|---|
| `docs/architecture/observation-vital-signs-write-workflow-design.md` | Reviewed — classifications consistent |
| `docs/gates/observation-vital-signs-write-workflow-design-approval.md` | Updated — gate-type severity correction |
| `docs/architecture/vital-signs-terminology-candidate-catalog.md` | Reviewed |
| `docs/gates/vital-signs-terminology-human-approval.md` | Reviewed — 0 APPROVED entries |
| `docs/architecture/vital-signs-terminology-approved-catalog.md` | Reviewed — 0 APPROVED entries |

---

## 3. Authority hierarchy (frozen)

Every material governance rule uses **exactly one** primary classification:

| Code | Meaning |
|---|---|
| `LEGAL_REQUIRED` | Applicable law/regulation obligation (scope-dependent) |
| `NATIONAL_INTEROPERABILITY_PROFILE` | SATUSEHAT / national exchange mapping evidence |
| `JOINT_CONTRACTUAL_CONTROL` | Contract / DPA / shared legal control |
| `VENDOR_SAFETY_DEFAULT` | Provider product safety default (may exceed minimum law) |
| `SITE_CLINICAL_POLICY` | Facility clinical SOP / medical governance |
| `SITE_ADMINISTRATIVE_POLICY` | Facility IT/admin configuration |
| `AI_REGULATORY_GATE` | AI/SaMD applicability assessment required before activation |
| `DEFERRED` | Explicitly not decided / not in scope |

Hierarchy (non-substitutable):

1. Applicable Indonesian law / regulation
2. National interoperability profiles
3. Contract / DPA
4. Provider safety defaults
5. Site clinical / administrative policy
6. Deferred items remain inactive

Regulation and vendor recommendation are **not** blurred.

---

## 4. Official source verification (snapshot metadata)

Traceability only — **not** full regulation copies.

| Source ID | Official title | Number/year | Official issuer | Official reference | Verified date | Status (official) | Scope notes |
|---|---|---|---|---|---|---|---|
| REG-PMK-24-2022 | Peraturan Menteri Kesehatan tentang Rekam Medis | Permenkes 24/2022 | Kementerian Kesehatan | https://jdih.kemkes.go.id/documents/peraturan-menteri-kesehatan-nomor-24-tahun-2022 | 2026-08-28 | **Berlaku** | RME obligations for covered health facilities |
| REG-UU-PDP-27-2022 | Undang-Undang Pelindungan Data Pribadi | UU 27/2022 | RI / Komdigi JDIH mirror | https://jdih.komdigi.go.id/produk_hukum/view/id/832 | 2026-08-28 | **Berlaku** | Personal data protection; health data = specific personal data |
| REG-PMK-19-2024 | Peraturan Menteri Kesehatan tentang Penyelenggaraan Pusat Kesehatan Masyarakat | Permenkes 19/2024 | Kementerian Kesehatan | https://jdih.kemkes.go.id/documents/peraturan-menteri-kesehatan-nomor-19-tahun-2024 | 2026-08-28 | **Berlaku** | Puskesmas operational governance — site profile, not product fork |
| REG-SE-KOMDIGI-9-2023 | Surat Edaran Etika Kecerdasan Artifisial | SE Menkominfo 9/2023 | Kementerian Komunikasi dan Informatika | https://jdih.komdigi.go.id/produk_hukum/view/id/883 | 2026-08-28 | **Berlaku** (circular) | **Surat Edaran / ethics guidance** — not equivalent normative hierarchy to UU |
| REG-PMK-11-2025 | Standar Kegiatan Usaha dan Standar Produk/Jasa PBBR Subsektor Kesehatan | Permenkes 11/2025 | Kementerian Kesehatan | https://jdih.kemkes.go.id/documents/peraturan-menteri-kesehatan-nomor-11-tahun-2025 | 2026-08-28 | **Berlaku** | Risk-based business/product standards — **feature-specific applicability only** |
| REG-SATUSEHAT | SATUSEHAT interoperability profiles | evolving | Kementerian Kesehatan | https://satusehat.kemkes.go.id (operational portal) | 2026-08-28 | Evolving | National HIE mapping evidence — distinct from site clinical approval |

**What verified sources support:** traceable regulatory existence, official status where listed, high-level scope.
**What they do NOT automatically imply:** platform-wide certification, universal SaMD classification for all AI features, site clinical approval, or that every EMR function is a regulated medical product.

---

## 5. Regulation-specific verified facts

### 5.1 Permenkes 24/2022 — Rekam Medis

| Fact | Evidence |
|---|---|
| Status | **Berlaku** (JDIH Kemenkes, verified 2026-08-28) |
| Applies to RME at covered facilities | Permenkes 24/2022 subject: REKAM MEDIS |
| Facility types | Includes Puskesmas, clinic, hospital, and other covered facility types under the regulation's scope — **desk mapping; facility-type detail requires counsel/SOP** |
| Platform relevance | RME confidentiality, integrity, availability, security, digital/integrated records enablement |

**Does NOT support inferring:** specific API contracts, encounter-status rules, vital-sign LOINC choices, or arbitrary technical timestamps not stated in the regulation.

### 5.2 UU 27/2022 — Pelindungan Data Pribadi

| Fact | Evidence (Pasal / penjelasan UU) |
|---|---|
| Health data = specific personal data | Pasal 4 — *data dan informasi kesehatan* listed under specific personal data |
| Controller obligations | Pasal 20+ — lawful basis, transparency, minimization, accuracy, security, etc. |
| Processor obligations | Pasal 21+ — process on controller instructions; contractual/security duties |
| Data-subject rights | Pasal 6–11 — access, correction, deletion, portability, objection, etc. |
| Transfer considerations | Transfer rules in UU — deployment/contract specific |

**Does NOT support assuming:** vendor is always **Processor** or always **Controller** — role is **deployment-specific** (`JOINT_CONTRACTUAL_CONTROL`).

### 5.3 Controller / processor assessment

| Classification | Detail |
|---|---|
| Primary | `JOINT_CONTRACTUAL_CONTROL` |
| Gate type | **`DEPLOYMENT_GATE`** — not a provider-platform P1 defect |
| Per deployment requires | legal entity · processing purposes · decision-making authority · controller role · processor role · possible independent/joint role · subprocessors · contractual evidence |
| If unresolved at go-live | **`DEPLOYMENT BLOCKED`** for that customer |
| Platform defect? | **No** — absence of customer-specific assessment is expected pre-contract |

Control: **PRIV-001** (see regulatory matrix).

### 5.4 Permenkes 19/2024 — Puskesmas

| Fact | Platform implication |
|---|---|
| Status **Berlaku** | Puskesmas-specific operational/site profile justified |
| Shared architecture | **Preferred** — no separate software fork |
| Classification | `LEGAL_REQUIRED` (Puskesmas context) + `SITE_*` for local SOP |

### 5.5 SE Menkominfo 9/2023 — AI ethics

| Fact | Platform implication |
|---|---|
| Nature | **Surat Edaran** — ethics guidance for AI programming businesses, public PSE, private PSE |
| Legal force | **Not** equivalent to UU/statute normative hierarchy |
| Use | AI governance evidence / voluntary alignment input |
| Classification | `AI_REGULATORY_GATE` (ethics alignment) — not automatic SaMD determination |

### 5.6 Permenkes 11/2025 — scope handling (critical)

| Supported | Not supported |
|---|---|
| Regulation **exists** and is **Berlaku** for risk-based health subsector business/product standards | Blanket statement that **every AI feature** in the platform is medical-device AI |
| Feature-specific classification may be required **where applicable** to regulated product/business class | Presenting GMLP/transparency/incident controls as **direct legal requirements for all EMR features** without classification memo |
| `LEGAL_REQUIRED` **only if** use case classified applicable | Self-declaring "not medical device" by engineering alone |

**Correction applied:** all Permenkes 11/2025 AI obligation sentences softened to *"where applicable to the relevant regulated product classification"* unless backed by feature-specific assessment evidence.

---

## 6. AI medical purpose gate (frozen)

Naming alone (`assistant`, `copilot`, `recommendation`, `summary`) does **not** determine regulatory class. Classification depends on **intended use** and **actual function**.

```
AI_REGULATORY_APPLICABILITY =
  NOT_ASSESSED | NOT_APPLICABLE | POTENTIALLY_APPLICABLE | APPLICABLE
```

| State | Production clinical activation |
|---|---|
| `NOT_ASSESSED` (default) | **BLOCKED** |
| `NOT_APPLICABLE` | Requires authorized review record |
| `POTENTIALLY_APPLICABLE` | **BLOCKED** until review completes |
| `APPLICABLE` | Additional regulated-product controls per assessment |

Gate type: **`AI_ACTIVATION_GATE`** — not provider-foundation P1.

Autonomous clinical AI: **`PROHIBITED BY DEFAULT`** — classification `VENDOR_SAFETY_DEFAULT` + `AI_REGULATORY_GATE`. **Not** claimed as literal national statutory prohibition unless specific legal evidence exists for the use case.

---

## 7. SATUSEHAT mappings (national profile — not site-approved)

Classification: **`NATIONAL_INTEROPERABILITY_PROFILE`**

| Concept | LOINC | UCUM | Display (interop) |
|---|---|---|---|
| Heart Rate | 8867-4 | `/min` | beats/min |
| Respiratory Rate | 9279-1 | `/min` | breaths/min |
| Body Temperature | 8310-5 | `Cel` | °C / Cel |
| Systolic BP | 8480-6 | `mm[Hg]` | mmHg |
| Diastolic BP | 8462-4 | `mm[Hg]` | mmHg |
| Body Height | 8302-2 | `cm` | cm |
| Body Weight | 29463-7 | `kg` | kg |

National profile evidence ≠ provider catalog activation ≠ site clinical acceptance.

Terminology lifecycle: **CANDIDATE → evidence → national mapping → engineering review → provider catalog approval → site clinical approval (where required) → ACTIVE**.

---

## 8. Encounter / time / access / correction (normalized)

| Topic | Classification |
|---|---|
| Encounter required (Manual Vitals product) | Product / interoperability contract |
| `IN_PROGRESS` allow | `VENDOR_SAFETY_DEFAULT` |
| `CANCELLED` / `ENTERED_IN_ERROR` reject | `VENDOR_SAFETY_DEFAULT` |
| `PLANNED` | `SITE_CLINICAL_POLICY` |
| `FINISHED` / late entry | `SITE_CLINICAL_POLICY` |
| `effective_at` required | `VENDOR_SAFETY_DEFAULT` |
| `recorded_at` server-generated | `VENDOR_SAFETY_DEFAULT` / data integrity contract |
| Backdating | `SITE_CLINICAL_POLICY` |
| Future skew | Site / technical policy — **no universal 5-minute national rule** |
| Permission engine enforcement | Provider (`VENDOR_SAFETY_DEFAULT`) |
| Who receives which permission | Site (`SITE_ADMINISTRATIVE_POLICY`) |
| No universal NURSE/DOCTOR/REGISTRAR backend roles | Frozen design |
| No silent clinical overwrite | `VENDOR_SAFETY_DEFAULT` |
| Correction who/when/reason | `SITE_CLINICAL_POLICY` within supported product capabilities |

---

## 9. Legal review status model

Replaces vague P2 for unresolved legal interpretation:

```
LEGAL_REVIEW = NOT_REQUIRED | PENDING | COMPLETE | ESCALATION_REQUIRED
```

Pending counsel review is **not** automatically a software defect.

| Item | LEGAL_REVIEW |
|---|---|
| Permenkes 24/2022 facility-type detail mapping | PENDING |
| UU PDP cross-border transfer for SaaS deployments | PENDING |
| Permenkes 11/2025 feature-specific SaMD paths | PENDING (per use case) |
| Provider baseline authority labels | NOT_REQUIRED (descriptive) |

---

## 10. Severity and gate classification (corrected)

### Provider foundation defects (P0 / P1)

| Severity | Count | Notes |
|---|---|---|
| **P0** | **none** | |
| **P1 provider-foundation unresolved** | **none** | Hardening pass complete |

### Non-severity gate types (do not force into P1)

| Gate | Items |
|---|---|
| **`DEPLOYMENT_GATE`** | Controller/processor assessment · DPA · per-customer privacy role · go-live contractual evidence |
| **`SITE_APPROVAL_PENDING`** | Vital terminology human approval (0 APPROVED) · Observation write design · site SOP/training/UAT |
| **`AI_ACTIVATION_GATE`** | Intended-use/regulatory assessment · TEVV · model/version pinning · site AI acceptance |
| **`LEGAL_REVIEW_PENDING`** | Counsel rows in regulatory matrix |

### Inherited technical debt

| Severity | Item |
|---|---|
| **P2** | DENIED-audit rollback (inherited) |
| **P3** | Site Clinical Policy Profile not persisted in DB (design only) |
| **P3** | Voluntary ISO frameworks mapped — not certified |

Historical `patient_identity_id` non-rewrite: **frozen MPI invariant** — not P2.

### Observation / vitals capability blocker

| Status | Gate |
|---|---|
| OBSERVATION / VITAL SIGNS WRITE DESIGN | **BLOCKED** |
| Reason | **`SITE_APPROVAL_PENDING`** — not global provider P1 |
| Migration 0020 | **NOT CREATED** |

---

## 11. Governance test matrix

| Test ID | Purpose | Evidence required for PASS |
|---|---|---|
| `REGULATORY_TRACEABILITY_TEST` | Each regulation row has official source + scope boundary | JDIH/BPK/SATUSEHAT reference; verified date |
| `INTEROPERABILITY_CONFORMANCE_TEST` | LOINC/UCUM mappings match national profile | Mapping doc + version |
| `CLINICAL_SAFETY_CONTROL_TEST` | Vendor defaults enforced in product | Test report / config evidence |
| `PRIVACY_RESPONSIBILITY_TEST` | Controller/processor roles documented per deployment | Signed DPA / role assessment |
| `SITE_GO_LIVE_EVIDENCE_TEST` | Site checklist complete before clinical activation | Named dated approvals |
| `OPERATIONAL_TABLETOP_TEST` | Incident / breach / rollback exercised | Tabletop record |
| `AI_REGULATORY_APPLICABILITY_TEST` | Each AI use case classified before activation | Assessment artifact |
| `AI_TECHNICAL_EVALUATION_TEST` | TEVV passed for clinical AI | Evaluation artifact |

**Rule:** No control gets PASS solely because a policy document exists.

---

## 12. Adversarial governance tests

| Scenario | Expected outcome | Result |
|---|---|---|
| A. Vendor claims all AI is non-medical-device | Blocked by intended-use assessment (`AI_REGULATORY_GATE`) | **PASS** (policy) |
| B. Hospital asks vendor to make all doctors superadmin | Deny-by-default; site approval cannot bypass hard security | **PASS** (policy) |
| C. Puskesmas different workflow | Site profile, not code fork | **PASS** (policy) |
| D. Site has no controller/processor assessment | Deployment governance incomplete — **DEPLOYMENT BLOCKED** | **PASS** (policy) |
| E. AI model silently changes provider version | Change-control / evaluation gate required | **PASS** (policy) |
| F. SATUSEHAT terminology changes | Versioned terminology review — no unreviewed mutation | **PASS** (policy) |
| G. Clinical feature implemented but no SOP/training | Site go-live blocked | **PASS** (policy) |

Policy-level PASS = design documented. Production enforcement PASS requires future implementation evidence.

---

## 13. Waiver model

Explicit waiver fields (no permanent anonymous waivers):

`control_id` · risk · reason · compensating_controls · owner · approver · created_at · expires_at · review_date

**High-risk — normally no open production waiver:**

- Wrong-patient isolation
- Cross-tenant isolation
- Authentication bypass
- Clinical authorization bypass
- Required terminology ambiguity
- AI regulatory classification when applicable

Control: **OPS-001** (see provider baseline).

---

## 14. ISO / NIST / WHO classification

| Framework | Classification |
|---|---|
| ISO 27001 / 27701 / 42001 / 7101 / 14971 | `VOLUNTARY_ALIGNMENT` / `CERTIFICATION_READINESS` |
| IEC 62304 | Readiness **if** SaMD path applicable |
| NIST AI RMF | `REFERENCE_FRAMEWORK` |
| WHO AI-for-health | Ethics mapping reference |

**Never write CERTIFIED** unless certification evidence exists.

---

## 15. Consistency check (overclaim scan)

Searched governance + Observation/terminology docs for: *mandatory*, *required by law*, *SATUSEHAT requires*, *medical device* (blanket), *certified*, *compliant*, *approved*, *FULLY COMPLIANT*.

| Finding | Action |
|---|---|
| "mandatory labels" in baseline §2 | **OK** — refers to classification label requirement, not legal mandate |
| "TEVV mandatory for clinical AI" in AI policy | **OK** — vendor activation gate (`VENDOR_SAFETY_DEFAULT`), not statute |
| Permenkes 11 blanket AI obligations | **Corrected** — softened to feature-specific / where applicable |
| SATUSEHAT-mandatory claims for vitals timing | **Already corrected** — `VENDOR_SAFETY_DEFAULT` |
| Certification claims | **None found** in governance docs |

---

## 16. Unresolved items (explicit — not hardening blockers)

| Item | Gate / status |
|---|---|
| Vital terminology human approval (0 APPROVED) | `SITE_APPROVAL_PENDING` |
| Observation write implementation gaps vs Note Write | Capability design — blocked |
| Per-deployment controller/processor assessment | `DEPLOYMENT_GATE` |
| Counsel confirmation of Permenkes 24/2022 amendment state | `LEGAL_REVIEW_PENDING` |
| AI use cases | `NOT_ASSESSED` — no clinical AI implemented |
| Site Clinical Policy Profile persistence | Design only (P3) |

---

## 17. Explicit non-actions

No Observation write implementation · no migration `0020` · no AI implementation · no backend/frontend production changes · no PDP/MPI/Clinical Read changes · no invented site approvals · no commit · no tag · no push · no final-freeze document.

---

## 18. Final verdict

```
PROVIDER GOVERNANCE HARDENING = COMPLETE

HEALTHCARE SOFTWARE PROVIDER GOVERNANCE FOUNDATION = HARDENED
PROVIDER GOVERNANCE ASSURANCE = PASS WITH DEPLOYMENT / SITE-SPECIFIC GATES
PROVIDER GOVERNANCE FOUNDATION = NOT YET FROZEN

P0 = none
P1 provider-foundation unresolved = none

DEPLOYMENT GATES = controller/processor · DPA · per-customer requirements
AI ACTIVATION GATES = intended-use · TEVV · site approval (per use case)
OBSERVATION / VITAL SIGNS WRITE DESIGN = BLOCKED BY SITE/CLINICAL APPROVAL
AI CLINICAL IMPLEMENTATION = NOT STARTED
MIGRATION 0020 = NOT CREATED

NO COMMIT · NO TAG · NO PUSH
```

All material regulatory claims in this pass are traceable to official sources listed in §4 or explicitly marked as vendor default / pending legal review. **No hardening blockers.**
