# Provider clinical safety defaults

**Date:** 2026-08-28
**Kind:** VENDOR CLINICAL SAFETY DEFAULTS — design only
**Baseline:** `c55d259180c4864b56ea40e4c24833c9cd438d68`
**Hardening gate:** `docs/gates/provider-governance-hardening-gate.md`

Not legal advice. Not an Observation write implementation authorization.
Observation / Vital Signs write design remains **BLOCKED** until site/product/clinical human approvals exist.

Every control below is labeled: **vendor default**, **national profile**, or **site policy**.

---

## 1. Deny by default — CLIN-001

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLIN-001 | Deny-by-default clinical mutation | Provider baseline | `VENDOR_SAFETY_DEFAULT` | No permission → no clinical mutation | Provider | All clinical writes | PDP tests; config | CLINICAL_SAFETY_CONTROL_TEST | Design + Note Write | Waiver per OPS-001 — normally none | Auth model change |

| Rule | Classification |
|---|---|
| No permission → no clinical mutation | `VENDOR_SAFETY_DEFAULT` |
| Permissions (not role names) are authority | `VENDOR_SAFETY_DEFAULT` |
| Site assigns grants per SOP | `SITE_ADMINISTRATIVE_POLICY` / `SITE_CLINICAL_POLICY` |

Example: `clinical.observation.create` — not “NURSE automatically allowed.” No universal NURSE/DOCTOR/REGISTRAR role authority in backend.

---

## 2. Patient-context binding — CLIN-003

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLIN-003 | Expected-patient binding | Provider baseline | `VENDOR_SAFETY_DEFAULT` | Server-visible expected patient; encounter binding; same-person; 404 conceal | Provider | Chart write workflows | Note Write tests | CLINICAL_SAFETY_CONTROL_TEST | Implemented (Note Write) | None | MPI merge policy change |

| Rule | Classification |
|---|---|
| Selected patient required for Chart write workflows | `VENDOR_SAFETY_DEFAULT` |
| Server-visible `expected_patient_identity_id` precondition (not persisted authority) | `VENDOR_SAFETY_DEFAULT` |
| Persisted patient from encounter/domain binding | `VENDOR_SAFETY_DEFAULT` |
| Current-org visibility **before** canonical resolution | `VENDOR_SAFETY_DEFAULT` |
| Cluster-aware same-person; historical id not rewritten | `VENDOR_SAFETY_DEFAULT` (frozen MPI invariant) |
| Wrong patient → 404 conceal | `VENDOR_SAFETY_DEFAULT` |
| RETIRED / unusable → 409 | `VENDOR_SAFETY_DEFAULT` |

---

## 3. Encounter / facility — CLIN-004

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLIN-004 | Encounter status policy for Manual Vitals | Product contract + site policy | Mixed | See table below | Provider + site | Manual Vitals (when approved) | Design doc; site profile | SITE_GO_LIVE_EVIDENCE_TEST | Design — **BLOCKED** | Site may allow PLANNED/FINISHED per SOP | Encounter workflow change |

| Rule | Classification |
|---|---|
| Manual vital / Observation product workflow: **encounter required** | Product / interoperability contract — not falsely claimed as SATUSEHAT statute alone |
| `IN_PROGRESS` allow | `VENDOR_SAFETY_DEFAULT` |
| `CANCELLED` reject | `VENDOR_SAFETY_DEFAULT` |
| `ENTERED_IN_ERROR` reject | `VENDOR_SAFETY_DEFAULT` |
| `PLANNED` | **`SITE_CLINICAL_POLICY`** — not universal vendor allow |
| `FINISHED` | **`SITE_CLINICAL_POLICY`** / late-documentation policy — not universal vendor allow |
| Facility header omission never widens explicit facility scope | `VENDOR_SAFETY_DEFAULT` |
| Encounter/header mismatch → 409 | `VENDOR_SAFETY_DEFAULT` |
| Explicit wrong facility authority (absent header) → 403 | `VENDOR_SAFETY_DEFAULT` |

---

## 4. Time semantics — CLIN-005

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLIN-005 | Measurement and record timestamps | Provider baseline | Mixed | See table | Provider + site | Manual Vitals | Design doc | CLINICAL_SAFETY_CONTROL_TEST | Design | Site backdating policy | Time policy change |

| Rule | Classification |
|---|---|
| `effective_at` required for manually measured vitals | `VENDOR_SAFETY_DEFAULT` — **not** falsely SATUSEHAT-mandatory |
| `recorded_at` server-generated | `VENDOR_SAFETY_DEFAULT` / data integrity contract |
| Backdating allowed? | `SITE_CLINICAL_POLICY` |
| Future timestamp tolerance | `SITE_CLINICAL_POLICY` / technical config — **no invented 5-minute national rule** |
| Timezone-aware internal timestamps | `VENDOR_SAFETY_DEFAULT` |
| SATUSEHAT transport formatting | `NATIONAL_INTEROPERABILITY_PROFILE` (adapter) |

---

## 5. Immutable / auditable facts — CLIN-002

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLIN-002 | No silent clinical overwrite | Provider baseline | `VENDOR_SAFETY_DEFAULT` | Corrections are explicit; no silent mutation | Provider | All clinical mutations | Audit/provenance design | CLINICAL_SAFETY_CONTROL_TEST | Design + Note Write | Site defines correction workflow | Correction feature change |

