# Wave 2B.6 — Architecture review and domain-approval result

**Date:** 2026-08-15  
**Scope:** Architecture review, discovery, then explicit Medical Device design approval  
**Discovery (prior pass):** WAVE 2B.6 was NOT DEFINED; no implementation-ready domain existed in the repository  
**This pass:** Native Medical Device evaluated against the frozen architecture  
**Decision:** WAVE 2B.6 = APPROVED FOR MEDICAL DEVICE — DESIGN ONLY  
**Domain approval:** [docs/clinical/wave2b6-medical-device-domain-approval.md](../clinical/wave2b6-medical-device-domain-approval.md)  
**Gate:** [docs/gates/wave2b6-medical-device-domain-approval.md](wave2b6-medical-device-domain-approval.md)

This is not an implementation gate. This is not a HIPAA, ISO 27001, or SOC 2 certification. No production code, migration, API, commit, tag, or push is authorized by this document.

Companion canvas: [wave2b6-architecture-review.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/wave2b6-architecture-review.canvas.tsx)

## A. Frozen baseline

| Item | Live value |
|---|---|
| Repository | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Branch | `main` == `origin/main` |
| HEAD | `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad` |
| Tag | Annotated `wave-2b5-procedure-frozen` → same SHA |
| Working tree at inspection | CLEAN (this review document is the only intended uncommitted artifact) |
| Alembic | `current == heads == 20260814_0014` |
| Chain | `0001 → … → 0013 → 0014` |
| Migrations `0001`–`0014` | Frozen publication; this pass does not add `0015` |

`Wave1PolicyPDP`, `docker-compose.yml`, and `gsai-minio` are untouched by this review.

## B. Current clinical inventory

Implemented native clinical facts. None of these may be redesigned as Wave 2B.6.

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

Shared frozen conventions (do not redesign):

- Canonical identity FK: `patient_identities.id`
- Org-scoped resource/identity miss = 404
- `X-Purpose` required, normalized, audited; does not grant access
- Permission-based authorization; not role-name checks
- Insert-only `clinical_provenances`; service always sets `provenance_id`; FK `ON DELETE RESTRICT`; column nullable by frozen convention
- Lifecycle success audit; Wave 1 DENIED-audit rollback inherited
- PostgreSQL `SELECT FOR UPDATE`; Redis is not a clinical lock
- `/api/v1/clinical` only; PUT/PATCH/DELETE 405 on fact routes; no `/api/v2/`; no `/fhir/`
- Historical `patient_identity_id` is not rewritten after MPI merge

Catalog ends at `WAVE2B5_PERMISSIONS` (`clinical.procedure.*`). There is no `WAVE2B6_PERMISSIONS`. Clinical module registration ends at Wave 2B.5 Procedure.

## C. Existing Wave 2B.6 definition

**None.**

| Source | What it says | Classification |
|---|---|---|
| `docs/gates/wave2b5-procedure-final-freeze.md` | `WAVE 2B.6: NOT STARTED` | Status line, not a domain |
| `docs/architecture/modular-monolith.md` | Ends at Wave 2B.5 Procedure | No 2B.6 module |
| `docs/development/migrations.md` | Ends at `0014` procedures | No later schema |
| `docs/clinical/` | No `wave2b6-*` file | Undefined |
| README | Stale Wave 0/1 text; no 2B.6 | Undefined |
| Authorization catalog | Ends at procedure permissions | No 2B.6 permissions |
| Clinical `__init__.py` | Ends at Wave 2B.5 Procedure | No 2B.6 registration |
| Deny-by-default stubs | `clinical.care_plan.create`, `clinical.diagnosis.create` | Unknown actions, not grants |
| `FORBIDDEN_TABLES` | Includes `care_plans`, `diagnoses`, FHIR tables, `treatments`, `imaging_studies`, … | Forbidden architecture, not a backlog |

“Wave 2B.6 NOT STARTED” is not domain approval.

## D. Candidate domains found

