# Wave 2B.8 — Architecture review and domain-approval result

**Date:** 2026-08-16  
**Scope:** Architecture review, discovery, then explicit Family History design approval  
**Discovery (prior pass):** WAVE 2B.8 was NOT DEFINED; no implementation-ready domain existed in the repository  
**This pass:** Native Family History evaluated against the frozen architecture  
**Decision:** WAVE 2B.8 = APPROVED FOR FAMILY HISTORY — DESIGN ONLY  
**Domain approval:** [docs/clinical/wave2b8-family-history-domain-approval.md](../clinical/wave2b8-family-history-domain-approval.md)  
**Gate:** [docs/gates/wave2b8-family-history-domain-approval.md](wave2b8-family-history-domain-approval.md)

This is not an implementation gate. This is not a HIPAA, ISO 27001, or SOC 2 certification. No production code, migration, API, commit, tag, or push is authorized by this document.

Companion canvas: [wave2b8-architecture-review.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/wave2b8-architecture-review.canvas.tsx)

Classification key:

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
| HEAD | `8d455b3dede07b9ada00205ff6c49b41b97a0895` |
| Tag | Annotated `wave-2b7-adverse-event-frozen` → same SHA |
| Parent | `fdcd24b19d9797034d89b6928c37dc6c47ffe863` (`wave-2b6-medical-device-frozen`) |
| Working tree at inspection | CLEAN except this review document (canvas lives outside git) |
| Alembic | `current == heads == 20260814_0016` (exactly one head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014 → 0015 → 0016` |
| Migration `0017` | Does not exist |
| `Wave1PolicyPDP` | Untouched |
| Migrations `0001`–`0016` | Unchanged by this pass |

`docker-compose.yml` is not modified. Frozen domains are not redesigned.

## B. Frozen clinical inventory

Implemented native clinical facts. None of these may be redesigned as Wave 2B.8. Adverse Event and Medical Device are already frozen and must not be proposed again.

| Domain | Wave | Table(s) | API (under `/api/v1/clinical`) | Lifecycle (summary) | Permissions | Audit | Provenance | Migration | Freeze evidence |
|---|---|---|---|---|---|---|---|---|---|
| Encounter | 2A | `encounters`, `encounter_participants` | POST/GET `/encounters`, GET `{id}`, POST `{id}/status` | Class-specific open + status transitions; EIE terminal | `clinical.encounter.create\|read\|update_status` | `ENCOUNTER_CREATED`, `ENCOUNTER_STATUS_CHANGED` | `ENCOUNTER` | `0004` / `0005` | `docs/gates/wave2a-final-freeze.md` |
| Clinical Note | 2A | `clinical_notes` | POST/GET `/notes`, POST `{id}`, `{id}/finalize`, `{id}/entered-in-error` | DRAFT → FINAL / ENTERED_IN_ERROR | `clinical.note.create\|read\|update_draft\|finalize` | `CLINICAL_NOTE_*` | `CLINICAL_NOTE` | `0004` / `0005` | `docs/gates/wave2a-final-freeze.md` |
| Condition | 2B.1 | `conditions` | POST/GET `/conditions`, GET `{id}`, POST `{id}/status`, `{id}/entered-in-error` | Clinical + verification; EIE terminal | `clinical.condition.create\|read\|update\|entered_in_error` | `CONDITION_*` | `CONDITION` | `0006` / `0007` | Subsequent-wave freeze baselines; `docs/gates/wave2b1-condition-final-hardening-review.md` |
| Observation | 2B.2a | `observations` | POST/GET `/observations`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | FINAL → AMENDED / EIE | `clinical.observation.*` | `OBSERVATION_*` | `OBSERVATION` | `0008` | `docs/gates/wave2b2a-observation-final-freeze.md` |
| Laboratory | 2B.2b | `laboratory_orders`, `laboratory_specimens`, `laboratory_results` | `/laboratory/orders\|specimens\|results` plus cancel/amend/EIE | Three coordinated lifecycles | `clinical.laboratory.{order,specimen,result}.*` | `LAB_*` | `LABORATORY_ORDER\|SPECIMEN\|RESULT` | `0009` | `docs/gates/wave2b2b-laboratory-final-freeze.md` |
| Medication | 2B.3a | `medications` | POST/GET `/medications`, GET `{id}`, POST `{id}/stop`, `{id}/entered-in-error` | ACTIVE → STOPPED / EIE | `clinical.medication.*` | `MEDICATION_*` | `MEDICATION` | `0010` | `docs/gates/wave2b3a-medication-final-freeze.md` |
| Allergy | 2B.3b | `allergies` | POST/GET `/allergies`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.allergy.*` | `ALLERGY_*` | `ALLERGY` | `0011` | `docs/gates/wave2b3b-allergy-final-freeze.md` |
| Consent | 2B.3c | `consents` | POST/GET `/consents`, GET `{id}`, POST `{id}/amend`, `{id}/revoke`, `{id}/entered-in-error` | ACTIVE → AMENDED / REVOKED / EIE | `clinical.consent.create\|read\|update\|revoke\|entered_in_error` | `CONSENT_*` | `CONSENT` | `0012` | `docs/gates/wave2b3c-consent-final-freeze.md` |
| Immunization | 2B.4 | `immunizations` | POST/GET `/immunizations`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.immunization.*` | `IMMUNIZATION_*` | `IMMUNIZATION` | `0013` | `docs/gates/wave2b4-immunization-final-freeze.md` |
| Procedure | 2B.5 | `procedures` | POST/GET `/procedures`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.procedure.*` | `PROCEDURE_*` | `PROCEDURE` | `0014` | `docs/gates/wave2b5-procedure-final-freeze.md` |
| Medical Device | 2B.6 | `medical_devices` | POST/GET `/medical-devices`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE; association `IN_USE` \| `NO_LONGER_USED` | `clinical.medical_device.*` | `MEDICAL_DEVICE_*` | `MEDICAL_DEVICE` | `0015` | `docs/gates/wave2b6-medical-device-final-freeze.md`; tag `wave-2b6-medical-device-frozen` |
| Adverse Event | 2B.7 | `adverse_events` | POST/GET `/adverse-events`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.adverse_event.*` | `ADVERSE_EVENT_*` | `ADVERSE_EVENT` | `0016` | `docs/gates/wave2b7-adverse-event-final-freeze.md`; tag `wave-2b7-adverse-event-frozen` |

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

Catalog ends at `WAVE2B7_PERMISSIONS` (`clinical.adverse_event.*`). There is no `WAVE2B8_PERMISSIONS`. Clinical module registration ends at Wave 2B.7 Adverse Event.

## C. Repository search results

Searched: `WAVE2B8`, `Wave 2B.8`, `2B.8`, `wave2b8`, `NOT STARTED`, `NOT DEFINED`, domain approval, candidate, proposed domain, clinical domain, future domain, deferred domain, out-of-scope, `FORBIDDEN_TABLES`, deny-by-default stubs, README, architecture docs, clinical docs, gate documents, migration docs, authorization catalog, clinical enums, models, routes, tests, comments mentioning future waves.

| Source | What it says | Meaning for Wave 2B.8 |
|---|---|---|
| `docs/gates/wave2b7-adverse-event-final-freeze.md` | `WAVE 2B.8: NOT STARTED` | Status line, not a domain |
| `docs/architecture/modular-monolith.md` | Ends at Wave 2B.7 Adverse Event | No 2B.8 module |
| `docs/development/migrations.md` | Ends at `0016` adverse_events | No later schema |
| `docs/clinical/` | No `wave2b8-*` file | Undefined |
| README | No Wave 2B.8 / next-domain text; still says later waves own FHIR/AI | Undefined / stale overview |
| Authorization catalog | Ends at `clinical.adverse_event.*` | No 2B.8 permissions |
| Clinical `__init__.py` | Ends at Wave 2B.7 Adverse Event | No 2B.8 registration |
| Deny-by-default stubs | `clinical.care_plan.create`, `clinical.diagnosis.create` | Unknown actions, not grants |
| `FORBIDDEN_TABLES` | `vital_signs`, `care_plans`, `diagnoses`, `treatments`, `prescriptions`, `imaging_studies`, `clinical_timelines`, `fhir_*` | Forbidden architecture, not a backlog |
| Wave 2B.7 tests | Also assert `patient_histories` and `fhir_adverse_events` absent | Absence probe, not a backlog |
| Alembic versions | `0001`–`0016` only | No `0017` |
| `docs/security/file-security.md` | “Magic-byte and malware scanning arrive with the Documents wave” | Historical mention, not a contract |

“Wave 2B.8 NOT STARTED” is not domain approval.

## D. Candidate inventory

Names found in the repository, whether as exclusions, forbidden tables, stubs, deferred fields, or undefined later-fact lists.

| Name | How it appears |
|---|---|
| Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, Medical Device, Adverse Event | Implemented and frozen |
| Vital Signs | Observation category `VITAL_SIGNS`; `vital_signs` in `FORBIDDEN_TABLES`; Observation docs own heart rate / BP / SpO2 / temperature |
| Patient History | Exclusion lists on Medical Device / Adverse Event design / freeze / hardening; tests assert `patient_histories` is absent |
| Family History | Medical Device distinction row and Adverse Event out-of-scope list; no table, permission, lifecycle, or API |
| CarePlan | `care_plans` forbidden; `clinical.care_plan.create` deny-by-default |
| Separate Diagnosis | `diagnoses` forbidden; `clinical.diagnosis.create` deny-by-default; Condition already stores diagnosis |
| Documents | Wave 2A out-of-scope list; README forbids real clinical documents in-repo; file-security mentions a later “Documents wave” |
| Device-related Event | Not named as a domain. Adverse Event already has optional immutable `medical_device_id` |
| Treatment | `treatments` in `FORBIDDEN_TABLES` |
| Prescription | `prescriptions` in `FORBIDDEN_TABLES`; Medication is the native medication fact |
| Imaging | `imaging_studies` in `FORBIDDEN_TABLES` |
| Goals / Coverage | Named only as undefined inferences in Wave 2B.6 architecture review; Wave 2A says coverage never blocks a write |
| Clinical timeline / Patient Summary / Dashboard / Registry | Timeline forbidden; others unnamed aggregates |
| FHIR resources | `fhir_*` forbidden; modular-monolith forbids FHIR as internal model |
| Consent-as-PDP | Consent freeze: fact, not a grant |
| AI / RAG / CDS | Explicit architecture exclusions |
| Break-glass / patient portal | Explicit out-of-scope |
| Scheduling / forecast / inventory / pharmacovigilance / incident management / registry | Out-of-scope lists on frozen Immunization / Procedure / Medical Device / Adverse Event |
| Adverse Event causality / outcome / `LIFE_THREATENING` | Deferred on **frozen** Adverse Event |
| Medical Device UDI / serial / manufacturer / lot | Deferred on **frozen** Medical Device |
| Procedure performer / site / reason / outcome | Deferred on **frozen** Procedure |
| `clinical_governance` | Wave 0 shell; rules, not patient facts |

## E. Classification A–F

| Candidate | Evidence | Classification | Why |
|---|---|---|---|
| Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure, Medical Device, Adverse Event | Implemented and frozen through `0016` | **A** | Already shipped; not Wave 2B.8 |
| CarePlan | `care_plans` in `FORBIDDEN_TABLES`; `clinical.care_plan.create` deny-by-default | **D** | Forbidden table + stub is not a backlog |
| Separate Diagnosis | `diagnoses` in `FORBIDDEN_TABLES`; Condition owns diagnosis | **D** | Duplicate of frozen Condition |
| Vital Signs as a new table | `vital_signs` in `FORBIDDEN_TABLES`; Observation category `VITAL_SIGNS` | **D** | Duplicate of frozen Observation |
| Imaging, treatments, prescriptions, clinical timeline | `FORBIDDEN_TABLES` | **D** | Explicitly forbidden |
| FHIR / `/fhir/` / `/api/v2/` | Forbidden tables + modular-monolith | **D** | Forbidden architecture |
| Consent-as-PDP / `Wave1PolicyPDP` rewrite | Consent freeze: fact, not a grant | **D** | Forbidden architecture |
| AI / RAG / CDS | Explicit architecture exclusions | **D** | Forbidden architecture |
| Pharmacovigilance / incident management | Adverse Event freeze: AE is not those systems | **D** / **C** | Explicitly excluded from frozen AE |
| Break-glass / patient portal | Explicit out-of-scope | **C** / **D** | Not a native fact contract |
| Scheduling / forecast / inventory / registry | Out-of-scope lists on frozen Immunization / Procedure / Medical Device / Adverse Event | **C** | Explicitly out of scope |
| Expanding frozen AE with causality / outcome / `LIFE_THREATENING` | Deferred on frozen Adverse Event | Would redesign **A** | Not a new wave |
| Expanding frozen Medical Device with UDI / serial / manufacturer / lot | Deferred on frozen Medical Device | Would redesign **A** | Not a new wave |
| Expanding frozen Procedure with performer / site / reason / outcome | Deferred on frozen Procedure | Would redesign **A** | Not a new wave |
| Documents | Wave 2A out-of-scope + file-security “Documents wave” sentence; no table or permissions | **E** | Historical mention, not a contract |
| `clinical_governance` | Wave 0 placeholder | **E** | Rules shell, not a patient fact |
| Patient History | Exclusion only; no contract | **F** | Undefined; structurally an aggregate |
| Family History | Out-of-scope mentions only | **F** | Undefined / inferred |
| Device-related Event | Not named as a domain; AE already points at devices | **F** | Duplicate of frozen AE related-fact |
| Coverage / goal | Prior review inference only | **F** | Undefined / inferred |

**Implementation-ready count:** 0.  
**Explicitly proposed-but-not-approved (B) count:** 0.

No candidate is class **B**. Remaining unimplemented names are **C**, **D**, **E**, or **F**.

## F. Implementation-ready assessment

A domain is implementation-ready only if the repository already supplies enough explicit contract evidence to implement it without inventing major semantics.

Checked against: clinical fact definition, identity, encounter, org/facility, lifecycle, immutable fields, amendable fields, terminal state, authorization, purpose, audit, provenance, concurrency, API boundary, table semantics, migration placement, validation rules, out-of-scope boundaries.

| Candidate | Contract evidence | Result |
|---|---|---|
| Frozen Class A domains | Complete | Already implemented; not 2B.8 |
| CarePlan / Diagnosis / Vital Signs table / Imaging / Treatment / Prescription | Forbidden or already owned | Not implementable as a new native fact |
| Patient History | Missing all 18 contract items | **F**, not ready |
| Family History | Missing all 18 contract items | **F**, not ready |
| Documents | Security policy only; missing fact, lifecycle, authz, API, table | **E**, not ready |
| Coverage / goal / Device-related Event | Name only | **F**, not ready |
| Deferred columns on frozen AE / Device / Procedure | Would rewrite frozen semantics | Not a new domain |

No unimplemented name has an explicit implementation-ready contract.

## G. Duplicate-domain analysis

| Possible name | Existing owner | Conclusion |
|---|---|---|
| Diagnosis | Condition (`conditions`; problem list and encounter diagnosis) | Do not propose a new domain |
| Vital Signs | Observation (`observations`; category `VITAL_SIGNS`) | Do not propose a new domain |
| Medical Device / implant association | Medical Device (`medical_devices`) | Already frozen |
| Adverse Event / reaction documentation | Adverse Event (`adverse_events`) | Already frozen |
| Device-related Event | Adverse Event optional `medical_device_id` | Already owned; not a separate fact |
| Prescription / administration | Medication (`medications`; stop lifecycle exists) | Do not propose `prescriptions` |
| Treatment as a performed act | Procedure (`procedures`) | Do not propose `treatments` |
| Imaging report as lab-like result | Laboratory / Observation already cover measured/result facts; `imaging_studies` is forbidden | Do not invent Imaging |
| Patient History / Clinical Timeline / Patient Summary / Dashboard / Clinical Profile | Would project many frozen facts | Aggregate, not a native fact |
| Family History | No owner and no contract | Undefined; do not invent |

## H. Forbidden / out-of-scope analysis

Do not start as Wave 2B.8:

- FHIR, `/fhir/`, `/api/v2/`
- Consent-as-PDP or `Wave1PolicyPDP` rewrite
- AI, RAG, CDS
- CarePlan while `care_plans` remains in `FORBIDDEN_TABLES`
- Separate Diagnosis while `diagnoses` remains forbidden and Condition exists
- `vital_signs` while Observation owns measurements
- Imaging, treatments, prescriptions, clinical_timelines
- Pharmacovigilance platform or incident-management system
- Break-glass, patient portal
- Scheduling, forecasting, inventory, national registry, warehouse/asset management
- Expanding frozen Adverse Event with causality / outcome / `LIFE_THREATENING`
- Expanding frozen Medical Device with UDI / serial / manufacturer / lot
- Expanding frozen Procedure with performer / site / reason / outcome
- Patient History as a cross-domain aggregate
- An invented Family History / Documents / Coverage / Goal / Device-related Event contract
- Redesign of any frozen clinical domain

## I. Architecture comparison

Viable later work would have to match Immunization / Procedure / Medical Device / Adverse Event:

| Dimension | Frozen pattern | Patient History | Family History | Documents | Vital Signs table |
|---|---|---|---|---|---|
| Single native fact vs aggregate | One fact, one table | Aggregate of many frozen facts | Undefined | Upload/security policy, not a fact | Duplicate Observation |
| Identity | `patient_identities.id` + MPI rules | Would inherit if later approved | Undefined | Undefined | Already Observation |
| Encounter | Optional, non-mutating | Undefined | Undefined | Undefined | Already Observation |
| Lifecycle | ACTIVE/FINAL → AMENDED / EIE | Undefined | Undefined | Undefined | Already Observation |
| Authorization | `clinical.<domain>.*` catalog | None | None | None | Would collide with `clinical.observation.*` |
| Migration | Additive after current head | Would be `0017` only after approval | Same | Same | Forbidden table |
| FHIR creep | Explicitly forbidden | High if treated as “everything about the patient” | High (FHIR FamilyMemberHistory) | High (FHIR DocumentReference) | High (FHIR Observation vitals) |
| Frozen-domain redesign | Forbidden | High | Unknown | Unknown | Direct Observation redesign |

No candidate matches the frozen pattern **and** has a repository contract.

Wave 2A listed diagnosis, condition, observation, laboratory, medication, allergy, immunization, procedure, care plan, consent, FHIR, AI, timeline, and documents as out of scope. Every legitimate native fact on that list that was **not** forbidden has already been implemented through Wave 2B.7. Remaining names are forbidden, out of scope, historical, already frozen, or undefined.

## J. Conflicts / blockers

- Selecting any named unimplemented candidate would invent identity, lifecycle, immutability, authz, audit, provenance, API, and migration semantics.
- `FORBIDDEN_TABLES` and deny-by-default stubs (`clinical.care_plan.create`, `clinical.diagnosis.create`) are boundary tests, not a product backlog.
- Laboratory remains the explicit historical exception (three coordinated tables). It is not a license for Patient History, CarePlan, or other aggregates.
- Deferred fields on frozen Adverse Event, Medical Device, and Procedure are residuals of those freezes. Implementing them now would redesign frozen domains, which this pass forbids.
- Any later native clinical fact would reuse frozen MPI, optional Encounter, `X-Purpose`, permission catalog + untouched `Wave1PolicyPDP`, insert-only provenance, PostgreSQL `SELECT FOR UPDATE`, and additive Alembic after `0016` only. Those shared conventions are not themselves a domain.

Inherited residuals (not selection criteria; not redesigned here):

- Wave 1 DENIED-audit rollback with `ForbiddenError`
- Historical `patient_identity_id` is not rewritten after MPI merge
- Same-org UUID clinical read remains org-scoped until a later PDP wave
- `app_dml` grants live in `grant_dev_privileges.sql`
- `provenance_id` nullable (service always sets it)
- Duplicate clinical facts are allowed
- Docker backend image may lag working-tree publication

## K. Decision

Selection rule applied:

- **Case 1** — Exactly one repository-supported, implementation-ready candidate? **No.**
- **Case 2** — Multiple candidates exist but none has sufficient contract evidence? **Yes** (Patient History, Family History, Documents, Coverage/Goal, and similar).
- **Case 3** — All remaining candidates are forbidden, out-of-scope, historical, already frozen, or undefined? **Yes.**
- **Case 4** — Explicitly proposed but unapproved (class B)? **No such candidate.**

Therefore:

**WAVE 2B.8 = NOT DEFINED**

No domain is approved. No domain is recommended. Naming one would invent architecture.

A later domain-approval pass may approve a domain only if it:

1. Names one native documented fact
2. Proves it is not in `FORBIDDEN_TABLES` unless architecture is explicitly changed first
3. Proves it is not a FHIR resource, CarePlan aggregate, Observation duplicate, Patient History projection, frozen Adverse Event/Medical Device/Procedure redesign, or other frozen-domain redesign
4. Freezes identity, encounter, lifecycle, immutability, authz, purpose, audit, provenance, API, and migration (`0017` additive only, design then implementation)
5. Leaves `Wave1PolicyPDP` untouched

Until that evidence exists, implementation is forbidden.

NO DOMAIN APPROVED  
NO CODE  
NO MODEL  
NO SERVICE  
NO API  
NO SCHEMA  
NO PERMISSION  
NO GRANT  
NO TRIGGER  
NO MIGRATION 0017  
NO TEST IMPLEMENTATION  
NO PRODUCTION CHANGE  
NO COMMIT  
NO TAG  
NO PUSH

WAVE 2B.7 ADVERSE EVENT = FROZEN  
WAVE 2B.7 ADVERSE EVENT = PUBLISHED  
WAVE 2B.8 = NOT DEFINED

## L. Files changed (discovery pass)

Discovery artifacts:

- `docs/gates/wave2b8-architecture-review.md` (this document)
- companion canvas outside git: `wave2b8-architecture-review.canvas.tsx`

## M. Production code status

Untouched. No changes to `backend/app`, `backend/alembic`, `backend/tests`, authorization catalog, services, repositories, schemas, routes, lifecycle, models, or grants.

## N. Domain-approval pass (design only)

Performed against frozen Adverse Event `8d455b3dede07b9ada00205ff6c49b41b97a0895` / `wave-2b7-adverse-event-frozen` / Alembic `20260814_0016`. Chain `0001 → 0016` intact. `Wave1PolicyPDP` untouched. Production code, models, services, APIs, and migrations were not modified.

Discovery class **F** for Family History is no longer the end state: this pass tests whether the frozen architecture can support that named fact as a minimal native row.

| Question | Result |
|---|---|
| Single native clinical fact? | Yes — documented/reported family-history fact: one relationship + one coded finding for a patient |
| One-native-fact-per-wave (Immunization/Procedure/Medical Device/Adverse Event)? | Yes — one table `family_histories` |
| New aggregate family? | No — no relative master table, no Patient History table |
| Forbidden-table conflict? | None — `family_histories` is not in `FORBIDDEN_TABLES` |
| Already owned? | No — Condition owns the patient's own diagnosis; Observation owns vitals; Adverse Event owns the patient's own harm event |
| FHIR semantics? | No — not FHIR FamilyMemberHistory; no `/fhir/` or `/api/v2/` |
| Consent-as-PDP / AI/RAG/CDS? | No |
| Reuse MPI, encounter, provenance, purpose, RBAC, FOR UPDATE? | Yes |
| Redesign frozen domains? | No — no FKs onto frozen fact tables |
| Patient History? | Remains a presentation/read-model; not a table |

Relationship is a closed eight-value CHECK enum (`PARENT`, `SIBLING`, `CHILD`, `GRANDPARENT`, `GRANDCHILD`, `AUNT_UNCLE`, `COUSIN`, `OTHER`). Category is `DOCUMENTED` \| `REPORTED`. Finding uses the frozen `code_system` + `code` + optional display stub, not a Condition FK. Relative identity, deceased, and age-at-onset are deferred.

## O. Candidate comparison (this pass)

| Candidate | Classification |
|---|---|
| Native Family History | **Candidate — approved for design** |
| Patient History | Out of scope; aggregate / read-model; not a table |
| Vital Signs | Already covered by Observation; not a new domain |
| CarePlan | Forbidden (`care_plans`) |
| Separate Diagnosis | Forbidden (`diagnoses`); Condition already owns it |
| Adverse Event | Already frozen; must not be proposed again |
| Medical Device | Already frozen; must not be proposed again |
| Documents / Coverage / Goal | Undefined or historical; not approved |

## P. Final decision

**WAVE 2B.8 = APPROVED FOR FAMILY HISTORY**  
**DESIGN ONLY**

CarePlan is not approved. Diagnosis is not approved. Patient History is not approved. Vital Signs is not a new domain. Production code is untouched.

WAVE 2B.7 ADVERSE EVENT = FROZEN  
WAVE 2B.7 ADVERSE EVENT = PUBLISHED  
WAVE 2B.8 NATIVE FAMILY HISTORY = APPROVED FOR DESIGN ONLY  
WAVE 2B.8 NATIVE FAMILY HISTORY = NOT STARTED (implementation)

NO CODE  
NO MODEL  
NO SERVICE  
NO API  
NO SCHEMA  
NO PERMISSION  
NO GRANT  
NO TRIGGER  
NO MIGRATION 0017  
NO TEST IMPLEMENTATION  
NO PRODUCTION CHANGE  
NO COMMIT  
NO TAG  
NO PUSH
