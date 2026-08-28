# Vital Signs terminology — approved product catalog

**Date:** 2026-08-27 (clarified 2026-08-28 post-OGP)
**Kind:** PRODUCT CATALOG FREEZE RECORD
**Baseline:** `d449ffed6bd314edac3964f1c6c69bb51955a8db` (`organization-governance-profile-foundation-frozen`)
**Source gate:** `docs/gates/vital-signs-terminology-human-approval.md`

```
APPROVAL DIMENSION CLARIFICATION
  PROVIDER_SUPPORTED ≠ SITE_APPROVED ≠ ACTIVE_FOR_ORGANIZATION

VITAL CATALOG VERSION (proposed provider) = manual-vitals-mvp-v1
SITE-APPROVED ENTRY COUNT = 0
PROVIDER-SUPPORTED ENGINEERING SUBSET = defined in reconciliation gate (not site-approved)
MANUAL VITAL SIGNS ENGINEERING DESIGN = APPROVED FOR IMPLEMENTATION
SITE ACTIVATION = PENDING
```

**Filename note:** “approved” refers to the **product catalog freeze record** document type, not site clinical approval. **Zero** site-approved measurement rows exist.

## Ingestion result

Human approval ingestion was attempted on 2026-08-27.

**Zero** catalog entries satisfied the full APPROVED threshold (terminology PASS + unit PASS + product APPROVED with named decision maker/date + clinical APPROVED with named reviewer/date + engineering ready).

Therefore this document contains **no frozen approved measurement rows**.

Do not treat candidate catalog entries as approved. Do not implement Observation Manual Vital writes until ≥1 entry is fully approved and this document is updated with exact:

- product catalog version
- LOINC code + canonical unit code
- product labels
- approval actors and dates
- semantic limitations

Blood pressure remains deferred for the first MVP unless separately approved with atomicity design.

External terminology / profile versions (for future freeze, not product catalog version):

- LOINC distribution **2.83** (2026-08-19)
- LOINC FHIR TS may report **2.82** until updated
- UCUM via official Example UCUM Units / `http://unitsofmeasure.org`
- **SATUSEHAT** vital mappings = `NATIONAL_INTEROPERABILITY_PROFILE` evidence only (8867-4/`/min`, 9279-1/`/min`, 8310-5/`Cel`, 29463-7/`kg`, 8302-2/`cm`, BP 8480-6 & 8462-4/`mm[Hg]`) — **not** site clinical approval

See also: `docs/governance/` provider governance foundation (2026-08-28). BP write and SpO2 remain deferred for first Manual Vital activation.
