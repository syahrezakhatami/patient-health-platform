# Vital Signs terminology — human approval gate

**Date:** 2026-08-27
**Kind:** HUMAN APPROVAL TEMPLATE — ready for real signatures
**Baseline:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Evidence package:** `docs/architecture/vital-signs-terminology-candidate-catalog.md`

```
TERMINOLOGY HUMAN APPROVAL = PENDING
TERMINOLOGY CANDIDATE CATALOG = READY FOR HUMAN DECISION
OBSERVATION / VITAL SIGNS WRITE DESIGN = BLOCKED
VITAL CATALOG VERSION = UNASSIGNED / PENDING FIRST APPROVAL
```

Engineering / Cursor must **not** mark PRODUCT or CLINICAL fields APPROVED. No fictional reviewers.

---

## Ingestion pass result (2026-08-27)

**Pass:** HUMAN APPROVAL INGESTION / PRODUCT CATALOG FREEZE

**Evidence read:** this file only. Approval log empty. No external approval artifact found in-repo.

| Entry | PRODUCT MVP INCLUSION | CLINICAL SEMANTIC APPROVAL | UNIT EVIDENCE | FINAL (as recorded) |
|---|---|---|---|---|
| Heart rate `8867-4` | PENDING | PENDING | DECISION REQUIRED | CANDIDATE |
| Respiratory rate `9279-1` | PENDING | PENDING | DECISION REQUIRED | CANDIDATE |
| Body temperature `8310-5` | PENDING | PENDING | PASS | CANDIDATE |
| SpO₂ / `59408-5` | PENDING | PENDING | PASS | CANDIDATE |
| Body weight `29463-7` | PENDING | PENDING | PASS | CANDIDATE |
| Body height `8302-2` | PENDING | PENDING | PASS | CANDIDATE |
| Blood pressure | REJECTED FOR FIRST MVP (defer) | — | — | DEFERRED |
| Shared encounter / timing policies | PENDING | PENDING | — | PENDING |

**Fully APPROVED entries meeting all threshold fields:** **0**

**Outcome:** No product catalog version assigned. No approved-catalog freeze. Observation Vital Signs write design remains **BLOCKED**. Engineering did not invent approver names, dates, units, or APPROVED statuses.

To unblock: fill PRODUCT/CLINICAL fields with real names/dates, set exact unit codes where UNIT EVIDENCE is DECISION REQUIRED, then re-run ingestion.

---

## Approval threshold (per entry)

FINAL ENTRY STATUS = APPROVED only when:

| Field | Required |
|---|---|
| TERMINOLOGY EVIDENCE | PASS |
| UNIT EVIDENCE | PASS (exact unit code chosen) |
| PRODUCT MVP INCLUSION | APPROVED |
| CLINICAL SEMANTIC APPROVAL | APPROVED |
| ENGINEERING CONTRACT READY | YES |
| PRODUCT DECISION BY / DATE | real name + date |
| CLINICAL REVIEW BY / DATE | real name + date |

Partial approval allowed. Minimum unblock: **≥1** APPROVED useful measurement.

After APPROVED: freeze LOINC code, canonical unit code, product labels, actors, dates; bump product catalog version on any later change.

---

## Shared product policies (not LOINC facts)

| Policy | Proposal | Classification | PRODUCT DECISION BY | DATE | CLINICAL REVIEW BY | DATE | Status |
|---|---|---|---|---|---|---|---|
| Encounter required | YES | Product contract | PENDING | PENDING | PENDING | PENDING | PENDING |
| `IN_PROGRESS` allow | YES | `VENDOR_SAFETY_DEFAULT` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `PLANNED` allow | Site decides | `SITE_CLINICAL_POLICY` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `FINISHED` allow | Site / late-entry | `SITE_CLINICAL_POLICY` | PENDING | PENDING | PENDING | PENDING | PENDING |
| `CANCELLED` / `ENTERED_IN_ERROR` | Reject | `VENDOR_SAFETY_DEFAULT` | — | — | — | — | Provider default |
| `effective_at` required | YES | `VENDOR_SAFETY_DEFAULT` (not SATUSEHAT-mandatory claim) | PENDING | PENDING | PENDING | PENDING | PENDING |
| Backdating | Site SOP | `SITE_CLINICAL_POLICY` | PENDING | PENDING | PENDING | PENDING | PENDING |
| Future timestamp tolerance | Site/technical | `SITE_CLINICAL_POLICY` — no 5-minute national invention | PENDING | PENDING | PENDING | PENDING | PENDING |
| One canonical unit per vital; no conversion; no silent aliases | Proposed | `VENDOR_SAFETY_DEFAULT` | PENDING | PENDING | PENDING | PENDING | PENDING |
| Blood pressure deferred from first MVP | YES | Atomicity + safety | PENDING | PENDING | PENDING | PENDING | DEFERRED |
| SpO2 deferred pending use-case/site approval | YES | `SITE_CLINICAL_POLICY` / use-case | PENDING | PENDING | PENDING | PENDING | DEFERRED |
| SATUSEHAT LOINC/UCUM mappings | Evidence only | `NATIONAL_INTEROPERABILITY_PROFILE` | — | — | — | — | Not site approval |

