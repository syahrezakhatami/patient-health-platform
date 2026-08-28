# Observation / Manual Vital Signs — provider vs site gate reconciliation

**Date:** 2026-08-28  
**Kind:** GOVERNANCE / DESIGN RECONCILIATION — docs only  
**Pass:** Post-OGP provider-implementation vs site-activation gate separation  
**Baseline HEAD:** `d449ffed6bd314edac3964f1c6c69bb51955a8db`  
**Baseline tag:** `organization-governance-profile-foundation-frozen`  
**Parent OGP:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)  
**Software capability parent:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)  
**Alembic:** `current == heads == 20260814_0020` (exactly one head; Observation migration **UNASSIGNED**)

This pass reconciles Observation / Manual Vital Signs governance after the frozen Organization Governance Profile (OGP) foundation. It does **not** authorize implementation, migration creation, provider registration, site activation, or any production code change.

---

## Verdict

```
OBSERVATION / MANUAL VITAL SIGNS
PROVIDER-vs-SITE GATE RECONCILIATION = COMPLETE

MANUAL VITAL SIGNS ENGINEERING DESIGN =
APPROVED FOR IMPLEMENTATION

PROVIDER PRODUCTION REGISTRATION =
PENDING PROVIDER RELEASE / CLINICAL SAFETY GATE

SITE ACTIVATION =
PENDING SITE CLINICAL / TERMINOLOGY APPROVAL
```

**OGP SECURITY ASSURANCE (unchanged):** PASS WITH NO ACTIVE P0 / P1 on frozen OGP foundation.

---

## 1. Rationale — governance model changed

Before OGP freeze, Observation / Manual Vital Signs design was blocked by a conflated assumption:

> site approval must exist before vendor engineering can implement the capability.

The frozen OGP foundation now provides authoritative infrastructure for:

- provider capability state (`AVAILABLE` / `SUSPENDED` / `RETIRED`)
- `governance_required` semantics
- organization site feature activation
- deployment gates (`CONTROLLER_PROCESSOR_ASSESSMENT`, `DPA`)
- organization governance profile + approval evidence
- fail-closed resolver + permission separation

Therefore three **independent** gates must be tracked:

| Gate | Question |
|---|---|
| **A. Provider engineering implementation** | May engineering implement and test the feature? |
| **B. Provider capability release / registration** | May the provider freeze/publish/register this as a supported production capability? |
| **C. Fasyankes site activation** | May Organization X actually activate and use the feature? |

**Frozen principle:**

```
SITE APPROVAL != PROVIDER SOFTWARE IMPLEMENTATION APPROVAL
```

Site approval governs activation/use by that organization. It does **not** need to prevent a software vendor from developing an inactive, fail-closed capability.

---

## 2. Gate A — provider engineering implementation

**Status:** **APPROVED FOR IMPLEMENTATION**

Engineering may proceed when all technical contracts in `docs/architecture/observation-vital-signs-write-workflow-design.md` are exact.

### May rely on

- authoritative national interoperability evidence (SATUSEHAT profile subset)
- provider product scope
- approved technical safety contract (patient, encounter, facility, numeric, idempotency)
- OGP fail-closed integration design

### Does NOT require

- a specific customer hospital approval
- a specific clinic / Puskesmas approval
- provider production registration
- site terminology approval rows

### Engineering policy (explicit)

Engineering implementation **MAY proceed** while provider clinical safety review is **PENDING**, **only if**:

1. feature remains **non-registered / non-available** in production provider registry
2. OGP fail-closed path is implemented (`NOT_REGISTERED` → deny)
3. no site can activate the feature
4. no product claims clinical approval
5. final capability freeze / production registration has an explicit provider clinical-review gate

**Recommended decision:** **YES**.

---

## 3. Gate B — provider capability release / registration

**Status:** **PENDING PROVIDER RELEASE / CLINICAL SAFETY GATE**

Separate question: may the provider register `manual_vital_signs_write` as a supported production capability?

### Requires (when pursued)

- provider clinical-safety review (qualified reviewer — **not invented in this pass**)
- terminology review completion for provider-supported subset
- security hardening + adversarial tests
- clinical semantic limitations documented
- regulatory applicability assessment where applicable
- provider release acceptance

```
PROVIDER CLINICAL SAFETY REVIEW = PENDING
```

