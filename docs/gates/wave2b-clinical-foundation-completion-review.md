# Wave 2B — Clinical foundation completion review

**Date:** 2026-08-26  
**Kind:** Architecture review only  
**Baseline:** `wave-2b8-family-history-frozen` / `9a56c0893f8638c1a66d854ca61f137a6177ebf4`  
**Alembic:** `current == heads == 20260814_0017`  
**Decision:** WAVE 2B CLINICAL FOUNDATION = COMPLETE  
**WAVE 2B.9:** NOT REQUIRED

This is not an implementation gate. This is not a HIPAA, ISO 27001, or SOC 2 certification. No production code, migration `0018`, API, commit, tag, or push is authorized.

Companion canvas: [wave2b-clinical-foundation-completion-review.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/wave2b-clinical-foundation-completion-review.canvas.tsx)

Classification key used in this review:

- **A** already represented
- **B** real missing native clinical fact
- **C** workflow / capability, not a clinical fact
- **D** aggregate / read model
- **E** explicitly deferred
- **F** forbidden / out of scope
- **G** undefined

`NOT STARTED`, deny-by-default permission stubs, `FORBIDDEN_TABLES`, and old comments are **not** approval.

## 1. Frozen baseline

Verified before this review.

| Item | Live value |
|---|---|
| Repository | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Branch | `main` == `origin/main` |
| HEAD | `9a56c0893f8638c1a66d854ca61f137a6177ebf4` |
| Tag | Annotated `wave-2b8-family-history-frozen` → same SHA |
| Parent | `8d455b3dede07b9ada00205ff6c49b41b97a0895` (`wave-2b7-adverse-event-frozen`) |
| Working tree at inspection | CLEAN |
| Alembic | `current == heads == 20260814_0017` (exactly one head) |
| Chain | `0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011 → 0012 → 0013 → 0014 → 0015 → 0016 → 0017` |
| Migration `0018` | Does not exist |
| `Wave1PolicyPDP` | Untouched (last production change remains Wave 2A freeze `f051e39`) |
| Migrations `0001`–`0017` | Intact; this pass changes none |

`docker-compose.yml` is not modified. Frozen domains are not redesigned.

## 2. Frozen domain inventory

Native clinical facts, in freeze order. None may be redesigned as Wave 2B.9.

