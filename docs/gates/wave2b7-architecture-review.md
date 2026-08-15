# Wave 2B.7 — Architecture review and domain-approval result

**Date:** 2026-08-16  
**Scope:** Architecture review, discovery, then explicit Adverse Event design approval  
**Discovery (prior pass):** WAVE 2B.7 was NOT DEFINED; no implementation-ready domain existed in the repository  
**This pass:** Native Adverse Event evaluated against the frozen architecture  
**Decision:** WAVE 2B.7 = APPROVED FOR ADVERSE EVENT — DESIGN ONLY  
**Domain approval:** [docs/clinical/wave2b7-adverse-event-domain-approval.md](../clinical/wave2b7-adverse-event-domain-approval.md)  
**Gate:** [docs/gates/wave2b7-adverse-event-domain-approval.md](wave2b7-adverse-event-domain-approval.md)

This is not an implementation gate. This is not a HIPAA, ISO 27001, or SOC 2 certification. No production code, migration, API, commit, tag, or push is authorized by this document.

Companion canvas: [wave2b7-architecture-review.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/wave2b7-architecture-review.canvas.tsx)

Classification key used below:

- **A** already implemented / frozen
- **B** explicitly proposed but not approved
- **C** explicitly out of scope
- **D** forbidden
- **E** historical / reference-only
- **F** undefined / inferred

`NOT STARTED`, deny-by-default stubs, `FORBIDDEN_TABLES` entries, and old roadmap names are **not** approval.

## A. Frozen baseline

Verified before this review.

