# Vital Signs terminology — candidate catalog (evidence-normalized)

**Date:** 2026-08-27
**Kind:** DESIGN / RESEARCH / HUMAN APPROVAL PACKAGE — not implementation
**Pass:** Candidate evidence normalization / human-review readiness
**Baseline HEAD:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Alembic:** `20260814_0019` (no `0020`)

```
TERMINOLOGY CANDIDATE CATALOG = READY FOR HUMAN DECISION
TERMINOLOGY HUMAN APPROVAL = PENDING
OBSERVATION / VITAL SIGNS WRITE DESIGN = BLOCKED
BLOCKED BY = VITAL SIGNS TERMINOLOGY HUMAN APPROVAL
VITAL CATALOG VERSION = UNASSIGNED / PENDING FIRST APPROVAL
```

This package does **not** approve terminology. Stronger evidence ≠ approval. Engineering must not self-approve.

Not a HIPAA / ISO 27001 / SOC 2 certification.

---

## 1. Why a catalog is required

Frozen Observation create accepts any Wave 2A `CodeableConcept` stub + free-string `unit`. Manual Vitals must not become generic Observation authoring.

Repo today: **no** terminology tables, registry, LOINC/UCUM seeds, or observation allowlist. Test fixture `8867-4` / `beats/min` is **not** authority (`beats/min` is not a LOINC Example UCUM Unit).

---

## 2. Source / version normalization (do not mix)