No qualified clinical reviewer name, date, or sign-off is recorded in this repository.

### Release implication

Manual Vitals must **NOT** be finalized as production-supported / provider `AVAILABLE` while required provider-side clinical review remains incomplete.

**Provider capability production registry remains EMPTY.** No `manual_vital_signs_write` row is registered in this pass.

---

## 4. Gate C — fasyankes site activation

**Status:** **PENDING SITE CLINICAL / TERMINOLOGY APPROVAL**

Separate question: may Organization X activate Manual Vital Signs?

For `governance_required = true` clinical capability, site activation requires:

- site clinical approval (via OGP approval evidence — server-resolved, not client claims)
- site terminology approval for the provider vital catalog version + measurement subset
- site workflow policy (encounter states, backdating, future-time tolerance)
- required deployment gates (as declared on capability registration)
- entitlement
- actor permission (`clinical.observation.create`)
- provider capability availability

```
SITE-APPROVED TERMINOLOGY ENTRIES = 0
SITE FEATURE ACTIVE = none
```

No site approval means **no organization may activate/use Manual Vitals**, even after code exists or provider registers the capability.

Site approval may occur after vendor capability publication, during onboarding, or when an organization chooses to enable the feature.

---

## 5. National interoperability evidence

Classification: **`NATIONAL_INTEROPERABILITY_PROFILE`** — **not** `SITE_CLINICAL_APPROVED`.

| Concept | LOINC | UCUM code | Display |
|---|---|---|---|
| Heart Rate | `8867-4` | `/min` | beats/min |
| Respiratory Rate | `9279-1` | `/min` | breaths/min |
| Body Temperature | `8310-5` | `Cel` | (Cel) |
| Body Weight | `29463-7` | `kg` | kg |
| Body Height | `8302-2` | `cm` | cm |
| BP Systolic | `8480-6` | `mm[Hg]` | mmHg |
| BP Diastolic | `8462-4` | `mm[Hg]` | mmHg |

SATUSEHAT mapping evidence does **not** equal site clinical approval.

---

## 6. Provider engineering subset (first bounded target)

**Status:** approved as engineering implementation target (not site-approved for all organizations).

| Measurement | LOINC | UCUM | Notes |
|---|---|---|---|
| Heart Rate | `8867-4` | `/min` | SATUSEHAT national profile unit |
| Respiratory Rate | `9279-1` | `/min` | SATUSEHAT national profile unit |
| Body Temperature | `8310-5` | `Cel` | no measurement site/method in MVP |
| Body Weight | `29463-7` | `kg` | |
| Body Height | `8302-2` | `cm` | |

### Temperature limitation (preserved)

Generic Body Temperature (`8310-5`, `Cel`). MVP does **not** capture measurement site or method. UI must **not** imply oral / axillary / tympanic / rectal when not captured.

### Deferred from first implementation

| Item | Status | Reason |
|---|---|---|
| **Blood Pressure** | **DEFERRED WORKFLOW** | Terminology evidence PASS; paired/atomic measurement semantics require separate design |
| **SpO₂** | **DEFERRED** | pending explicit provider/site semantic review; not included merely because a LOINC candidate exists |

---

## 7. Terminology approval dimensions

Do **not** use one `APPROVED` flag for all stages.

| Stage | Meaning |
|---|---|
| **CANDIDATE** | research / evidence package entry |
| **PROVIDER_SUPPORTED** | software knows how to safely represent/validate code+unit contract |
| **SITE_APPROVED** | organization clinically approves use for that site |
| **ACTIVE_FOR_ORGANIZATION** | runtime site feature activation + entitlement + permission satisfied |

### Provider catalog semantics

- **PROVIDER_SUPPORTED_TERMINOLOGY:** provider product catalog entry — safe code/unit contract for software validation
- **SITE_APPROVED_TERMINOLOGY:** organization accepts that catalog version + measurement subset for clinical use

A provider-supported entry does **not** mean every organization clinically approves use.

### Site cannot invent code

Site may approve a **provider-supported** terminology entry. Site may **not** introduce arbitrary runtime LOINC/UCUM pairs. New code/unit pairs must first pass provider terminology governance.

### Preferred bounded approval model (first capability)

Site approval binds to:

- feature ID: `manual_vital_signs_write`
- provider vital catalog version (e.g. `manual-vitals-mvp-v1`)
- approved measurement subset