| Name | How it appears | Classification |
|---|---|---|
| CarePlan | Deny-by-default stub `clinical.care_plan.create`; `care_plans` in `FORBIDDEN_TABLES`; repeated “do not start” in freeze/hardening docs | Forbidden table + deny-by-default stub. Not an approved domain. |
| Separate Diagnosis | Deny-by-default stub `clinical.diagnosis.create`; `diagnoses` in `FORBIDDEN_TABLES`; Condition already stores problem list and encounter diagnosis | Forbidden table. Would duplicate Condition. |
| Imaging | `imaging_studies` in `FORBIDDEN_TABLES` | Forbidden |
| Treatments | `treatments` in `FORBIDDEN_TABLES` | Forbidden |
| Prescriptions | `prescriptions` in `FORBIDDEN_TABLES`; Medication is the native medication fact | Forbidden |
| Vital signs | `vital_signs` in `FORBIDDEN_TABLES`; Observation is the native measurement fact | Forbidden |
| Clinical timeline | `clinical_timelines` in `FORBIDDEN_TABLES` | Forbidden |
| FHIR resources | `fhir_*` in `FORBIDDEN_TABLES`; modular-monolith forbids FHIR as internal model | Forbidden architecture |
| Consent-as-PDP | Consent freeze: fact, not a grant | Forbidden architecture |
| AI / RAG / CDS | Explicit out-of-scope since Wave 0/2A | Forbidden architecture |
| Break-glass / patient portal | Explicit out-of-scope | Forbidden architecture |
| Scheduling / forecast / inventory / registry | Procedure and Immunization out-of-scope lists | Not approved |
| Procedure performer / site / reason | Deferred on frozen Procedure | Would redesign Procedure |
| Unnamed later facts (family history, device/implant, adverse event, coverage, goal, document) | Not present in catalog, models, migrations, or clinical docs | Completely undefined |

## E. Candidate comparison matrix

| Dimension | CarePlan | Separate Diagnosis | Expanding frozen Procedure | Unnamed native fact (e.g. family history / device) |
|---|---|---|---|---|
| Native fact vs aggregate | Aggregate (goals, activities, authors, references) | Duplicate of Condition | Field expansion of an existing fact | Could be one documented fact — undefined |
| Table shape | `care_plans` forbidden | `diagnoses` forbidden | Extra columns/tables on `procedures` | Unknown; not in repo |
| Lifecycle | Undefined and large | Conflicts with Condition verification | Would reopen frozen amendable set | Undefined |
| Identity | Would use frozen MPI | Same | Same | Would use frozen MPI if later approved |
| Encounter | Longitudinal plan; not a single encounter fact | Condition already binds encounter diagnosis | Frozen optional encounter | Undefined |
| Org / facility | Would inherit org-scope | Same | Same | Would inherit if later approved |
| Provenance / audit | Would need new subject type | Duplicate | Would mutate frozen Procedure audit | Undefined |
| Authorization | Stub exists only as deny-by-default | Stub exists only as deny-by-default | Existing `clinical.procedure.*` | No catalog entry |
| Concurrency / immutability | Undefined | Conflicts with Condition | Would change frozen trigger | Undefined |
| API | Would be new `/care-plans` | Would collide with Condition | Would change Procedure API | Undefined |
| Migration | Requires lifting `FORBIDDEN_TABLES` | Requires lifting `FORBIDDEN_TABLES` | Rewrite of frozen `0014` behavior | Additive `0015` only after approval |
| Frozen-domain impact | High — would reference many facts | High — Condition owns diagnosis | Direct Procedure redesign | Catalog/boundary only if kept native |
| Architecture freeze conflict | Direct | Direct | Direct | None yet — also no design |
| Unresolved decisions | Entire model | Entire overlap with Condition | Entire deferred field set | Entire model |

No candidate has an approved contract.

## F. Architectural dependencies

Any later native clinical fact would reuse, not replace:

- Frozen MPI (`patient_identities.id`, MERGED/RETIRED/anonymous rules)
- Optional or required Encounter without mutating encounters
- Existing `X-Purpose` catalog
- Permission catalog + `Wave1PolicyPDP` (unknown actions remain deny-by-default)
- Insert-only `clinical_provenances`
- Additive Alembic after `0014` only
- `/api/v1/clinical` only

It must not depend on Consent as a grant, FHIR as the internal model, Redis as a clinical lock, or a new purpose mechanism.

## G. Frozen-domain impact

Wave 2B.6, if later defined, may register a new native domain and move deny-by-default stubs. It must not change Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, or Procedure behavior, tables, or APIs. It must not rewrite migrations `0001`–`0014`. It must not modify `Wave1PolicyPDP`.

## H. Architecture exclusions

Do not start as Wave 2B.6:

- FHIR, `/fhir/`, `/api/v2/`
- Consent-as-PDP or `Wave1PolicyPDP` rewrite
- AI, RAG, CDS
- CarePlan while `care_plans` remains in `FORBIDDEN_TABLES`
- Separate Diagnosis while `diagnoses` remains forbidden and Condition exists
- Imaging, treatments, prescriptions, vital_signs, clinical_timelines
- Break-glass, patient portal
- Scheduling, forecasting, inventory, national registry
- Redesign of any frozen clinical domain

## I. Inherited residual risks

Documented, not redesigned, not selection criteria:

