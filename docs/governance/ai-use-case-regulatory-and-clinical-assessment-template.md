# AI use-case regulatory and clinical assessment template

**Date:** 2026-08-28
**Kind:** ASSESSMENT TEMPLATE — default NOT ASSESSED
**Baseline:** `c55d259180c4864b56ea40e4c24833c9cd438d68`
**Hardening gate:** `docs/gates/provider-governance-hardening-gate.md`

Not legal advice. Not automatic approval. Complete **before** production clinical AI activation.

```
AI_REGULATORY_APPLICABILITY = NOT_ASSESSED   (default)
CLINICAL ACTIVATION = BLOCKED
ASSESSMENT STATUS = NOT ASSESSED
PRODUCTION ACTIVATION = PROHIBITED UNTIL APPROVED
```

Gate type: **`AI_ACTIVATION_GATE`** — not provider-foundation P1.

---

## A. Identification

| Field | Value |
|---|---|
| `use_case_id` | PENDING |
| Title | PENDING |
| Owner | PENDING |
| Request date | PENDING |
| Target release | PENDING |

---

## B. Intended use

| Field | Value |
|---|---|
| Intended use (plain language) | PENDING |
| Target users | PENDING |
| Target patient / population | PENDING / N/A |
| Care setting (hospital / clinic / Puskesmas / other) | PENDING |
| Risk class (taxonomy) | PENDING |
| Human oversight model | PENDING |
| Known limitations | PENDING |
| Fallback if AI unavailable | PENDING |
| Kill-switch scope | PENDING |
| Incident owner | PENDING |

---

## C. Data

| Field | Value |
|---|---|
| Input data categories | PENDING |
| Identifiers included? | PENDING |
| Minimum necessary justification | PENDING |
| Output type | PENDING |
| Privacy classification | PENDING |
| Training-on-customer-data risk | PENDING |

---

## D. Model / provider

| Field | Value |
|---|---|
| Provider | PENDING |
| Model | PENDING |
| Pinned version | PENDING |
| Region / processing location | PENDING |
| Retention policy | PENDING |
| Contractual controls reviewed | PENDING |

---

## E. Regulatory applicability (critical) — AI-002

| Question | Answer |
|---|---|
| Does software provide information for diagnosis? | YES / NO / UNCERTAIN |
| Screening? | YES / NO / UNCERTAIN |
| Treatment / therapy selection? | YES / NO / UNCERTAIN |
| Dosage? | YES / NO / UNCERTAIN |
| Clinical prediction? | YES / NO / UNCERTAIN |
| Possible software-based medical device / SaMD under applicable Indonesian rules (**incl. Permenkes 11/2025 where applicable to the relevant regulated product classification**)? | YES / POSSIBLE / UNCERTAIN / NO |
| **`AI_REGULATORY_APPLICABILITY`** | **NOT_ASSESSED** (default) / NOT_APPLICABLE / POTENTIALLY_APPLICABLE / APPLICABLE |
| If YES / POSSIBLE / UNCERTAIN | **REGULATORY REVIEW REQUIRED** before production |
| Regulatory reviewer | PENDING |
| Regulatory review date | PENDING |
| Classification decision | PENDING |
| `LEGAL_REVIEW` | NOT_REQUIRED / PENDING / COMPLETE / ESCALATION_REQUIRED |

Engineering must **not** self-declare “not medical device.”

**Permenkes 11/2025 note:** regulation existence ≠ automatic SaMD classification for this use case. Document feature-specific evidence or mark POTENTIALLY_APPLICABLE / APPLICABLE only after authorized review.

---

## F. Clinical / site approval

| Field | Value |
|---|---|
| Clinical impact summary | PENDING |
| SITE clinical approval | PENDING |
| Clinical reviewer name | PENDING |
| Clinical review date | PENDING |
| Product owner name | PENDING |
| Product decision date | PENDING |

---

## G. Evaluation evidence (TEVV) — AI-004

| Area | Result / link | Date | Acceptance criteria (use-case-specific) |
|---|---|---|---|
| Task correctness | PENDING | | PENDING |
| Hallucination / error | PENDING | | PENDING |
| Unsafe recommendation | PENDING | | PENDING |
| Refusal behavior | PENDING | | PENDING |
| Bias / subgroup | PENDING / N/A | | PENDING |
| Context omission | PENDING | | PENDING |
| Prompt injection | PENDING | | PENDING |
| Data leakage | PENDING | | PENDING |
| Adversarial input | PENDING | | PENDING |
| Version regression | PENDING | | PENDING |
| Latency / availability / fallback | PENDING | | PENDING |
| Clinician usability | PENDING | | PENDING |
| Golden dataset version | PENDING | | PENDING |

No universal clinical pass threshold invented in this template. Each use case defines clinically meaningful metrics, failure modes, and acceptance criteria.

---

## H. AI go-live gate checklist

- [ ] Intended use reviewed and documented
- [ ] `AI_REGULATORY_APPLICABILITY` assigned by authorized reviewer
- [ ] TEVV passed with use-case-specific acceptance criteria
- [ ] Model/version pinned or governed
- [ ] Privacy review complete
- [ ] Human oversight model defined and tested
- [ ] Fallback verified (core EMR works without AI)
- [ ] Kill switch tested
- [ ] Incident owner assigned
- [ ] Site clinical acceptance recorded

---

## I. Decision

| Field | Value |
|---|---|
| ASSESSMENT STATUS | NOT ASSESSED / IN REVIEW / APPROVED / REJECTED / DEFERRED |
| `AI_REGULATORY_APPLICABILITY` | NOT_ASSESSED (default) |
| Activation status | **DISABLED** by default |
| Rollback plan | PENDING |
| Incident owner | PENDING |
| Next review date | PENDING |
| Exceptions / waivers | NONE or documented per OPS-001 |