---

## Entry: Heart rate (`8867-4`)

```
MEASUREMENT = Heart rate
CATALOG_KEY = vital.heart_rate
CODE SYSTEM = http://loinc.org
CODE = 8867-4
EXACT LOINC CONCEPT = Heart rate
VALUE TYPE = NUMERIC
CATEGORY = VITAL_SIGNS

LOINC EVIDENCE CHANNEL = official concept website (+ release context 2.83)
LOINC EVIDENCE VERSION = concept last-updated 2.81 (MIN); distribution 2.83 (2026-08-19)
FHIR TS = do not cite as 2.83 while TS reports 2.82

UNIT SYSTEM = http://unitsofmeasure.org
OFFICIAL EXAMPLE UCUM = {beats}/min ; {counts}/min
NON-UCUM DISPLAYS (not aliases) = /MIN ; bpm
CANDIDATE UNIT CODE = <HUMAN MUST CHOOSE — e.g. {beats}/min or other exact approved UCUM>
UNIT STATUS = DECISION REQUIRED
Do NOT auto-select /min

PRODUCT UI LABEL ID = Denyut jantung (draft)
PRODUCT UI LABEL EN = Heart rate (draft)
FRIENDLY UNIT DISPLAY = <optional; must not replace unit code>

TERMINOLOGY EVIDENCE = PASS
UNIT EVIDENCE = DECISION REQUIRED
PRODUCT MVP INCLUSION = PENDING
CLINICAL SEMANTIC APPROVAL = PENDING
ENGINEERING CONTRACT READY = NO until UNIT EVIDENCE = PASS and human approvals

PRODUCT DECISION BY = PENDING
PRODUCT DECISION DATE = PENDING
CLINICAL REVIEW BY = PENDING
CLINICAL REVIEW DATE = PENDING

FINAL ENTRY STATUS = CANDIDATE
```

---

## Entry: Respiratory rate (`9279-1`)

```
MEASUREMENT = Respiratory rate
CATALOG_KEY = vital.respiratory_rate
CODE SYSTEM = http://loinc.org
CODE = 9279-1
EXACT LOINC CONCEPT = Respiratory rate
VALUE TYPE = NUMERIC
CATEGORY = VITAL_SIGNS

LOINC EVIDENCE CHANNEL = official concept website
LOINC EVIDENCE VERSION = last-updated 2.81 (MIN); distribution 2.83

UNIT SYSTEM = http://unitsofmeasure.org
OFFICIAL EXAMPLE UCUM = {breaths}/min ; {counts}/min
CANDIDATE UNIT CODE = <HUMAN MUST CHOOSE>
UNIT STATUS = DECISION REQUIRED
Do NOT silently normalize to /min

PRODUCT UI LABEL ID = Laju pernapasan (draft)
PRODUCT UI LABEL EN = Respiratory rate (draft)

TERMINOLOGY EVIDENCE = PASS
UNIT EVIDENCE = DECISION REQUIRED
PRODUCT MVP INCLUSION = PENDING
CLINICAL SEMANTIC APPROVAL = PENDING
ENGINEERING CONTRACT READY = NO until UNIT EVIDENCE = PASS and human approvals

PRODUCT DECISION BY = PENDING
PRODUCT DECISION DATE = PENDING
CLINICAL REVIEW BY = PENDING
CLINICAL REVIEW DATE = PENDING

FINAL ENTRY STATUS = CANDIDATE
```

---

## Entry: Body temperature (`8310-5`)

```
MEASUREMENT = Body temperature
CATALOG_KEY = vital.body_temperature
CODE SYSTEM = http://loinc.org
CODE = 8310-5
EXACT LOINC CONCEPT = Body temperature
VALUE TYPE = NUMERIC

UNIT SYSTEM = http://unitsofmeasure.org
CANDIDATE UNIT CODE = Cel
UNIT EVIDENCE = PASS (LOINC Example UCUM Cel)

SEMANTIC LIMITATION = no site/method workflow in Observation schema

TERMINOLOGY EVIDENCE = PASS
UNIT EVIDENCE = PASS
PRODUCT MVP INCLUSION = PENDING
CLINICAL SEMANTIC APPROVAL = PENDING
ENGINEERING CONTRACT READY = YES after human approvals (unit already exact)

PRODUCT DECISION BY = PENDING
PRODUCT DECISION DATE = PENDING
CLINICAL REVIEW BY = PENDING
CLINICAL REVIEW DATE = PENDING

FINAL ENTRY STATUS = CANDIDATE
```

