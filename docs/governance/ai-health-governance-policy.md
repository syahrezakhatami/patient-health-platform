# AI health governance policy

**Date:** 2026-08-28
**Kind:** PROVIDER AI GOVERNANCE — design only
**Baseline:** `c55d259180c4864b56ea40e4c24833c9cd438d68`
**Hardening gate:** `docs/gates/provider-governance-hardening-gate.md`

Not legal advice. Not SaMD certification. **AI CLINICAL IMPLEMENTATION = NOT STARTED.**
No production clinical module may call an external LLM directly — future **centralized AI Gateway** only.

Authority labels: `AI_REGULATORY_GATE` · `VENDOR_SAFETY_DEFAULT` · `SITE_CLINICAL_POLICY` · `LEGAL_REQUIRED` (when applicable per assessment) · `DEFERRED`.

---

## 1. Platform principle — AI-006

**AI DOES NOT CREATE AUTHORITATIVE CLINICAL FACTS AUTOMATICALLY.**

Clinical recommendation path:

```
AI suggestion → clinician reviews → accept / modify / reject → clinician action creates authoritative record
```

Acceptance/rejection recorded separately from raw AI output where appropriate.
Classification: `VENDOR_SAFETY_DEFAULT` + `SITE_CLINICAL_POLICY` for enabling use cases.

---

## 2. AI regulatory applicability gate — AI-002 (frozen)

Classification depends on **intended use** and **actual function** — not product naming (`assistant`, `copilot`, `recommendation`, `summary`).

```
AI_REGULATORY_APPLICABILITY =
  NOT_ASSESSED        (default — production BLOCKED)
  NOT_APPLICABLE      (requires authorized review record)
  POTENTIALLY_APPLICABLE
  APPLICABLE
```

Only a properly authorized review can assign final production status. Engineering must **not** self-declare “not medical device.”

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AI-002 | Per-use-case regulatory classification | Permenkes 11/2025 where applicable; UU/sector rules | `AI_REGULATORY_GATE` | Separate assessment per use case before production | Regulatory reviewer + product | Each AI use case | Assessment template artifact | AI_REGULATORY_APPLICABILITY_TEST | NOT_ASSESSED | None | New intended use; model change |

**Permenkes 11/2025 scope (critical):**

- **REGULATION EXISTS** — risk-based health subsector business/product standards (JDIH Kemenkes: Berlaku).
- **Does NOT mean** every AI feature in the platform is automatically governed as medical-device AI.
- Where applicable to the **relevant regulated product classification**, additional obligations may apply — evidenced by classification memo, not engineering assumption.
- Voluntary alignment items (GMLP concepts, transparency, security readiness) may be adopted as `VENDOR_SAFETY_DEFAULT` without claiming they are universal statutory requirements for all EMR features.

**SE Menkominfo 9/2023 (`AI-001`):** Surat Edaran / ethics guidance — informs policy; **not** UU-equivalent normative force.

---

## 3. Use-case registry — AI-003 (required fields)

Every AI use case record:

| Field | Description |
|---|---|
| `use_case_id` | Stable identifier |
| `intended_use` | Plain-language purpose |
| `target_user` | Role category |
| `clinical_purpose` | Y/N/uncertain |
| `patient_population` | If clinical |
| `inputs` | Data categories |
| `outputs` | Type and authority level |
| `human_oversight` | Review model |
| `model/provider/version` | Pinned where supported |
| `privacy_classification` | PDP category |
| `regulatory_applicability` | NOT_ASSESSED / NOT_APPLICABLE / POTENTIALLY_APPLICABLE / APPLICABLE |
| `evaluation_version` | TEVV artifact ref |
| `activation_state` | DISABLED default |
| `owner` | Product/clinical owner |
| `kill_switch_scope` | Disable granularity |

---

## 4. Risk taxonomy

| Class | Default posture |
|---|---|
| `AI_ADMINISTRATIVE` | Allowed with governance |
| `AI_WORKFLOW_ASSIST` | Allowed with governance |
| `AI_DOCUMENTATION_ASSIST` | Human review before authoritative save |
| `AI_PATIENT_EDUCATION` | Non-authoritative; clear labeling |
| `AI_CLINICAL_INFORMATION_RETRIEVAL` | Source-grounded; human oversight |
| `AI_CLINICAL_DECISION_SUPPORT` | `AI_REGULATORY_GATE` + site approval |
| `AI_DIAGNOSTIC_SUPPORT` | `AI_REGULATORY_GATE` + heightened evidence |
| `AI_TREATMENT_RECOMMENDATION` | `AI_REGULATORY_GATE` + heightened evidence |
| `AI_AUTONOMOUS_CLINICAL_DECISION` | **PROHIBITED BY DEFAULT** (`AI-005`) |