| Item | Live value |
|---|---|
| Repository | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Branch | `main` == `origin/main` |
| HEAD | `fdcd24b19d9797034d89b6928c37dc6c47ffe863` |
| Tag | Annotated `wave-2b6-medical-device-frozen` → same SHA |
| Working tree at inspection | CLEAN (this review document and companion canvas are the only intended uncommitted artifacts) |
| Alembic | `current == heads == 20260814_0015` (exactly one head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014 → 0015` |
| Migration `0016` | Does not exist |
| `Wave1PolicyPDP` | Untouched |

`docker-compose.yml` and frozen migrations `0001`–`0015` are not modified by this pass.

## B. Frozen clinical inventory

Implemented native clinical facts. None of these may be redesigned as Wave 2B.7.

| Domain | Wave | Table(s) | Lifecycle (summary) | Identity / anonymous | Encounter |
|---|---|---|---|---|---|
| Encounter | 2A | `encounters`, `encounter_participants` | Class-specific open + status transitions | Anonymous: EMER only | N/A (is the encounter) |
| Clinical Note | 2A | `clinical_notes` | DRAFT → FINAL / ENTERED_IN_ERROR | Via encounter | Required |
| Condition | 2B.1 | `conditions` | Clinical + verification; EIE terminal | Problem list no; EMER diagnosis yes | Optional (type-dependent) |
| Observation | 2B.2a | `observations` | FINAL → AMENDED / EIE | Standalone anonymous 409; EMER allowed | Optional |
| Laboratory | 2B.2b | `laboratory_orders`, `laboratory_specimens`, `laboratory_results` | Three coordinated lifecycles | Anonymous EMER on order | Optional on order |
| Medication | 2B.3a | `medications` | ACTIVE → STOPPED / EIE | Standalone 409; EMER allowed | Optional |
| Allergy | 2B.3b | `allergies` | ACTIVE → AMENDED / EIE | Standalone 409; EMER allowed | Optional |
| Consent | 2B.3c | `consents` | ACTIVE → AMENDED / REVOKED / EIE | Anonymous always 409; not a PDP | Optional |
| Immunization | 2B.4 | `immunizations` | ACTIVE → AMENDED / EIE | Standalone 409; EMER allowed | Optional |
| Procedure | 2B.5 | `procedures` | ACTIVE → AMENDED / EIE | Standalone 409; EMER allowed | Optional |
| Medical Device | 2B.6 | `medical_devices` | ACTIVE → AMENDED / EIE; association `IN_USE` \| `NO_LONGER_USED` | Standalone 409; EMER allowed | Optional |

Shared frozen conventions (do not redesign):

- Canonical identity FK: `patient_identities.id`
- Org / facility scoped writes; org-scoped resource/identity miss = 404
- Optional encounter must be same patient, same org, documentable; clinical facts do not mutate encounters
- Insert-only `clinical_provenances`; service always sets `provenance_id`; FK `ON DELETE RESTRICT`; column nullable by frozen convention
- `X-Purpose` required, normalized, catalog-validated, audited; does not grant access
- Permission-based authorization; not role-name checks; `Wave1PolicyPDP` unknown actions remain deny-by-default
- Lifecycle success audit; Wave 1 DENIED-audit rollback inherited
- PostgreSQL `SELECT FOR UPDATE`; Redis is not a clinical lock
- `app_dml` INSERT / SELECT / UPDATE; DELETE / TRUNCATE revoked
- History / immutability triggers on clinical fact tables
- `/api/v1/clinical` only; PUT / PATCH / DELETE 405 on fact routes; no `/api/v2/`; no `/fhir/`
- Historical `patient_identity_id` is not rewritten after MPI merge

Catalog ends at `WAVE2B6_PERMISSIONS` (`clinical.medical_device.*`). There is no `WAVE2B7_PERMISSIONS`. Clinical module registration ends at Wave 2B.6 Medical Device.

## C. Repository evidence

Searched: `WAVE2B7`, `Wave 2B.7`, `wave2b7`, `NOT STARTED`, out-of-scope lists, `FORBIDDEN_TABLES`, deny-by-default stubs, `clinical.*` permissions, clinical tables, architecture docs, migration planning, README, deferred-domain lists, Patient History, Adverse Event, Vital Signs, Family History, Device-related Event.

| Source | What it says | Meaning for Wave 2B.7 |
|---|---|---|
| `docs/gates/wave2b6-medical-device-final-freeze.md` | `WAVE 2B.7: NOT STARTED` | Status line, not a domain |
| `docs/architecture/modular-monolith.md` | Ends at Wave 2B.6 Medical Device | No 2B.7 module |
| `docs/development/migrations.md` | Ends at `0015` medical_devices | No later schema |
| `docs/clinical/` | No `wave2b7-*` file | Undefined |
| README | No Wave 2B.7 / next-domain text | Undefined |
| Authorization catalog | Ends at `clinical.medical_device.*` | No 2B.7 permissions |
| Clinical `__init__.py` | Ends at Wave 2B.6 Medical Device | No 2B.7 registration |
| Deny-by-default stubs | `clinical.care_plan.create`, `clinical.diagnosis.create` | Unknown actions, not grants |
| `FORBIDDEN_TABLES` | `vital_signs`, `care_plans`, `diagnoses`, `treatments`, `prescriptions`, `imaging_studies`, `clinical_timelines`, `fhir_*` | Forbidden architecture, not a backlog |
| Alembic versions | `0001`–`0015` only | No `0016` |

“Wave 2B.7 NOT STARTED” is not domain approval.

## D. Candidate inventory

Names found in the repository, whether as exclusions, forbidden tables, stubs, or undefined later-fact lists.

| Name | How it appears |
|---|---|
| Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, Medical Device | Implemented and frozen |
| Adverse Event | Exclusion lists on Medical Device design / freeze / hardening; no table, permission, lifecycle, or API |
| Patient History | Same exclusion lists; hardening tests assert `patient_histories` is absent |
| Vital Signs | Observation category `VITAL_SIGNS`; `vital_signs` in `FORBIDDEN_TABLES`; Observation docs own heart rate / BP / SpO2 / temperature |
| Family History | One Medical Device distinction row: “Family history / adverse event — Out of scope this wave” |
| Device-related Event | Not named as a domain. Medical Device out-of-scope includes adverse event; no separate event table |
| CarePlan | `care_plans` forbidden; `clinical.care_plan.create` deny-by-default |
| Separate Diagnosis | `diagnoses` forbidden; `clinical.diagnosis.create` deny-by-default; Condition already stores diagnosis |
| Imaging / treatments / prescriptions / clinical timeline | `FORBIDDEN_TABLES` |
| FHIR resources | `fhir_*` forbidden; modular-monolith forbids FHIR as internal model |
| Consent-as-PDP | Consent freeze: fact, not a grant |
| AI / RAG / CDS | Explicit architecture exclusions |
| Break-glass / patient portal | Explicit out-of-scope |
| Scheduling / forecast / inventory / registry | Immunization, Procedure, Medical Device out-of-scope lists |
| Medical Device UDI / serial / manufacturer / lot | Deferred on frozen Medical Device |
| Procedure performer / site / reason / outcome | Deferred on frozen Procedure |
| Documents | Wave 2A out-of-scope list; no table or permissions |
| `clinical_governance` | Wave 0 shell; rules, not patient facts |
| Coverage / goal | Named only as undefined inferences in the Wave 2B.6 architecture review |

## E. Classification A–F

| Candidate | Evidence | Class |
|---|---|---|
| Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, Medical Device | Implemented and frozen through `0015` | **A** (already shipped; not 2B.7) |
| CarePlan | `care_plans` in `FORBIDDEN_TABLES`; `clinical.care_plan.create` deny-by-default | **D** |
| Separate Diagnosis | `diagnoses` in `FORBIDDEN_TABLES`; Condition owns diagnosis | **D** |
| Vital Signs as a new table | `vital_signs` in `FORBIDDEN_TABLES`; Observation category `VITAL_SIGNS` | **D** (duplicate of **A** Observation) |
| Imaging, treatments, prescriptions, clinical timeline | `FORBIDDEN_TABLES` | **D** |
| FHIR / `/fhir/` / `/api/v2/` | Forbidden tables + modular-monolith | **D** |
| Consent-as-PDP / `Wave1PolicyPDP` rewrite | Consent freeze: fact, not a grant | **D** |
| AI / RAG / CDS | Explicit architecture exclusions | **D** |
| Break-glass / patient portal | Explicit out-of-scope | **C** / **D** |
| Scheduling / forecast / inventory / registry | Out-of-scope lists on frozen Immunization / Procedure / Medical Device | **C** |
| Medical Device UDI / serial / manufacturer / lot | Deferred on frozen Medical Device | Would redesign **A**; not a new wave |
| Procedure performer / site / reason / outcome | Deferred on frozen Procedure | Would redesign **A**; not a new wave |
| Documents | Wave 2A out-of-scope list only | **E** |
| `clinical_governance` | Wave 0 placeholder | **E** |
| Patient History | Exclusion only; no contract | **F** (and structurally an aggregate — see G) |
| Adverse Event | Exclusion only; no contract | **F** |
| Family History | One “out of scope this wave” mention | **F** |
| Device-related Event | Not named as a domain | **F** |
| Coverage / goal | Prior review inference only | **F** |

**Implementation-ready count:** 0.  
**Explicitly proposed-but-not-approved (B) count:** 0.

No candidate is class **B**. Remaining unimplemented names are **C**, **D**, **E**, or **F**.

## F. Vital Signs boundary

Observation already owns vital signs.

Evidence:

- `docs/clinical/wave2b2a-observation.md`: purpose is “clinical measurements and findings such as heart rate, blood pressure components, temperature, oxygen saturation, weight, height”
- Observation categories include `VITAL_SIGNS`
- Medical Device design: “Not `vital_signs` (forbidden; Observation already owns measurements)”
- `FORBIDDEN_TABLES` includes `vital_signs`
- Observation freeze residual: duplicate vitals for the same code/time are allowed (P3), confirming vitals are Observation rows

A separate Vital Signs domain would be a **duplicate / redesign of frozen Observation**. This review does not propose a `vital_signs` table. The repository does not require one; it forbids one.

## G. Patient History boundary

Patient History is **undefined** as a native clinical fact.

It appears only as an exclusion on Medical Device design, implementation, hardening, freeze, and migration docs. There is no table name, category, lifecycle, permission, audit action, provenance subject, API, or migration.

If interpreted as a longitudinal summary of Condition, Medication, Allergy, Procedure, Immunization, Medical Device, Observation, and similar, it is an **aggregate / read model / reporting projection**, not one native documented fact.

That shape would violate the current one-native-fact-per-wave architecture used by Immunization, Procedure, and Medical Device (one table, one lifecycle, one permission family, one provenance subject). Laboratory remains the explicit historical exception (three coordinated tables for one laboratory process), not a license for a cross-domain history aggregate.

This review does not create a Patient History table.

## H. Adverse Event boundary

Adverse Event is **not fully defined**.

It appears only as an exclusion (“do not start Adverse Event”). There is no design document, catalog entry, model, or migration.

Missing implementation-critical decisions (this review does **not** invent them):

- table name
- category
- event status / lifecycle
- severity
- occurrence time
- patient / encounter relationship
- causality
- related medication / device / procedure
- amendability
- entered-in-error semantics
- authorization permission codes
- audit actions
- provenance `subject_type`
- concurrency lock
- migration number
- API boundary

Related medication / device / procedure FKs would also risk redesigning frozen facts or introducing an aggregate family. That is an additional reason not to infer a contract from the name.

Device-related Event is not a separate repository domain. Medical Device explicitly left adverse event out of Wave 2B.6.

## I. Architecture comparison

Viable later work would have to match Immunization / Procedure / Medical Device:

| Dimension | Frozen pattern | Patient History | Adverse Event | Vital Signs table | Family History |
|---|---|---|---|---|---|
| Single native fact vs aggregate | One fact, one table | Aggregate of many frozen facts | Undefined; likely cross-fact | Duplicate Observation | Undefined |
| Identity | `patient_identities.id` + MPI rules | Would inherit if later approved | Undefined | Already Observation | Undefined |
| Encounter | Optional, non-mutating | Undefined | Undefined | Already Observation | Undefined |
| Org / facility | Org-scoped 404 | Would inherit | Undefined | Already Observation | Undefined |
| Lifecycle | ACTIVE/FINAL → AMENDED / EIE | Undefined | Undefined | Already Observation | Undefined |
| Immutability | Identity/code frozen; amendable set explicit | Undefined | Undefined | Already Observation | Undefined |
| Audit / provenance | Named events + insert-only provenance | Undefined | Undefined | Already Observation | Undefined |
| Concurrency | `SELECT FOR UPDATE` | Undefined | Undefined | Already Observation | Undefined |
| Authorization | `clinical.<domain>.*` catalog | None | None | Would collide with `clinical.observation.*` | None |
| Migration | Additive after current head | Would be `0016` only after approval | Same | Forbidden table | Same |
| API | `/api/v1/clinical/<plural>` | Undefined | Undefined | Would redesign Observation | Undefined |
| FHIR creep | Explicitly forbidden | High if treated as “everything about the patient” | High (FHIR AdverseEvent) | High (FHIR Observation vitals) | High (FHIR FamilyMemberHistory) |
| Frozen-domain redesign | Forbidden | High | High if FKs into frozen facts | Direct Observation redesign | Unknown |

No candidate matches the frozen pattern **and** has a repository contract.

## J. Dependencies

Any later native clinical fact would reuse, not replace:

- Frozen MPI (`patient_identities.id`, MERGED / RETIRED / anonymous / EMER rules)
- Optional or required Encounter without mutating encounters
- Existing `X-Purpose` catalog
- Permission catalog + `Wave1PolicyPDP` (unknown actions remain deny-by-default)
- Insert-only `clinical_provenances`
- Additive Alembic after `0015` only
- `/api/v1/clinical` only

It must not depend on Consent as a grant, FHIR as the internal model, Redis as a clinical lock, a new purpose mechanism, or rewriting `0001`–`0015`.

## K. Forbidden / excluded boundaries

Do not start as Wave 2B.7:

- FHIR, `/fhir/`, `/api/v2/`
- Consent-as-PDP or `Wave1PolicyPDP` rewrite
- AI, RAG, CDS
- CarePlan while `care_plans` remains in `FORBIDDEN_TABLES`
- Separate Diagnosis while `diagnoses` remains forbidden and Condition exists
- `vital_signs` while Observation owns measurements
- Imaging, treatments, prescriptions, clinical_timelines
- Break-glass, patient portal
- Scheduling, forecasting, inventory, national registry
- Expanding frozen Medical Device with UDI / serial / manufacturer / lot
- Expanding frozen Procedure with performer / site / reason / outcome
- Patient History as a cross-domain aggregate
- An invented Adverse Event / Family History / Device-related Event contract
- Redesign of any frozen clinical domain

## L. Residual risks

Documented, not redesigned, not selection criteria:

- Wave 1 DENIED-audit rollback with `ForbiddenError`
- Historical `patient_identity_id` is not rewritten after MPI merge
- Same-org UUID clinical read remains org-scoped until a later PDP wave
- `app_dml` grants live in `grant_dev_privileges.sql`
- `provenance_id` nullable (service always sets it)
- Duplicate clinical facts are allowed
- Docker backend image may lag working-tree publication

## M. Final decision

Selection rule applied:

- Exactly one repository-supported, implementation-ready candidate? **No.**
- Multiple named candidates, none with an explicit implementation-ready contract? **Yes** (Patient History, Adverse Event, Family History, and similar are **F**; Vital Signs / CarePlan / Diagnosis are **D**).
- Zero implementation-ready candidates? **Yes.**

Therefore:

**WAVE 2B.7 = NOT DEFINED**

No domain is approved. No domain is recommended. Naming one would invent architecture.

A later domain-approval pass may approve a domain only if it:

1. Names one native documented fact
2. Proves it is not in `FORBIDDEN_TABLES` unless architecture is explicitly changed first
3. Proves it is not a FHIR resource, CarePlan aggregate, Observation duplicate, Patient History projection, or frozen-domain redesign
4. Freezes identity, encounter, lifecycle, immutability, authz, purpose, audit, provenance, API, and migration (`0016` additive only, design then implementation)
5. Leaves `Wave1PolicyPDP` untouched

Until that evidence exists, implementation is forbidden.

## N. Domain-approval pass (design only)

Performed against frozen Medical Device `fdcd24b19d9797034d89b6928c37dc6c47ffe863` / `wave-2b6-medical-device-frozen` / Alembic `20260814_0015`. Chain `0001 → 0015` intact. `Wave1PolicyPDP` untouched. Production code, models, services, APIs, and migrations were not modified.

Discovery class **F** for Adverse Event is no longer the end state: this pass tests whether the frozen architecture can support that named fact as a minimal native row.

| Question | Result |
|---|---|
| Single native clinical fact? | Yes — documented coded adverse event for a patient |
| One-native-fact-per-wave (Immunization/Procedure/Medical Device)? | Yes — one table `adverse_events` |
| New aggregate family? | No — no relationship table, no Patient History |
| Forbidden-table conflict? | None — `adverse_events` is not in `FORBIDDEN_TABLES` |
| FHIR semantics? | No — not FHIR AdverseEvent; no `/fhir/` or `/api/v2/` |
| Consent-as-PDP / AI/RAG/CDS? | No |
| Reuse MPI, encounter, provenance, purpose, RBAC, FOR UPDATE? | Yes |
| Redesign frozen domains? | No — optional FKs are additive on AE only |
| Vital Signs / Patient History? | Remain Observation and out-of-scope aggregate |

Category is `DOCUMENTED` \| `REPORTED`, not related-domain type. Causality, outcome, and `LIFE_THREATENING` are deferred. Related Medication / Medical Device / Procedure pointers are optional, at most one, immutable.

## O. Candidate comparison (this pass)

| Candidate | Classification |
|---|---|
| Native Adverse Event | **Candidate — approved for design** |
| Patient History | Out of scope; aggregate / undefined as a native fact |
| Vital Signs | Already covered by Observation; not a new domain |
| Family History | Undefined; not approved |
| Device-related Event | Not a separate domain; optional `medical_device_id` on Adverse Event |
| CarePlan | Forbidden (`care_plans`) |
| Separate Diagnosis | Forbidden (`diagnoses`); Condition already owns it |

## P. Final decision

**WAVE 2B.7 = APPROVED FOR ADVERSE EVENT**  
**DESIGN ONLY**

CarePlan is not approved. Diagnosis is not approved. Patient History is not approved. Vital Signs is not a new domain. Family History is not approved. Production code is untouched.

WAVE 2B.6 MEDICAL DEVICE = FROZEN  
WAVE 2B.6 MEDICAL DEVICE = PUBLISHED  
WAVE 2B.7 NATIVE ADVERSE EVENT = APPROVED FOR DESIGN ONLY  
WAVE 2B.7 NATIVE ADVERSE EVENT = NOT STARTED (implementation)

NO CODE  
NO MODEL  
NO SERVICE  
NO API  
NO SCHEMA  
NO PERMISSION  
NO GRANT  
NO TRIGGER  
NO MIGRATION 0016  
NO TEST IMPLEMENTATION  
NO PRODUCTION CHANGE  
NO COMMIT  
NO TAG  
NO PUSH