Rather than introducing an unrestricted terminology administration engine in the first pass.

OGP foundation deferred generic terminology enforcement; Manual Vitals follow-up should use **feature-specific approval evidence** encoding catalog-version acceptance unless a broader engine is separately approved.

---

## 8. Future feature ID and OGP integration

| Item | Value |
|---|---|
| **Feature ID** | `manual_vital_signs_write` |
| **governance_required** | `true` (when production-registered) |
| **Production registration** | **NOT registered** in this pass |

Unlike Clinical Note (frozen without OGP integration), Manual Vitals must be designed from inception as **OGP-integrated**.

### Runtime resolution order (future integrated path)

Before mutation, resolve `manual_vital_signs_write`:

1. provider row absent → **deny** (`NOT_REGISTERED` / feature unavailable)
2. provider `SUSPENDED` / `RETIRED` → **deny** (`DENIED_PROVIDER`)
3. site activation missing → **deny**
4. deployment gates unsatisfied → **deny**
5. entitlement → permission → clinical safety validation

### Missing provider row during development

Before production registration, Manual Vitals code path treats `NOT_REGISTERED` as feature unavailable / deny. Allows dark/inactive implementation without exposing the capability.

### No global registry effect

Clinical Note and other non-integrated frozen capabilities are **unaffected** by absence/presence of Manual Vitals provider capability row.

### Site approval is not a request field

No `site_approved=true` client claim. Server resolves authoritative OGP governance records.

---

## 9. Observation domain (unchanged)

- Vitals remain **Observation** domain (`category = VITAL_SIGNS`)
- **No** `vital_signs` table, VitalSign domain, `/api/v1/vitals`, or FHIR API
- **No** generic Observation creation UI through Healthcare Web
- Manual Vitals = constrained write workflow over existing `POST /api/v1/clinical/observations`
- **Encounter required**; persisted patient identity from encounter binding
- `expected_patient_identity_id` = precondition only

---

## 10. Encounter policy

| Status | Manual Vital create | Classification |
|---|---|---|
| `IN_PROGRESS` | ALLOW (provider-safe default when otherwise activated) | `VENDOR_SAFETY_DEFAULT` |
| `CANCELLED` | REJECT | `VENDOR_SAFETY_DEFAULT` |
| `ENTERED_IN_ERROR` | REJECT | `VENDOR_SAFETY_DEFAULT` |
| `PLANNED` | deny unless site explicitly allows | `SITE_CLINICAL_POLICY` |
| `FINISHED` | deny unless site explicitly allows (late-documentation policy) | `SITE_CLINICAL_POLICY` |

Default missing site policy: **fail closed** for optional states.

---

## 11. Time, numeric, unit, command model

| Contract | Value |
|---|---|
| `effective_at` | required clinical measurement time (client) |
| `recorded_at` | server authoritative |
| Backdating / future skew | `SITE_CLINICAL_POLICY` — no invented universal tolerance |
| Numeric storage | `Numeric(14,4)` / Decimal; reject NaN/Infinity; no silent rounding beyond contract |
| Clinical range blocking | **NO** — abnormality is not rejection |
| Unit policy | one canonical code/unit pair per vital; no conversion; no free-text unit |
| Command model | ONE MEASUREMENT / ONE COMMAND / ONE RESULT |
| Create status | FINAL only; create-only MVP |
| Correction UI | deferred; no silent overwrite |

---

## 12. Patient / facility / permission / entitlement

- Note-like patient protection: current-org visibility, cluster-aware same-person, wrong-patient concealment, RETIRED rejected, encounter-derived binding
- Note-like facility authority; site governance cannot disable provider hard facility checks
- **Permission:** `clinical.observation.create` — OGP activation does not grant it
- **Entitlement:** separate from site approval and permission; subscription cannot auto-activate Manual Vitals

---

## 13. Idempotency and migration sequencing

| Item | Value |
|---|---|
| Idempotency table | `clinical_observation_write_idempotency` (feature-specific) |
| Reuse forbidden | `clinical_note_write_idempotency`, `governance_admin_idempotency` |
| Current Alembic head | `20260814_0020` (OGP foundation) |
| Planned next revision | `20260814_0021` (parent `20260814_0020`) — **NOT created in this pass** |
| Migration UNASSIGNED until | implementation pass assigns revision |