---

## Entry: Oxygen saturation — Pulse oximetry (`59408-5`)

```
MEASUREMENT = Oxygen saturation in Arterial blood by Pulse oximetry
CATALOG_KEY = vital.oxygen_saturation_pulse_ox
CODE SYSTEM = http://loinc.org
CODE = 59408-5
EXACT LOINC CONCEPT = Oxygen saturation in Arterial blood by Pulse oximetry
VALUE TYPE = NUMERIC

UNIT SYSTEM = http://unitsofmeasure.org
CANDIDATE UNIT CODE = %
UNIT EVIDENCE = PASS

Do NOT reduce authoritative concept to "SpO2" in evidence.
UI label SpO₂ only if product approves.
Confirm manual pulse-ox workflow matches this LOINC.
LIMITATION = no FiO2 / oxygen-delivery context in first MVP.

TERMINOLOGY EVIDENCE = PASS
UNIT EVIDENCE = PASS
PRODUCT MVP INCLUSION = PENDING
CLINICAL SEMANTIC APPROVAL = PENDING
ENGINEERING CONTRACT READY = NO until clinical confirms semantics + missing FiO2 OK

PRODUCT DECISION BY = PENDING
PRODUCT DECISION DATE = PENDING
CLINICAL REVIEW BY = PENDING
CLINICAL REVIEW DATE = PENDING

FINAL ENTRY STATUS = CANDIDATE
```

---

## Entry: Body weight (`29463-7`)

```
MEASUREMENT = Body weight
CATALOG_KEY = vital.body_weight
CODE SYSTEM = http://loinc.org
CODE = 29463-7
EXACT LOINC CONCEPT = Body weight
VALUE TYPE = NUMERIC

UNIT SYSTEM = http://unitsofmeasure.org
CANDIDATE UNIT CODE = kg
OFFICIAL EXAMPLE UCUM ALSO INCLUDES = [lb_av] (not MVP)
UNIT EVIDENCE = PASS
NO CONVERSION / NO BMI

TERMINOLOGY EVIDENCE = PASS
UNIT EVIDENCE = PASS
PRODUCT MVP INCLUSION = PENDING
CLINICAL SEMANTIC APPROVAL = PENDING
ENGINEERING CONTRACT READY = YES after human approvals

PRODUCT DECISION BY = PENDING
PRODUCT DECISION DATE = PENDING
CLINICAL REVIEW BY = PENDING
CLINICAL REVIEW DATE = PENDING

FINAL ENTRY STATUS = CANDIDATE
```

---

## Entry: Body height (`8302-2`)

```
MEASUREMENT = Body height
CATALOG_KEY = vital.body_height
CODE SYSTEM = http://loinc.org
CODE = 8302-2
EXACT LOINC CONCEPT = Body height
VALUE TYPE = NUMERIC

UNIT SYSTEM = http://unitsofmeasure.org
CANDIDATE UNIT CODE = cm
OFFICIAL EXAMPLE UCUM ALSO INCLUDES = m ; [in_us] (not MVP)
UNIT EVIDENCE = PASS
NO CONVERSION / NO BMI

TERMINOLOGY EVIDENCE = PASS
UNIT EVIDENCE = PASS
PRODUCT MVP INCLUSION = PENDING
CLINICAL SEMANTIC APPROVAL = PENDING
ENGINEERING CONTRACT READY = YES after human approvals

PRODUCT DECISION BY = PENDING
PRODUCT DECISION DATE = PENDING
CLINICAL REVIEW BY = PENDING
CLINICAL REVIEW DATE = PENDING

FINAL ENTRY STATUS = CANDIDATE
```

---

## Blood pressure

```
FINAL ENTRY STATUS = DEFERRED
PRODUCT MVP INCLUSION = REJECTED FOR FIRST MVP (defer)
REASON = separate Observation facts + SINGLE POST + one-measurement UI
```

---

## Approval log (humans only)

| Date | Entry | Role | Name | Decision | Chosen unit (if any) | Notes |
|---|---|---|---|---|---|---|
| | | | | | | |

---

## After first APPROVED entry

1. Set `VITAL CATALOG VERSION` explicitly in a successor gate.
2. Amend Observation Vital Signs design approval with exact approved rows.
3. Only then: `OBSERVATION / VITAL SIGNS WRITE DESIGN = APPROVED FOR IMPLEMENTATION` for that subset.
