# Indonesia health regulatory applicability matrix

**Date:** 2026-08-28
**Kind:** REGULATORY TRACEABILITY — governance design only
**Baseline:** `c55d259180c4864b56ea40e4c24833c9cd438d68`
**Hardening gate:** `docs/gates/provider-governance-hardening-gate.md`

**Disclaimer:** This is **not legal advice**. Applicability depends on facts, contracts, deployment model, and official guidance. Do not claim obligations beyond actual scope. Review with qualified counsel before production assertions.

Authority labels: `LEGAL_REQUIRED` · `NATIONAL_INTEROPERABILITY_PROFILE` · `VENDOR_SAFETY_DEFAULT` · `SITE_CLINICAL_POLICY` · `SITE_ADMINISTRATIVE_POLICY` · `JOINT_CONTRACTUAL_CONTROL` · `AI_REGULATORY_GATE` · `DEFERRED`.

---

## Column legend

| Column | Meaning |
|---|---|
| **SOURCE VERIFIED** | Official issuer reference captured with verified date |
| **APPLICABILITY ASSESSED** | Platform/facility relevance assessed at desk level |
| **LEGAL INTERPRETATION REQUIRED** | Counsel needed before binding production claim |
| **IMPLEMENTATION CONTROL** | Provider-platform control ID(s) |
| **SITE CONTROL** | Facility-side control / evidence |
| **EVIDENCE** | Artifact required for PASS |
| **LEGAL_REVIEW** | `NOT_REQUIRED` · `PENDING` · `COMPLETE` · `ESCALATION_REQUIRED` |

---

## Official source snapshots

| Source ID | Official title | Number/year | Official source | Verified | Status | Scope |
|---|---|---|---|---|---|---|
| REG-PMK-24-2022 | Permenkes tentang Rekam Medis | 24/2022 | https://jdih.kemkes.go.id/documents/peraturan-menteri-kesehatan-nomor-24-tahun-2022 | 2026-08-28 | Berlaku | RME at covered facilities |
| REG-UU-PDP-27-2022 | UU Pelindungan Data Pribadi | 27/2022 | https://jdih.komdigi.go.id/produk_hukum/view/id/832 | 2026-08-28 | Berlaku | Personal data; health = specific |
| REG-PMK-19-2024 | Permenkes Penyelenggaraan Puskesmas | 19/2024 | https://jdih.kemkes.go.id/documents/peraturan-menteri-kesehatan-nomor-19-tahun-2024 | 2026-08-28 | Berlaku | Puskesmas governance |
| REG-SE-KOMDIGI-9-2023 | SE Etika Kecerdasan Artifisial | SE 9/2023 | https://jdih.komdigi.go.id/produk_hukum/view/id/883 | 2026-08-28 | Berlaku (circular) | AI ethics guidance — not UU-equivalent |
| REG-PMK-11-2025 | Standar Kegiatan Usaha & Produk/Jasa PBBR Subsektor Kesehatan | 11/2025 | https://jdih.kemkes.go.id/documents/peraturan-menteri-kesehatan-nomor-11-tahun-2025 | 2026-08-28 | Berlaku | Risk-based business/product standards |
| REG-SATUSEHAT | SATUSEHAT interoperability | evolving | https://satusehat.kemkes.go.id | 2026-08-28 | Evolving | National HIE profiles |

Store traceability metadata only — do not copy full copyrighted regulation text unless licensing permits.

---

## Matrix