| Domain | Wave | Table(s) | API under `/api/v1/clinical` | Lifecycle | Permissions | Provenance | Audit | Freeze |
|---|---|---|---|---|---|---|---|---|
| Encounter | 2A | `encounters`, `encounter_participants` | POST/GET `/encounters`, GET `{id}`, POST `{id}/status` | Class-specific open + status; EIE terminal | `clinical.encounter.create\|read\|update_status` | `ENCOUNTER` | `ENCOUNTER_*` | `wave-2a-frozen` |
| Clinical Note | 2A | `clinical_notes` | POST `/notes`, GET `{id}`, POST `{id}`, `{id}/finalize`, `{id}/entered-in-error` | DRAFT → FINAL / EIE | `clinical.note.create\|read\|update_draft\|finalize` | `CLINICAL_NOTE` | `CLINICAL_NOTE_*` | `wave-2a-frozen` |
| Condition | 2B.1 | `conditions` | POST/GET `/conditions`, GET `{id}`, POST `{id}/status`, `{id}/entered-in-error` | Clinical + verification; EIE terminal | `clinical.condition.*` | `CONDITION` | `CONDITION_*` | `wave-2b1-condition-frozen` |
| Observation | 2B.2a | `observations` | POST/GET `/observations`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | FINAL → AMENDED / EIE | `clinical.observation.*` | `OBSERVATION` | `OBSERVATION_*` | `wave-2b2a-observation-frozen` |
| Laboratory | 2B.2b | `laboratory_orders`, `laboratory_specimens`, `laboratory_results` | `/laboratory/orders\|specimens\|results` plus cancel/amend/EIE | Three coordinated lifecycles | `clinical.laboratory.{order,specimen,result}.*` | `LABORATORY_*` | `LAB_*` | `wave-2b2b-laboratory-frozen` |
| Medication | 2B.3a | `medications` | POST/GET `/medications`, GET `{id}`, POST `{id}/stop`, `{id}/entered-in-error` | ACTIVE → STOPPED / EIE | `clinical.medication.*` | `MEDICATION` | `MEDICATION_*` | `wave-2b3a-medication-frozen` |
| Allergy | 2B.3b | `allergies` | POST/GET `/allergies`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.allergy.*` | `ALLERGY` | `ALLERGY_*` | `wave-2b3b-allergy-frozen` |
| Consent | 2B.3c | `consents` | POST/GET `/consents`, GET `{id}`, POST `{id}/amend`, `{id}/revoke`, `{id}/entered-in-error` | ACTIVE → AMENDED / REVOKED / EIE | `clinical.consent.*` | `CONSENT` | `CONSENT_*` | `wave-2b3c-consent-frozen` |
| Immunization | 2B.4 | `immunizations` | POST/GET `/immunizations`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.immunization.*` | `IMMUNIZATION` | `IMMUNIZATION_*` | `wave-2b4-immunization-frozen` |
| Procedure | 2B.5 | `procedures` | POST/GET `/procedures`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.procedure.*` | `PROCEDURE` | `PROCEDURE_*` | `wave-2b5-procedure-frozen` |
| Medical Device | 2B.6 | `medical_devices` | POST/GET `/medical-devices`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.medical_device.*` | `MEDICAL_DEVICE` | `MEDICAL_DEVICE_*` | `wave-2b6-medical-device-frozen` |
| Adverse Event | 2B.7 | `adverse_events` | POST/GET `/adverse-events`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.adverse_event.*` | `ADVERSE_EVENT` | `ADVERSE_EVENT_*` | `wave-2b7-adverse-event-frozen` |
| Family History | 2B.8 | `family_histories` | POST/GET `/family-histories`, GET `{id}`, POST `{id}/amend`, `{id}/entered-in-error` | ACTIVE → AMENDED / EIE | `clinical.family_history.*` | `FAMILY_HISTORY` | `FAMILY_HISTORY_*` | `wave-2b8-family-history-frozen` |

All thirteen facts bind `patient_identities.id`. Encounter is optional on later facts (required for notes). Clinical writes do not mutate Encounter. Catalog ends at `WAVE2B8_PERMISSIONS`. Clinical module registration ends at Wave 2B.8 Family History.

### Supporting foundation (frozen, not redesigned)

| Layer | Owner | Role |
|---|---|---|
| MPI / Patient Identity | `mpi` | Canonical `patient_identities.id`; ACTIVE / MERGED / RETIRED / anonymous + EMER |
| Organization / Facility | `organization` | Org-scoped writes; facility membership |
| IAM | `iam` | Users, memberships, JWT |
| RBAC | `authorization` catalog + `Wave1PolicyPDP` | Permission codes; unknown actions deny-by-default |
| Purpose | `X-Purpose` | Required, normalized, catalog-validated; does not grant access |
| Audit | `audit_events` | Insert-only success events; safe metadata |
| Provenance | `clinical_provenances` | Insert-only; `ON DELETE RESTRICT`; service always sets `provenance_id` |
| Concurrency | PostgreSQL `SELECT FOR UPDATE` | Redis is not the clinical lock |
| Immutability | History triggers + `app_dml` grants | DELETE/TRUNCATE denied; immutable columns frozen after create |

## 3. Clinical coverage matrix

What a minimal production chart can already represent, and which frozen domain owns it.

| Clinical concept | Owner | How |
|---|---|---|
| Encounter context | Encounter | Class, status, patient, org/facility |
| Clinical narrative | Clinical Note | DRAFT/FINAL/EIE body text on an encounter |
| Diagnosis / problem list | Condition | Problem-list and encounter diagnosis; `diagnoses` table is forbidden |
| Vital signs | Observation | Category `VITAL_SIGNS`; `vital_signs` table is forbidden |
| Other measurements / findings | Observation | Coded observation fact |
| Laboratory | Laboratory | Order + specimen + result |
| Medication | Medication | Documented prescribed/reported medication fact; stop / EIE |
| Allergy / intolerance | Allergy | Documented allergy fact |
| Immunization | Immunization | Documented vaccination fact |
| Procedure | Procedure | Documented performed/reported procedure |
| Medical devices / implants | Medical Device | Patient–device association |
| Adverse events | Adverse Event | Documented coded harm event; optional related med/device/procedure |
| Family history | Family History | Relationship + coded finding |
| Permit / refuse documentation | Consent | Documented consent fact; **not** a PDP |

Do not propose duplicate domains for any row above.

## 4. Search for true clinical gaps

Searched: `WAVE 2B.9`, `wave2b9`, `NOT STARTED`, `FORBIDDEN_TABLES`, deny-by-default stubs (`clinical.care_plan.create`, `clinical.diagnosis.create`), architecture docs, freeze documents, clinical module registration, authorization catalog, Alembic heads, README, file-security “Documents wave”, Patient History, CarePlan, Diagnosis, Vital Signs, Imaging, Prescription, Treatment, Coverage, Goal.

| Concept | Class | Why |
|---|---|---|
| Encounter through Family History (13 facts) | **A** | Frozen and published |
| Diagnosis | **A** | Condition |
| Vital signs | **A** | Observation `VITAL_SIGNS` |
| Laboratory / Medication / Allergy / Immunization / Procedure / Devices / Adverse Event / Family History / Narrative / Encounter | **A** | Frozen owners |
| Appointment, scheduling, queue, follow-up | **C** | Care-access operations |
| Prescription workflow, pharmacy dispense, medication reminder | **C** | Medication fact already exists; workflow is later |
| Inpatient / bed / ambulance / emergency dispatch | **C** | Emergency operations |
| Patient portal, mobile medical record, notifications | **C** / **D** | Experience + read model |
| Subscription, billing, tenant plans, AI quotas | **C** | Platform SaaS |
| AI / RAG / CDS / AI Gateway | **C** / **F** | Explicit architecture exclusion until a later gate |
| Patient History / clinical timeline / summary / dashboard | **D** | Projection of frozen facts; `patient_histories` and `clinical_timelines` are absence probes / forbidden |
| CarePlan | **F** | `care_plans` forbidden; stub is not a backlog |
| Separate Diagnosis table | **F** | `diagnoses` forbidden |
| Vital Signs table | **F** | `vital_signs` forbidden |
| Prescriptions / treatments / imaging_studies | **F** | `FORBIDDEN_TABLES` |
| FHIR / `/fhir/` / `/api/v2/` | **F** | Forbidden architecture |
| Consent-as-PDP / `Wave1PolicyPDP` rewrite | **F** | Forbidden |
| Adverse Event causality / outcome / `LIFE_THREATENING` | **E** | Deferred on **frozen** AE; not a new domain |
| Medical Device UDI / serial / manufacturer / lot | **E** | Deferred on **frozen** Device |
| Procedure performer / site / reason / outcome | **E** | Deferred on **frozen** Procedure |
| Family History relative identity / deceased / age-at-onset | **E** | Deferred on **frozen** Family History |
| Documents / attachments | **E** / **G** | File-security “Documents wave” sentence; no fact contract |
| Coverage / goal | **G** | Named only as prior-review inferences |
| `clinical_governance` | **E** | Wave 0 rules shell, not a patient fact |

**Class B count (real missing native clinical fact required for a minimal production record):** 0.

Wave 2A’s original later-clinical list that was **not** forbidden has been implemented: condition, observation, laboratory, medication, allergy, immunization, procedure, consent, plus Medical Device, Adverse Event, and Family History. Remaining names are owned, forbidden, workflow, aggregate, deferred columns on frozen domains, or undefined without a contract.

## 5. Workflow versus fact

These are **not** native clinical facts and must not be invented as Wave 2B.9 tables:

| Name | Classification |
|---|---|
| Appointment / doctor scheduling / queue / follow-up | **C** Care Access / Operations |
| Medication reminder | **C** Patient Experience on top of Medication |
| Prescription workflow / pharmacy dispense | **C** Pharmacy workflow; Medication is the source fact |
| Inpatient workflow / bed management | **C** Operations |
| Ambulance / emergency dispatch / emergency requests | **C** Emergency operations |
| Patient portal / Patient Medical Record timeline | **C** / **D** Experience + read model |
| Subscription / billing / entitlements / metering | **C** Platform SaaS |
| AI / AI Gateway / CDS | **C** / **F** Later gated capability |
| Hospital Web / Platform Admin Web / Patient Mobile / i18n | **C** Frontend / Experience |

## 6. Patient History decision

Patient History remains a **read model / timeline / presentation**. It is **not** a `patient_histories` table.

Existing frozen facts are sufficient to construct a longitudinal patient history later:

- Encounter frames episodes
- Condition, Observation, Laboratory, Medication, Allergy, Immunization, Procedure, Medical Device, Adverse Event, and Family History are the documented facts
- Clinical Note is the narrative
- Consent is the documented permit/refuse record
- MPI identity is the patient key
- Provenance and audit exist per fact

A later Patient History API would project these rows. It would not create a new clinical fact. `patient_histories` in freeze tests remains an absence probe, not a backlog.

## 7. Clinical Note assessment

Clinical Note is adequate narrative capture for closing Wave 2B.

- Bound to a documentable encounter and patient
- DRAFT → FINAL / ENTERED_IN_ERROR
- Provenance and audit exist
- It is not FHIR DocumentReference

It does not need redesign to leave the Wave 2B clinical-fact phase.

Later presentation may want list-by-patient (notes are currently GET-by-id). That is a read-model / API convenience, not a missing native fact, and does not block Wave 2B closure.

## 8. Workflow readiness (source of truth only)

The question is whether the **clinical source of truth** can support later capabilities. None of these are implemented here.

| Later capability | Clinical foundation adequate? | Why |
|---|---|---|
| Patient mobile medical record | Yes, as a later read model | Frozen facts + identity exist; UI/auth/notifications do not |
| Clinician / hospital web workspace | Yes, as a later application | `/api/v1/clinical` fact APIs exist |
| Appointment / follow-up | Clinical facts yes; scheduling no | Needs an operations domain, not another chart fact |
| Medication education / reminders | Medication fact yes; messaging no | Needs notification/experience |
| Pharmacy workflow | Medication fact yes; dispense/eRx no | Needs pharmacy workflow |
| AI clinical decision support | Facts can be inputs later | AI/RAG/CDS remain out of scope until a dedicated gate |
| Emergency / ambulance workflow | EMER encounter + anonymous identity exist | Dispatch/ops are not clinical facts |

The foundation is **adequate to support those later**. It does not implement them.

## 9. Database / API foundation

| Check | Result |
|---|---|
| Alembic | Single head `20260814_0017` |
| Chain | `0001` → `0017` intact |
| Clinical FKs | `patient_identities`, optional `encounters`, org/facility, provenance `ON DELETE RESTRICT` |
| Provenance | `FAMILY_HISTORY` included; insert-only; service-set `provenance_id` |
| Audit | Domain-specific created/amended/EIE (and encounter/note/consent variants) |
| Immutability | History triggers on clinical fact tables |
| Concurrency | `SELECT FOR UPDATE` on mutations |
| Permission catalog | Ends at `WAVE2B8_PERMISSIONS`; `Wave1PolicyPDP` untouched |
| API boundary | `/api/v1/clinical` only; PUT/PATCH/DELETE 405 on fact routes; no `/api/v2/`; no `/fhir/` |

No destructive migration was run.

## 10. Inherited risks

No P0 or P1 blocks closing Wave 2B. Independently confirmed still present:

| Sev | Finding | Blocks Wave 2B close? |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | No |
| P2 | Historical `patient_identity_id` is not rewritten after MPI merge | No (by design) |
| P2 | Same-org UUID read remains org-scoped until a later PDP wave | No |
| P3 | `app_dml` grants live in `grant_dev_privileges.sql` | No |
| P3 | `provenance_id` nullable (FK present; service always sets it) | No |
| P3 | Duplicate clinical facts are allowed | No |
| P3 | Deferred columns on frozen AE / Device / Procedure / Family History | No |
| P3 | Test `rate_limit_per_minute` 10000; production 120 | No |
| P3 | Docker `:9100` image lags published routes | No |

These are not redesigned in this pass.

## 11. Decision

Selection rule applied:

- Missing P0/P1-level native clinical foundation fact? **No.**
- Exactly one genuinely essential missing native clinical fact with strong repository evidence? **No.** Class **B** count is 0.
- Remaining unimplemented names? Forbidden, workflow, aggregate, deferred frozen-domain columns, or undefined without a contract.

Therefore:

**WAVE 2B CLINICAL FOUNDATION = COMPLETE**

**WAVE 2B.9 = NOT REQUIRED**

Do not invent another clinical domain. Do not create migration `0018`. Do not start CarePlan, Diagnosis, Vital Signs table, Patient History table, FHIR, or AI.

Family History was the last native documented fact that fit the frozen one-row pattern without colliding with `FORBIDDEN_TABLES` or an existing owner. After `wave-2b8-family-history-frozen`, the Wave 2B clinical-fact phase has no remaining essential chart fact.

## 12. Next macro-phase candidates (not selected)

Wave 2B can close. Later work is **capability families**, not Wave 2B.9 clinical facts. This review does **not** choose a next phase.

| Family | Examples | Depends on Wave 2B facts? |
|---|---|---|
| A. Patient Experience | Mobile app, medical-record read model, notifications, medication reminders | Yes (read/project) |
| B. Care Access / Operations | Appointment, follow-up, physician scheduling, queue | Encounter + identity; new ops domain |
| C. Pharmacy / Medication Workflow | Prescribing workflow, dispense, instructions | Medication fact |
| D. Emergency | Emergency requests, ambulance dispatch | EMER encounter + anonymous identity |
| E. Clinical AI | Diagnostic/medication CDS, AI audit/governance | Facts as inputs; requires a dedicated AI gate |
| F. Platform SaaS | Tenant plans, subscriptions, entitlements, AI quotas, metering, billing | Platform, not clinical |
| G. Frontend / Experience | Hospital Web, Platform Admin Web, Patient Mobile, ID/EN/ZH | Clients on `/api/v1` |

Do not start any of these in this pass.

## 13. Files

Review artifacts only:

- `docs/gates/wave2b-clinical-foundation-completion-review.md` (this file)
- companion canvas outside git: `wave2b-clinical-foundation-completion-review.canvas.tsx`

## 14. Production code status

Untouched. No changes to `backend/app`, `backend/alembic`, `backend/tests`, authorization catalog, services, repositories, schemas, routes, lifecycle, models, or grants.

NO CODE  
NO MIGRATION 0018  
NO API CHANGE  
NO COMMIT  
NO TAG  
NO PUSH

WAVE 2B CLINICAL FOUNDATION = COMPLETE  
WAVE 2B.9 = NOT REQUIRED