| Rule | Classification |
|---|---|
| **NO SILENT CLINICAL OVERWRITE** | `VENDOR_SAFETY_DEFAULT` |
| Success audit + provenance for mutations | `VENDOR_SAFETY_DEFAULT` |
| Correction retains original; records actor, reason, timestamp, relationship, auth | `VENDOR_SAFETY_DEFAULT` (mechanism) |
| Correction window / who may correct | `SITE_CLINICAL_POLICY` |
| First Manual Vital MVP: CREATE-ONLY / FINAL; correction UI deferred | `VENDOR_SAFETY_DEFAULT` / `DEFERRED` for correction UI |

---

## 6. Terminology — TERM-001 / TERM-002

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| TERM-001 | SATUSEHAT national vitals profile | SATUSEHAT | `NATIONAL_INTEROPERABILITY_PROFILE` | Document LOINC/UCUM mappings | Provider | Vitals interop | Mapping table below | INTEROPERABILITY_CONFORMANCE_TEST | Evidence only | N/A | SATUSEHAT profile change |
| TERM-002 | Provider catalog + site clinical approval | Provider baseline | `VENDOR_SAFETY_DEFAULT` + `SITE_CLINICAL_POLICY` | Server allowlist; lifecycle to ACTIVE | Provider + site | Manual Vitals | Approved catalog; gate sign-off | SITE_GO_LIVE_EVIDENCE_TEST | **SITE_APPROVAL_PENDING** (0 APPROVED) | Site subset | New terminology version |

| Rule | Classification |
|---|---|
| Server-enforced allowlist for Manual Vitals | `VENDOR_SAFETY_DEFAULT` |
| National LOINC/UCUM mappings | `NATIONAL_INTEROPERABILITY_PROFILE` |
| Site clinical approval of catalog subset | `SITE_CLINICAL_POLICY` |
| No frontend-only terminology activation | `VENDOR_SAFETY_DEFAULT` |
| No automatic unit conversion / free-text units / silent aliases (unless approved) | `VENDOR_SAFETY_DEFAULT` |

**SATUSEHAT evidence (national profile — not site-approved):**

| Concept | LOINC | UCUM code | Display (interop) |
|---|---|---|---|
| Heart Rate | 8867-4 | `/min` | beats/min |
| Respiratory Rate | 9279-1 | `/min` | breaths/min |
| Body Temperature | 8310-5 | `Cel` | °C / Cel |
| Body Weight | 29463-7 | `kg` | kg |
| Body Height | 8302-2 | `cm` | cm |
| BP Systolic | 8480-6 | `mm[Hg]` | mmHg |
| BP Diastolic | 8462-4 | `mm[Hg]` | mmHg |

BP **write workflow** remains **DEFERRED** (atomicity). SpO2 remains **DEFERRED** pending use-case/site clinical approval.

Terminology lifecycle: CANDIDATE → evidence → national mapping → engineering review → provider catalog approval → site clinical approval (where required) → ACTIVE.

---

## 7. Values: technical vs clinical — CLIN-006

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLIN-006 | Technical vs clinical value validation | Provider baseline | Mixed | Technical rejects only unless site-approved clinical rule | Provider + site | Numeric vitals | Design doc | CLINICAL_SAFETY_CONTROL_TEST | Design | Site clinical thresholds if approved | New vital type |

| Allowed technical reject | Not allowed without approved clinical rule |
|---|---|
| Invalid Decimal, NaN, Infinity | “Abnormal → invalid” |
| Unsupported precision | Fever/hypertension/hypoxia thresholds as write blockers |
| Unsupported code/unit | Invented normal ranges |

Classification: technical rules = `VENDOR_SAFETY_DEFAULT`; clinical interpretation = `SITE_CLINICAL_POLICY` or `DEFERRED`.

---

## 8. Vital form default — CLIN-007

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CLIN-007 | One measurement per command | Provider baseline | `VENDOR_SAFETY_DEFAULT` | ONE MEASUREMENT · ONE COMMAND · ONE RESULT | Provider | Manual Vitals MVP | Design doc | CLINICAL_SAFETY_CONTROL_TEST | Design | None | MVP scope change |

| Rule | Classification |
|---|---|
| ONE MEASUREMENT · ONE COMMAND · ONE RESULT | `VENDOR_SAFETY_DEFAULT` |
| No Save-All multi-vital atomicity illusion | `VENDOR_SAFETY_DEFAULT` |

---

## 9. Privacy of clinical writes — PRIV-003

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| PRIV-003 | Minimize PHI in logs and client persistence | Provider baseline | `VENDOR_SAFETY_DEFAULT` | No routine value logging; memory-only unsaved PHI on clients | Provider | Clinical write UI | Logging policy | PRIVACY_RESPONSIBILITY_TEST | Design | N/A | Logging change |

No routine logging of measurement values; audit without full clinical payloads where possible; memory-only unsaved PHI on clients.

---

## 10. AI human oversight (future) — AI-006

| control_id | title | authority | classification | requirement | owner | applicability | evidence | test_method | status | exceptions | review_trigger |
|---|---|---|---|---|---|---|---|---|---|---|---|
| AI-006 | AI output is not authoritative clinical fact | Provider AI policy | `VENDOR_SAFETY_DEFAULT` + `AI_REGULATORY_GATE` | Suggestion → human review → authorized clinical command | Provider + site | Future clinical AI | AI policy; assessment | AI_REGULATORY_APPLICABILITY_TEST | NOT STARTED | N/A | New AI use case |

For future clinical AI: AI suggestion → human review → accept/modify/reject → explicit authorized clinical command.

Autonomous clinical AI: **PROHIBITED BY DEFAULT** — `VENDOR_SAFETY_DEFAULT` + `AI_REGULATORY_GATE` (not claimed as literal national statutory prohibition unless specific evidence exists).