| Source | SOURCE VERIFIED | APPLICABILITY ASSESSED | LEGAL INTERPRETATION REQUIRED | Classification | IMPLEMENTATION CONTROL | SITE CONTROL | EVIDENCE | LEGAL_REVIEW |
|---|---|---|---|---|---|---|---|---|
| **Permenkes 24/2022** Rekam Medis | Yes — JDIH Kemenkes | Yes — EMR/RME enablement | Facility-type detail; retention operationalization | `LEGAL_REQUIRED` (facility-facing; provider enables) | REG-001 | Operate EMR per SOP; staff access; retention practice | Policy mapping; feature checklist; site SOP | PENDING |
| **UU 27/2022** PDP | Yes — JDIH Komdigi | Yes — health data processing | Controller/processor role per deployment; cross-border | `LEGAL_REQUIRED` + `JOINT_CONTRACTUAL_CONTROL` | PRIV-001, PRIV-002, SEC-001 | Lawful basis; staff access; subject-request coordination | Role assessment; DPA; security evidence | PENDING |
| **SATUSEHAT** profiles | Yes — portal | Yes — vitals LOINC/UCUM | Profile version drift | `NATIONAL_INTEROPERABILITY_PROFILE` | TERM-001 | Facility onboarding; operational exchange | Mapping evidence; conformance tests | NOT_REQUIRED |
| **Permenkes 19/2024** Puskesmas | Yes — JDIH Kemenkes | Yes — site type profile | Local service scope under Permenkes | `LEGAL_REQUIRED` (Puskesmas) + `SITE_*` | SITE-001 | Local governance, services, staffing | Profile checklist; go-live | PENDING |
| **SE Menkominfo 9/2023** AI ethics | Yes — JDIH Komdigi | Yes — AI governance input | Not binding statute equivalence | Ethics alignment under `AI_REGULATORY_GATE` | AI-001 | Local AI use approval | Use-case assessments | NOT_REQUIRED |
| **Permenkes 11/2025** PBBR subsektor kesehatan | Yes — JDIH Kemenkes | Partial — **regulation exists**; **feature-specific class TBD** | SaMD / regulated product class per use case | `LEGAL_REQUIRED` **if classified applicable**; else `AI_REGULATORY_GATE` | AI-002 | Clinical intended use; local approval | Classification memo; risk file; evaluation | PENDING (per use case) |

---

## Regulation detail records

### REG-001 — Permenkes 24/2022 (Rekam Medis)

| Field | Value |
|---|---|
| **control_id** | REG-001 |
| **title** | Electronic medical record obligations enablement |
| **authority** | Permenkes 24/2022 |
| **classification** | `LEGAL_REQUIRED` |
| **requirement** | Provider platform supports secure, confidential, integral, available digital clinical records for covered facilities |
| **owner** | Provider product + site operations |
| **applicability** | Hospitals, clinics, Puskesmas, and other facility types within Permenkes 24/2022 scope |
| **evidence** | JDIH status Berlaku; feature mapping checklist; site SOP |
| **test method** | `REGULATORY_TRACEABILITY_TEST` + site go-live checklist |
| **status** | SOURCE VERIFIED — implementation mapping OPEN |
| **exceptions** | None assumed |
| **review trigger** | Permenkes amendment; new facility type; major RME feature |

**Supports:** RME, confidentiality, integrity, availability, security, digital records.
**Does NOT automatically imply:** specific API design, encounter-status rules, vital LOINC choices, or timing policies.

### PRIV-001 — UU 27/2022 health data as specific personal data

| Field | Value |
|---|---|
| **control_id** | PRIV-001 |
| **title** | Health data treated as specific personal data |
| **authority** | UU 27/2022 Pasal 4 |
| **classification** | `LEGAL_REQUIRED` |
| **requirement** | Health data processing follows specific-personal-data protections |
| **owner** | Joint — controller determined per deployment |
| **applicability** | All health data processing in platform scope |
| **evidence** | Official UU text; processing inventory |
| **test method** | `PRIVACY_RESPONSIBILITY_TEST` |
| **status** | SOURCE VERIFIED |
| **exceptions** | Lawful basis exceptions per UU — counsel required |
| **review trigger** | UU amendment; PP PDP changes; new processing purpose |

**Supports:** heightened protection for health data; controller/processor framework; data-subject rights.
**Does NOT automatically imply:** vendor is always Processor.

### PRIV-002 — Controller / processor role assessment