- Wave 1 DENIED-audit rollback with `ForbiddenError`
- Historical `patient_identity_id` is not rewritten after MPI merge
- Same-org UUID clinical read remains org-scoped until a later PDP wave
- `app_dml` grants live in `grant_dev_privileges.sql`
- `provenance_id` nullable (service always sets it)
- Duplicate clinical facts are allowed

## J. Recommended candidate

**None justified.**

Wave 2B.5 could recommend Procedure because design material named it, the deny-by-default stub pointed at it, and `procedures` was **not** in `FORBIDDEN_TABLES`.

Wave 2B.6 has the opposite signal: the current deny-by-default stub is `clinical.care_plan.create`, and `care_plans` **is** forbidden. That stub is a boundary test, not a backlog item.

No remaining named native fact in repository documentation is both unimplemented and allowed. Unnamed later facts (family history, device, adverse event, and similar) are completely undefined. Recommending one would invent a domain.

Label if a later pass names one: **RECOMMENDED ONLY — NOT APPROVED**. This review does not name one.

## K. Explicit unresolved decisions

These remain unresolved because Wave 2B.6 is not defined. This review does not resolve them.

- What native fact, if any, is Wave 2B.6
- Whether `FORBIDDEN_TABLES` is ever lifted for CarePlan (architecture change, not a wave shortcut)
- Whether any deferred Procedure/Immunization fields ever become their own facts
- Table shape, lifecycle, coded fields, anonymous/encounter rules, permissions, and audit names for any future fact
- Whether Laboratory-style multi-table aggregates are ever allowed again (Laboratory was an explicit exception; CarePlan is not)

## L. Domain-approval pass (design only)

Performed against frozen Procedure `0a61ee67a7ab68f37f90dd1fa9e17f2d3e2ba8ad` / `wave-2b5-procedure-frozen` / Alembic `20260814_0014`. Chain `0001 → 0014` intact. `Wave1PolicyPDP` untouched. Production code, models, services, APIs, and migrations were not modified.

Approval bar used: only explicitly approved architecture/design material can authorize Wave 2B.6. An exclusion list, deny-by-default permission, `NOT STARTED` status, TODO, absent table, or historical name is not approval.

| Test | Result |
|---|---|
| Exactly one named native fact, unimplemented, and not forbidden | Fail — no such fact |
| CarePlan | Fail — `care_plans` in `FORBIDDEN_TABLES`; aggregate, not a single fact |
| Separate Diagnosis | Fail — `diagnoses` in `FORBIDDEN_TABLES`; Condition already owns the fact |
| FHIR / Consent-as-PDP / AI / RAG / CDS | Fail — architecture exclusions |
| Break-glass / portal / scheduling / inventory / registry | Fail — not approved |
| Deferred Procedure performer / site / reason | Fail — would redesign frozen Procedure |
| Unnamed later facts | Fail — inventing a domain is forbidden |

No implementation-ready contract exists (table, category, lifecycle, immutability, identity, encounter, anonymous/EMER, authz, purpose, audit, provenance, concurrency, API, or `0015`). Writing a fake approval document would invent architecture decisions.

## N. Domain discovery pass (design only)

Re-inspected modular-monolith, migrations, Wave 2A foundation, all `docs/clinical/wave2*` and `docs/gates/wave2*` documents, clinical module, catalog, `FORBIDDEN_TABLES`, deny-by-default stubs, models, services, lifecycle, schemas, repositories, `Wave1PolicyPDP`, and Alembic `0001`–`0014`. Searched for Wave 2B.6, roadmap, next domain, CarePlan, Diagnosis, forbidden, deny-by-default, and out-of-scope.

No `roadmap` names a next clinical fact. Catalog has no `WAVE2B6_PERMISSIONS`. `clinical_governance` remains a Wave 0 shell (rules, not patient facts).

Classification key: **A** explicitly approved · **B** explicitly proposed but not approved · **C** out of scope · **D** forbidden · **E** historical/reference-only · **F** undefined / inferred.