---

## 5. Regulatory classification gate — AI-002

Before implementing/deploying AI with potential medical purpose, complete:

`docs/governance/ai-use-case-regulatory-and-clinical-assessment-template.md`

Ask: intended use? Information for diagnosis / screening / treatment / dosage / prediction / therapy selection? Possible software-based medical device / SaMD under applicable Indonesian rules (**including Permenkes 11/2025 where applicable to the relevant regulated product classification**)?

If **YES / POSSIBLE / UNCERTAIN** → **REGULATORY REVIEW REQUIRED** before production.

Readiness frameworks **if** SaMD path applies: ISO 14971, IEC 62304, GMLP — classified as `CERTIFICATION_READINESS`, not “certified.”

Voluntary AI MS: ISO/IEC 42001:2023, NIST AI RMF (GOVERN/MAP/MEASURE/MANAGE) — `VOLUNTARY_ALIGNMENT` / `REFERENCE_FRAMEWORK`.

Ethics: WHO AI-for-health principles; SE Menkominfo 9/2023 alignment — `REFERENCE_FRAMEWORK` / ethics input.

---

## 6. Transparency

Authorized users see: AI was used; model/provider family where appropriate; limitations; timestamp; draft/recommendation status; human confirmation required.
No hidden chain-of-thought exposure.

---

## 7. Data minimization & provider registry

AI Gateway sends minimum necessary context — not entire chart by default; no unnecessary identifiers.

External model registry: provider, model, region/processing, retention, training-on-customer-data policy, contractual controls, availability, cost, security review, approved/prohibited use cases.

---

## 8. Evaluation (TEVV) — AI-004

**Vendor activation requirement** for clinical AI (`VENDOR_SAFETY_DEFAULT`) — not claimed as universal statutory threshold.

No activation because “the model looks good.”

Evaluate (use-case-specific metrics; **no universal clinical pass thresholds invented here**):

task correctness · hallucination/error · unsafe recommendation · refusal · bias/subgroup · context omission · prompt injection · data leakage · adversarial input · version regression · latency · availability · fallback · clinician usability.

Each use case must define: clinically meaningful metrics · failure modes · acceptance criteria · review authority.

**Golden datasets:** provenance, de-id/synthetic status, clinical review, version, intended use, representativeness, access, retention. No casual real PHI in fixtures.

---

## 9. Change control

**Model/provider upgrade ≠ automatically safe.** Require: change request, release notes, re-evaluation, clinical impact, security/privacy, approval, rollback. No silent “latest” in clinical workflow. Pin version where supported.

**Prompts:** material system prompt changes = product changes (review, test, version, approve, release, monitor). No arbitrary production editing by normal users.

---

## 10. Incidents & kill switch

Categories: unsafe recommendation · wrong-patient context · data disclosure · prompt injection · outage · bias · clinical near miss · unexpected behavior.

Process: contain · disable feature · rollback · notify owner · site notify · regulatory assess · RCA · CAPA.

**Kill switch:** disable use case / provider / model / organization / all clinical AI — **without** disabling core EMR.
**Fallback:** EMR must work if AI unavailable, disabled, rate-limited, unsafe, or under investigation.

---

## 11. Audit & billing telemetry

AI audit metadata (avoid over-storing PHI): use_case_id, model/provider, actor, patient ref where allowed, purpose, timestamp, accepted/rejected/modified, latency/status.
Detailed prompts/responses: separate governed storage if required — not general audit dump.

Billing telemetry: tokens, model, provider, org, use case, cost, latency — **no** unnecessary clinical content.

---

## 12. Site activation — AI go-live gate

Site must approve clinical AI use locally (`SITE_CLINICAL_POLICY`). Vendor implementation alone is insufficient.

Future AI activation additionally requires:

- intended use reviewed
- regulatory applicability assessed (`AI-002`)
- TEVV passed (`AI-004`)
- model/version pinned or governed
- privacy review
- human oversight defined
- fallback defined
- kill switch tested
- incident owner assigned
- site acceptance

See fasyankes go-live template.

---

## 13. Autonomous clinical AI — AI-005

| control_id | title | classification | requirement | status |
|---|---|---|---|---|
| AI-005 | Autonomous clinical decision prohibited by default | `VENDOR_SAFETY_DEFAULT` + `AI_REGULATORY_GATE` | No autonomous diagnosis/prescription/treatment without explicit authorized exception path | Policy — NOT STARTED |

**Not** claimed as literal national statutory prohibition unless specific legal evidence supports it for the use case.