| Field | Value |
|---|---|
| **control_id** | PRIV-002 |
| **title** | Per-deployment controller/processor classification |
| **authority** | UU 27/2022 + contract |
| **classification** | `JOINT_CONTRACTUAL_CONTROL` |
| **requirement** | Before customer go-live: document legal entity, purposes, decision authority, controller role, processor role, possible joint/independent role, subprocessors, contractual evidence |
| **owner** | Joint — legal + customer + provider |
| **applicability** | Every customer deployment |
| **evidence** | Signed role assessment; DPA |
| **test method** | `PRIVACY_RESPONSIBILITY_TEST` |
| **status** | **DEPLOYMENT_GATE** — PENDING per deployment |
| **exceptions** | None for production without assessment |
| **review trigger** | Contract change; subprocessor change; processing purpose change |

**Gate:** If unresolved at go-live → **DEPLOYMENT BLOCKED**.
**Not** a provider-platform P1 defect when no customer assessment exists yet.

### SEC-001 — Security measures for personal data processing

| Field | Value |
|---|---|
| **control_id** | SEC-001 |
| **title** | Technical and organizational security for health data |
| **authority** | UU 27/2022 + provider baseline |
| **classification** | `LEGAL_REQUIRED` + `VENDOR_SAFETY_DEFAULT` |
| **requirement** | Access control, encryption, audit, incident capability — provider implements; site configures grants |
| **owner** | Provider (controls) + site (assignments) |
| **applicability** | All deployments |
| **evidence** | Security config; test reports; ISO readiness mapping (voluntary) |
| **test method** | `CLINICAL_SAFETY_CONTROL_TEST` + security review |
| **status** | Partial — product controls exist; formal cert not claimed |
| **exceptions** | Documented waiver only per OPS-001 |
| **review trigger** | Security incident; major architecture change |

### TERM-001 — SATUSEHAT national interoperability mappings

| Field | Value |
|---|---|
| **control_id** | TERM-001 |
| **title** | National LOINC/UCUM vitals profile |
| **authority** | SATUSEHAT / national profile |
| **classification** | `NATIONAL_INTEROPERABILITY_PROFILE` |
| **requirement** | Document and version national mappings; implement only after provider + site approval path |
| **owner** | Provider engineering + interoperability |
| **applicability** | Vitals exchange / Manual Vitals product (when approved) |
| **evidence** | Mapping table; profile version |
| **test method** | `INTEROPERABILITY_CONFORMANCE_TEST` |
| **status** | Evidence documented — **not SITE_CLINICAL_APPROVED** |
| **exceptions** | Site may restrict activated subset |
| **review trigger** | SATUSEHAT profile change; new LOINC release |

Mappings: HR 8867-4 `/min`; RR 9279-1 `/min`; Temp 8310-5 `Cel`; Sys BP 8480-6 `mm[Hg]`; Dia BP 8462-4 `mm[Hg]`; Height 8302-2 `cm`; Weight 29463-7 `kg`.

### SITE-001 — Puskesmas site profile (Permenkes 19/2024)

| Field | Value |
|---|---|
| **control_id** | SITE-001 |
| **title** | Puskesmas operational/site policy profile |
| **authority** | Permenkes 19/2024 |
| **classification** | `LEGAL_REQUIRED` (context) + `SITE_CLINICAL_POLICY` |
| **requirement** | Shared platform with Puskesmas-specific policy profile — **no product fork** |
| **owner** | Site + provider configuration |
| **applicability** | Puskesmas deployments |
| **evidence** | Site profile version; go-live checklist |
| **test method** | `SITE_GO_LIVE_EVIDENCE_TEST` |
| **status** | Design only |
| **exceptions** | N/A |
| **review trigger** | Permenkes 19 amendment; new Puskesmas service model |

### AI-001 — SE Menkominfo 9/2023 ethics alignment

| Field | Value |
|---|---|
| **control_id** | AI-001 |
| **title** | AI ethics guidance alignment |
| **authority** | SE Menkominfo 9/2023 |
| **classification** | `AI_REGULATORY_GATE` (ethics reference) |
| **requirement** | Use as governance evidence for transparency, accountability, privacy, risk management — **not** as statute-equivalent mandate |
| **owner** | Provider AI governance |
| **applicability** | AI programming businesses; public PSE; private PSE (per SE audience) |
| **evidence** | AI policy mapping to SE principles |
| **test method** | `AI_REGULATORY_APPLICABILITY_TEST` |
| **status** | SOURCE VERIFIED — voluntary alignment |
| **exceptions** | N/A |
| **review trigger** | New AI statute/Perpres; SE revision |