| Candidate | Evidence | Class |
|---|---|---|
| Encounter, Clinical Note, Condition, Observation, Laboratory, Medication, Allergy, Consent, Immunization, Procedure | Implemented and frozen through `0014` | **A** (already shipped; not 2B.6) |
| CarePlan | `care_plans` in `FORBIDDEN_TABLES`; `clinical.care_plan.create` deny-by-default; freeze docs “do not start” | **D** |
| Separate Diagnosis | `diagnoses` in `FORBIDDEN_TABLES`; `clinical.diagnosis.create` deny-by-default; Condition owns diagnosis | **D** |
| Imaging, treatments, prescriptions, vital signs, clinical timeline | `FORBIDDEN_TABLES` | **D** |
| FHIR resources / `/fhir/` / `/api/v2/` | Forbidden tables + modular-monolith | **D** |
| Consent-as-PDP / `Wave1PolicyPDP` rewrite | Consent freeze: fact, not a grant | **D** |
| AI / RAG / CDS | Explicit architecture exclusions | **D** |
| Break-glass / patient portal | Explicit out-of-scope | **C** / **D** |
| Scheduling / forecast / inventory / registry | Immunization and Procedure out-of-scope lists | **C** |
| Documents | Wave 2A out-of-scope list only; README forbids real clinical documents in-repo; no table, lifecycle, or permissions | **E** — not a contract |
| `clinical_governance` | Wave 0 placeholder; no patient-fact tables | **E** |
| Procedure performer / site / reason | Deferred on frozen Procedure | Would redesign **A**; not a new wave |
| Family history, device/implant, adverse event, coverage, goal | Absent from catalog, models, migrations, clinical docs | **F** |

**Implementation-ready count:** 0.

Wave 2A listed diagnosis, condition, observation, laboratory, medication, allergy, immunization, procedure, care plan, consent, FHIR, AI, timeline, and documents as out of scope. Every legitimate native fact on that list that was **not** forbidden has already been implemented. Remaining names are forbidden, out of scope, historical, or undefined. None is implementation-ready. Multiple inferred names exist; choosing one would invent a domain. Decision rule: if none, or if multiple undefined inferences, Wave 2B.6 stays **NOT DEFINED**.

A later domain-approval pass may approve a domain only if it:

1. Names one native documented fact
2. Proves it is not in `FORBIDDEN_TABLES` unless architecture is explicitly changed first
3. Proves it is not a FHIR resource, CarePlan aggregate, or frozen-domain redesign
4. Freezes identity, encounter, lifecycle, immutability, authz, purpose, audit, provenance, API, and migration (`0015` additive only, design then implementation)
5. Leaves `Wave1PolicyPDP` untouched

Until that evidence exists, implementation is forbidden.

## O. Medical Device architecture review (this pass)

Explicit product/architecture selection named **Native Medical Device**. Discovery class **F** is no longer the end state: this pass tests whether the frozen architecture can support that named fact.

| Question | Result |
|---|---|
| Single native clinical fact? | Yes — patient has/uses/is associated with a coded device |
| One-native-fact-per-wave (Immunization/Procedure)? | Yes — one table `medical_devices` |
| New aggregate family? | No |
| Scheduling or inventory? | No — those remain out of scope |
| FHIR semantics? | No — not FHIR Device; no `/fhir/` or `/api/v2/` |
| Consent-as-PDP? | No |
| AI/RAG/CDS? | No |
| Reuse MPI identity rules? | Yes |
| Optional encounter? | Yes — Immunization/Procedure convention |
| Reuse provenance, purpose, audit, RBAC, FOR UPDATE, immutability? | Yes |
| Redesign frozen domains? | No |
| Forbidden-table conflict? | None — `medical_devices` is not in `FORBIDDEN_TABLES` |

Distinctions frozen by this pass:

- pacemaker association → Medical Device
- pacemaker implantation → existing Procedure
- heart rate / BP / SpO2 → existing Observation
- warehouse stock → out of scope

Lifecycle: record `ACTIVE` → `AMENDED` / `ENTERED_IN_ERROR`. Association `IN_USE` \| `NO_LONGER_USED` is an amendable field (Allergy analog), not Medication `STOPPED`, not FHIR Device.status, not inventory retirement.

## P. Candidate comparison (this pass)

| Candidate | Classification |
|---|---|
| Native Medical Device | **Candidate — approved for design** |
| Patient History | Out of scope this wave; undefined as a native fact |
| Adverse Event | Out of scope this wave; undefined as a native fact |
| CarePlan | Forbidden (`care_plans`) |
| Separate Diagnosis | Forbidden (`diagnoses`); Condition already owns it |
| Vital Signs | Already covered by Observation; not a new domain |

## Q. Final decision

**WAVE 2B.6 = APPROVED FOR MEDICAL DEVICE**  
**DESIGN ONLY**

CarePlan is not approved. Diagnosis is not approved. Documents is not approved. Patient History is not approved. Adverse Event is not approved. Vital Signs is not a new domain. Production code is untouched.

WAVE 2B.5 PROCEDURE = FROZEN  
WAVE 2B.5 PROCEDURE = PUBLISHED  
WAVE 2B.6 MEDICAL DEVICE = APPROVED FOR DESIGN ONLY  
WAVE 2B.6 MEDICAL DEVICE = NOT STARTED (implementation)

NO CODE  
NO MIGRATION  
NO API  
NO COMMIT  
NO TAG  
NO PUSH