| Channel | What it is | Version for this package | Retrieved / verified |
|---|---|---|---|
| Official LOINC downloads | Full release zip | **LOINC 2.83** released **2026-08-19** ([loinc.org/downloads](https://loinc.org/downloads)) | 2026-08-27 |
| Official LOINC concept website | Per-code Long Common Name, Example UCUM Units, term “Last Updated” | Term pages may show concept last-updated (e.g. 2.81 MIN) while distribution is 2.83 | 2026-08-27 (web research; some CDN fetches blocked by Cloudflare) |
| LOINC FHIR Terminology Service (`fhir.loinc.org`) | Programmatic `$lookup` | Reports **LOINC 2.82** until its **2.83** content update is available | Do **not** claim FHIR TS evidence = 2.83 unless re-verified after that update |
| UCUM specification | `http://unitsofmeasure.org` | UCUM Organization **2.2** (2024); HL7 FHIR R5 ValueSet `ucum-vitals-common` expansion cites **UCUM 2.0.1** | 2026-08-27 |
| **SATUSEHAT** national interoperability mappings | National exchange profile evidence for selected vitals | Profile-dependent; treat as `NATIONAL_INTEROPERABILITY_PROFILE` | 2026-08-28 (governance pass) |

**Critical separation:**

| Evidence type | Meaning | Does it activate Manual Vitals? |
|---|---|---|
| `NATIONAL_INTEROPERABILITY_PROFILE` | SATUSEHAT / national mapping evidence | **No** — not site clinical approval |
| LOINC/UCUM authoritative concept evidence | Terminology fact | **No** — still needs site/product approval where required |
| `SITE_CLINICAL_POLICY` / product human approval | Facility/product accepts measurement in MVP | **Yes** — required for APPROVED catalog entry |

**Rule:** A candidate may cite multiple official channels. Keep **code evidence** and **unit evidence** on separate rows/fields. Do not collapse into one unverifiable “LOINC latest” citation. Do not treat SATUSEHAT mapping as automatic site approval.

### 2.1 SATUSEHAT national vital mapping evidence (not site-approved)

Classification: **`NATIONAL_INTEROPERABILITY_PROFILE`** only.

| Concept | LOINC | UCUM code | Interop display |
|---|---|---|---|
| Heart Rate | `8867-4` | `/min` | beats/min |
| Respiratory Rate | `9279-1` | `/min` | breaths/min |
| Body Temperature | `8310-5` | `Cel` | (Cel) |
| Body Weight | `29463-7` | `kg` | kg |
| Body Height | `8302-2` | `cm` | cm |
| BP Systolic | `8480-6` | `mm[Hg]` | mmHg |
| BP Diastolic | `8462-4` | `mm[Hg]` | mmHg |

**Blood pressure:** terminology evidence PASS for national mapping; **write workflow = DEFERRED** until paired/atomic semantics or explicit partial-entry approval.
**SpO2:** remains **DEFERRED PENDING USE-CASE / SITE CLINICAL APPROVAL** — not in first provider-default vital catalog activation.

Provider Manual Vital product catalog may later adopt SATUSEHAT unit codes (e.g. `/min`) **only** when site/product human approval freezes that exact canonical unit for the product catalog. Until then HR/RR product unit remains **DECISION REQUIRED** in the human-approval gate (annotated UCUM vs `/min`).

---

## 3. Concept separation

| Layer | Meaning | Must not be confused with |
|---|---|---|
| Observation code | What is measured (LOINC) | UI label |
| Unit code | Canonical stored/submitted UCUM string | Friendly unit display |
| Unit display | Human-facing unit wording | Unit code |
| Product label ID/EN | App wording | LOINC Long Common Name |

**UCUM annotations** such as `{beats}` and `{breaths}` carry semantic context. Do **not** strip them to a generic `/min` for engineering convenience. Prefer one canonical storage/input unit per approved vital. No automatic aliases (`bpm`, `beats/min`, `/min`) unless each exact string is explicitly governed. No silent UI→canonical conversion unless product contract approves it. Friendly UI label + exact submitted unit code is allowed **if** humans approve both.

---

## 4. Static catalog / versioning / 0020

Future enforcement: static application-owned immutable catalog (conceptual path `backend/app/modules/clinical/domain/vital_signs_catalog.py` — **do not create now**).

**VITAL CATALOG VERSION = UNASSIGNED / PENDING FIRST APPROVAL.** After first APPROVED entry, a successor pass assigns an explicit product-owned version; approved rows are immutable without a new reviewed version.

**Partial approval:** only APPROVED entries activate.

**MIGRATION 0020:** Observation idempotency only — **not** terminology storage. DESIGN REQUIRED / NOT CREATED. Do not repurpose `clinical_note_write_idempotency`.

---

## 5. Blood pressure

**BLOOD PRESSURE = DEFERRED.** No BP candidates for first unblock gate.

---

## 6. Normalized candidate summary table

| catalog_key | LOINC code | Exact LOINC concept | LOINC evidence | Candidate unit | Unit evidence | UI label ID (draft) | UI label EN (draft) | Semantic limitation | TERMINOLOGY EVIDENCE | UNIT EVIDENCE | PRODUCT | CLINICAL | FINAL |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `vital.heart_rate` | `8867-4` | Heart rate | Official concept site; LOINC 2.83 release context; term last-updated 2.81 (MIN) | **DECISION REQUIRED** (see §7.1) | LOINC Example UCUM `{beats}/min`, `{counts}/min`; also shows non-UCUM `/MIN`, `bpm` | Denyut jantung | Heart rate | Heart rate ≠ pulse casually | **PASS** | **DECISION REQUIRED** | PENDING | PENDING | **CANDIDATE** |
| `vital.respiratory_rate` | `9279-1` | Respiratory rate | Official concept site; LOINC 2.83; term last-updated 2.81 (MIN) | **DECISION REQUIRED** (see §7.2) | LOINC Example UCUM `{breaths}/min`, `{counts}/min` | Laju pernapasan | Respiratory rate | Component = Breaths | **PASS** | **DECISION REQUIRED** | PENDING | PENDING | **CANDIDATE** |
| `vital.body_temperature` | `8310-5` | Body temperature | Official concept site; LOINC 2.83 | `Cel` | LOINC Example UCUM **Cel** | Suhu tubuh | Body temperature | No site/method in Observation schema | **PASS** | **PASS** | PENDING | PENDING | **CANDIDATE** |
| `vital.oxygen_saturation_pulse_ox` | `59408-5` | Oxygen saturation in Arterial blood by Pulse oximetry | Official concept site; LOINC 2.83; term last-updated 2.73 (MIN) | `%` | LOINC / UCUM `%` | Saturasi oksigen (SpO₂) *if UI approved* | Oxygen saturation (pulse oximetry) | Exact concept ≠ shorthand “SpO2”; no FiO₂ / O₂-delivery workflow | **PASS** | **PASS** | PENDING | PENDING | **CANDIDATE** |
| `vital.body_weight` | `29463-7` | Body weight | Official concept site; LOINC 2.83 | `kg` | LOINC Example UCUM `kg`, `[lb_av]` — MVP candidate **kg only** | Berat badan | Body weight | No BMI; no lb conversion | **PASS** | **PASS** | PENDING | PENDING | **CANDIDATE** |
| `vital.body_height` | `8302-2` | Body height | Official concept site; LOINC 2.83; term last-updated 2.73 (MIN) | `cm` | LOINC Example UCUM `cm`, `m`, `[in_us]` — MVP candidate **cm only** | Tinggi badan | Body height | No BMI; no inch/m conversion | **PASS** | **PASS** | PENDING | PENDING | **CANDIDATE** |

All `code_system = http://loinc.org`. All `unit_system = http://unitsofmeasure.org` when a UCUM unit is chosen. All `value_type = NUMERIC`. All `observation_category = VITAL_SIGNS`.

**Numeric storage:** `Numeric(14,4)` / Decimal sufficient for all six. UI decimal places = PRODUCT DECISION (not forced to 4). No normal ranges / CDS.

---

## 7. Per-candidate evidence detail

### 7.1 Heart rate — `8867-4`

| Field | Value |
|---|---|
| SOURCE CHANNEL (code) | Official LOINC concept website |
| SOURCE VERSION (code) | Concept last updated **2.81 (MIN)**; release context **LOINC 2.83** (2026-08-19) |
| FHIR TS | Do **not** cite as 2.83 until TS updated from **2.82** |
| Exact concept | **Heart rate** |
| Example UCUM Units (official) | `{beats}/min` ; `{counts}/min` |
| Also displayed (non-UCUM / Regenstrief) | `/MIN` ; `bpm` — **not** interchangeable aliases for storage |
| Candidate unit code | **UNIT STATUS = DECISION REQUIRED** |
| Human must choose | Prefer `{beats}/min` **or** another **explicitly approved** exact UCUM representation. Do **not** auto-approve generic `/min` merely because it is a rate. |
| TERMINOLOGY EVIDENCE | **PASS** |
| UNIT EVIDENCE | **DECISION REQUIRED** |
| PRODUCT / CLINICAL / FINAL | PENDING / PENDING / **CANDIDATE** |

### 7.2 Respiratory rate — `9279-1`

| Field | Value |
|---|---|
| SOURCE CHANNEL (code) | Official LOINC concept website |
| SOURCE VERSION (code) | Last updated **2.81 (MIN)**; release context **2.83** |
| Exact concept | **Respiratory rate** (FSN component Breaths) |
| Example UCUM Units | `{breaths}/min` ; `{counts}/min` |
| Candidate unit code | **UNIT STATUS = DECISION REQUIRED** — do **not** silently normalize to `/min` |
| TERMINOLOGY EVIDENCE | **PASS** |
| UNIT EVIDENCE | **DECISION REQUIRED** |
| PRODUCT / CLINICAL / FINAL | PENDING / PENDING / **CANDIDATE** |

### 7.3 Body temperature — `8310-5`

| Field | Value |
|---|---|
| Exact concept | **Body temperature** |
| Candidate unit | `Cel` (LOINC Example UCUM Unit) |
| TERMINOLOGY EVIDENCE | **PASS** |
| UNIT EVIDENCE | **PASS** |
| Semantic limitation | No designed site/method workflow (oral/axillary/tympanic etc.). Do not invent fields. Clinical must decide if generic Body temperature is enough for MVP. |
| FINAL | **CANDIDATE** |

### 7.4 Oxygen saturation by Pulse oximetry — `59408-5`

| Field | Value |
|---|---|
| Exact concept | **Oxygen saturation in Arterial blood by Pulse oximetry** |
| Candidate unit | `%` |
| TERMINOLOGY EVIDENCE | **PASS** |
| UNIT EVIDENCE | **PASS** |
| Semantic limitation | Evidence table must retain full concept — not collapse to “SpO2”. UI may show SpO₂ only if product approves. Human must confirm manual pulse-ox workflow matches this LOINC. No FiO₂ / oxygen-delivery context in first MVP. Prefer over methodless `2708-6` for pulse-ox intent. |
| ENGINEERING CONTRACT READY | **NO** until clinical confirms code + missing FiO₂ context |
| FINAL | **CANDIDATE** |

### 7.5 Body weight — `29463-7`

| Field | Value |
|---|---|
| Exact concept | **Body weight** |
| Candidate unit | `kg` (ONE unit; Example UCUM also lists `[lb_av]` — not in MVP) |
| TERMINOLOGY / UNIT | **PASS** / **PASS** |
| FINAL | **CANDIDATE** |

### 7.6 Body height — `8302-2`

| Field | Value |
|---|---|
| Exact concept | **Body height** |
| Candidate unit | `cm` (ONE unit; Example UCUM also `m`, `[in_us]` — not in MVP) |
| TERMINOLOGY / UNIT | **PASS** / **PASS** |
| FINAL | **CANDIDATE** |

---

## 8. Terminology fact vs product decision

| Fact | Decision (human) |
|---|---|
| LOINC lists Example UCUM `{beats}/min` and `{counts}/min` for 8867-4 | Which exact unit string is stored/submitted? |
| Generic `/min` appears in FHIR vitals-common | Accept `/min` for HR/RR or reject in favor of annotated UCUM? |
| 59408-5 is pulse-oximetry oxygen saturation | Match intended Chart workflow? Include or defer? |
| 8310-5 has no site/method in our schema | Accept limitation? |
| PLANNED/FINISHED encounter documentable (Observation) | Product/clinical policy for Manual Vitals? |

---

## 9. Implementation unblock condition

≥1 measurement with:

- TERMINOLOGY EVIDENCE = PASS
- UNIT EVIDENCE = PASS
- PRODUCT MVP INCLUSION = APPROVED
- CLINICAL SEMANTIC APPROVAL = APPROVED
- ENGINEERING CONTRACT READY = YES
- FINAL ENTRY STATUS = APPROVED

Plus Observation safety contracts remain implementation-exact. BP not required. Partial catalog OK.

After approval: record LOINC code, canonical unit, labels, approvers, dates, and assign first **VITAL CATALOG VERSION**. No silent mutation of frozen entries.

---

## 10. Non-terminology contracts preserved

Patient precondition / same-person / facility matrix / encounter required / create-only FINAL / single measurement / idempotency replay safety — unchanged; see Observation Vital Signs design. Encounter PLANNED/FINISHED and timing policies remain **PENDING** human product/clinical sign-off.