### Planned 0021 scope (when assigned)

Potentially:

- Observation-specific write idempotency table + hardening
- bounded provider-vital catalog DB support **only if** schema actually required
- site catalog/subset approval support **only if** OGP schema needs capability-specific extension

**Do NOT create:** `vital_signs` table, generic terminology database, BP tables, AI tables, facility override tables.

---

## 14. Provider catalog version

```
PROVIDER VITAL CATALOG VERSION (proposed) = manual-vitals-mvp-v1
```

This is a **provider product catalog version**, not LOINC version and not SATUSEHAT version. Formal assignment occurs when provider-supported subset is defined through provider release gate.

External terminology evidence recorded separately (LOINC 2.83 distribution context, SATUSEHAT national profile).

---

## 15. Human approval document preservation

Existing `docs/gates/vital-signs-terminology-human-approval.md` entries remain **PENDING** / **CANDIDATE**. No names, dates, or clinical sign-off were invented.

Clarification: entries previously read as blocking **all** engineering now map primarily to:

- **SITE / CLINICAL ACTIVATION APPROVAL** (Gate C)
- **PROVIDER RELEASE REVIEW** where product/clinical fields apply (Gate B)

HR/RR unit fields remain **DECISION REQUIRED** in the human-approval gate history; provider engineering adopts SATUSEHAT `/min` as national-profile-aligned provisional contract pending provider clinical review at release gate.

---

## 16. Approved catalog document note

`docs/architecture/vital-signs-terminology-approved-catalog.md` filename uses “approved” in the product-catalog-freeze sense. **APPROVED ENTRY COUNT = 0.** Document clarifies **approval dimension** — provider-supported vs site-approved — to avoid implying site clinical approval where none exists.

---

## 17. CSRF / CORS / rate limiting

| Item | Record |
|---|---|
| Auth model | bearer/token audience authentication |
| CORS | existing application CORS behavior |
| Cookie auth | not ambient for governance/clinical API paths |
| Governance rate limiting | **DEFERRED HARDENING / ABUSE CONTROL** (P3) — not required by existing frozen security contract for this reconciliation |

---

## 18. Findings

| Severity | Item |
|---|---|
| **P0** | none |
| **P1** | none — site activation pending is **not** a provider software P1 |
| **P2** | inherited DENIED-audit rollback (unchanged) |
| **P3** | approval withdrawal API deferred; governance rate-limiting deferred; facility overrides deferred; Redis cache deferred; governance admin UI deferred; AI runtime deferred; correction/amend UI deferred; BP workflow deferred; SpO2 deferred |

### Gate-classified pending items (not P0/P1)

| Gate | Status |
|---|---|
| `PROVIDER_RELEASE_GATE` | PENDING — provider clinical safety review |
| `SITE_ACTIVATION_GATE` | PENDING — 0 site-approved vital entries |

---

## 19. Explicit non-actions (this pass)

- No backend / frontend / migration / OpenAPI / permission changes
- No `manual_vital_signs_write` provider registration
- No OGP tag or implementation modification
- No invented human approvals
- No Observation implementation

---

## 20. Post-reconciliation product status

| Item | Status |
|---|---|
| OGP foundation | FROZEN (`organization-governance-profile-foundation-frozen`) |
| Clinical Note | FROZEN, unchanged, no OGP runtime dependency |
| Provider capability production registry | **EMPTY** |
| Real clinical OGP enforcement | **NONE** |
| Manual Vitals engineering | **APPROVED FOR IMPLEMENTATION** |
| Manual Vitals provider registration | **PENDING** |
| Manual Vitals site activation | **PENDING** |
| Observation migration | **UNASSIGNED** (planned `20260814_0021` when implementation starts) |
| AI Clinical | NOT STARTED |
| Frontend Governance UI | NOT IMPLEMENTED |

---

## Sources

- `docs/architecture/observation-vital-signs-write-workflow-design.md`
- `docs/gates/observation-vital-signs-write-workflow-design-approval.md`
- `docs/architecture/organization-governance-profile-design.md`
- `docs/gates/organization-governance-profile-final-freeze.md`
- `docs/architecture/vital-signs-terminology-candidate-catalog.md`
- `docs/gates/vital-signs-terminology-human-approval.md`
- `docs/architecture/vital-signs-terminology-approved-catalog.md`