**Nature:** Surat Edaran — **not** equivalent normative hierarchy to UU.

### AI-002 — Permenkes 11/2025 feature-specific applicability

| Field | Value |
|---|---|
| **control_id** | AI-002 |
| **title** | Risk-based health subsector product/business standards — per use case |
| **authority** | Permenkes 11/2025 |
| **classification** | `LEGAL_REQUIRED` **if applicable**; else `AI_REGULATORY_GATE` |
| **requirement** | Each potentially medical-purpose AI use case: separate applicability assessment before production |
| **owner** | Regulatory reviewer + product owner |
| **applicability** | Regulated health business/product classes — **not all EMR features by default** |
| **evidence** | Classification memo; risk file; TEVV where applicable |
| **test method** | `AI_REGULATORY_APPLICABILITY_TEST` + `AI_TECHNICAL_EVALUATION_TEST` |
| **status** | REGULATION EXISTS — feature assessments NOT_ASSESSED |
| **exceptions** | None — no blanket "non-medical-device" self-declaration |
| **review trigger** | New AI intended use; Permenkes 11 amendment; model change |

**Supports:** risk-based standards framework exists for subsektor kesehatan products/services.
**Does NOT support:** claiming every AI feature (assistant/copilot/summary) is automatically SaMD-regulated **or** automatically exempt.

---

## Voluntary / certification-readiness frameworks (not claimed certified)

| Framework | Role | Classification |
|---|---|---|
| ISO/IEC 27001:2022 | Information security MS readiness | `VOLUNTARY_ALIGNMENT` |
| ISO/IEC 27701:2025 | Privacy information MS readiness | `VOLUNTARY_ALIGNMENT` |
| ISO 7101 | Healthcare quality org concepts | `REFERENCE_FRAMEWORK` |
| ISO 14971 | Risk management for MD software path | `CERTIFICATION_READINESS` if SaMD |
| IEC 62304 | Medical device software lifecycle | `CERTIFICATION_READINESS` if SaMD |
| ISO/IEC 42001:2023 | AI management system | `VOLUNTARY_ALIGNMENT` |
| NIST AI RMF | GOVERN / MAP / MEASURE / MANAGE | `REFERENCE_FRAMEWORK` |
| WHO AI-for-health principles | Ethics mapping | `REFERENCE_FRAMEWORK` |

Never write **CERTIFIED** unless certification evidence exists.

---

## Controller / processor role assessment (required per deployment)

| Question | Result | Gate |
|---|---|---|
| Who determines purposes of health data processing? | PENDING (deployment-specific) | `DEPLOYMENT_GATE` |
| Provider role | PENDING — Controller / Processor / Joint / Mixed | `DEPLOYMENT_GATE` |
| Site role | PENDING | `DEPLOYMENT_GATE` |
| Cross-border / data location | PENDING | `DEPLOYMENT_GATE` |
| Approver | PENDING | `DEPLOYMENT_GATE` |
| Subprocessors documented | PENDING | `DEPLOYMENT_GATE` |

Do **not** assume provider is always the same PDP legal role.
Unresolved at go-live → **DEPLOYMENT BLOCKED** (not platform P1).

---

## DPA readiness checklist (template — not contract text)

- [ ] Processing purposes
- [ ] Categories of personal/health data
- [ ] Documented instructions
- [ ] Confidentiality obligations
- [ ] Security measures
- [ ] Subprocessors + notification
- [ ] Breach handling / timelines
- [ ] Data subject request assistance
- [ ] Retention
- [ ] Return / deletion on termination
- [ ] Audit / evidence access
- [ ] Cross-border / location terms if applicable

Owner: `JOINT_CONTRACTUAL_CONTROL` · Legal counsel drafts binding text.
