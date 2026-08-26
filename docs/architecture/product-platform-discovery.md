# Product platform architecture discovery

**Date:** 2026-08-26  
**Kind:** Architecture discovery only  
**Baseline:** `wave-2b-clinical-foundation-complete` / `b1606fe38dfaf4ee24d95775c07e77cb842c3736`  
**Alembic:** `current == heads == 20260814_0017`  
**Status:** NOT an implementation approval

The Wave 2B native clinical foundation is **closed**. This document describes the macro product architecture that can sit on top of it. It does not authorize production code, migration `0018`, frontends, AI integration, subscription tables, commit, tag, or push.

Companion gate: `docs/gates/product-platform-architecture-discovery.md`.

Follow-on design (not implemented): `docs/architecture/product-access-tenancy-foundation-design.md` and `docs/gates/product-access-tenancy-foundation-design-approval.md`.

## 1. Product vision

The intended product is a **healthcare SaaS platform** with **one shared modular-monolith backend** and **three client applications**:

| Client | Actor | Commercial posture |
|---|---|---|
| Platform Admin Web | SaaS / platform operator | Internal operator tool |
| Healthcare Web Platform | Hospital and clinic staff | B2B subscription |
| Patient Mobile Application | Patient | Free |

Do not split Healthcare Web into Doctor Web, Nurse Web, Clinic Web, and Hospital Web unless a later contract proves that one app cannot isolate workspaces by tenant, facility, role, permission, resource, and purpose. UI visibility must never substitute backend authorization.

Patient usage remains free. Healthcare organizations pay. Exact prices, payment providers, and platform margin are **out of this discovery**.

## 2. Shared backend direction

**Recommendation:** keep the existing FastAPI modular monolith as the shared platform API for all three clients. Do **not** introduce three backends.

Current modules under `backend/app/modules/`:

| Module | Today | Future evolution |
|---|---|---|
| `clinical` | Frozen native facts (Encounter → Family History) | Clinical core. Do not redesign facts. Add only later *read-model* adapters, not duplicate domains. |
| `iam` | Staff users, memberships, JWT `sub` mapping | Staff IAM plus a future **patient principal** (new contract). |
| `authorization` | `Wave1PolicyPDP`, permission catalog, purpose | Remain deny-by-default. Add patient and entitlement *callers*; do not merge entitlement into the PDP. |
| `organization` | Org + facility + identifiers | Tenant candidate. Hierarchy / group contract is missing. |
| `mpi` | Platform person identity | Remains identity. Patient app binds to it; it is not a chart. |
| `audit` | Insert-only success-oriented events | Keep. Add AI/clinical-decision audit separately from cost telemetry. |
| `clinical_governance` | Shell only | Rules, not patient facts. Not an AI Gateway. |

Future modules (new bounded contexts, same process, `/api/v1/...` adapters):

- `scheduling` — appointments, slots, follow-up requests
- `notifications` — orchestration, preferences, delivery
- `pharmacy_workflow` — prescribe / verify / dispense (not a second Medication fact)
- `emergency` — request, dispatch, ambulance ops (not Medical Device)
- `saas` — plans, subscriptions, entitlements
- `billing` — invoices, payments (provider-agnostic ports)
- `ai_gateway` — routing, policy, adapters, usage
- `patient_access` — patient principal APIs and medical-record projection

Architecture v2.1 constraints remain: no microservices, Kafka, Kubernetes, vector database, PACS, or blockchain without a later gate. FHIR adapters must not become the internal model. Domain logic must not import FastAPI.

## 3. Multi-tenancy

### What exists

| Concept | Current representation | Tenant? |
|---|---|---|
| Organization | `organizations` with types `HOSPITAL`, `CLINIC`, `LABORATORY`, `PHARMACY`, `NETWORK`, `OTHER` | **Candidate**, not a SaaS tenant object |
| Facility | `facilities` owned by one organization (`organization_id`, unique `code` per org) | Site / location, not a tenant |
| Hierarchy | None. No `parent_organization_id`. `NETWORK` is a type label only | Missing |
| Staff membership | `organization_memberships` (user, optional org, optional facility, role) | Isolation key for staff |
| Isolation header | `X-Organization-Id` required on org-scoped APIs | Exists |
| Clinical facts | Every clinical table has `organization_id` | Org-attributed source of truth |
| MPI identity | Platform-wide person UUID; identifiers may carry `organization_id` (e.g. MRN) | Identity is not org-owned; **clinical data is** |
| Platform operator | `PLATFORM_ADMIN` + `iam.platform` | Bypasses org scope in the PDP today |

`docs/organization/organization-model.md`: an organization is a healthcare institution or owning body, not hardcoded as hospital. A user is not implicitly authorized for every organization.

### Can organization act as tenant?

**Yes, as the default tenant grain**, if a later contract states:

1. One billing/subscription customer = one `organizations.id` (clinic or hospital), **or**
2. An enterprise/hospital group is an explicit parent tenant that owns child organizations.

Option 1 is sufficient for MVP. Option 2 needs a **new domain design** (`NETWORK` / parent graph, delegated admin, shared vs isolated charts). Do not imply hierarchy from the `NETWORK` enum alone.

Hospital vs clinic is already a **classification** (`organization_type`). It is not a reason to build two Healthcare Web applications. Entitlements may later differ (ambulance, inpatient ops) without splitting the client.

### Isolation rules (must remain)

- Hospital A must never gain unauthorized access to Hospital B.
- Clinic A must never gain unauthorized access to Clinic B.
- Staff same-org UUID read (inherited P2) remains org-scoped until a later PDP wave.
- Patient-centric cross-org *self* access is a **different** authorization problem from staff cross-org access. It needs its own contract. It must not weaken staff isolation.

### What requires a new contract

- Organization-as-tenant (subscription FK, entitlement FK, status vs org `ACTIVE`/`INACTIVE`)
- Hospital group / multi-org admin
- Platform operator **without** default clinical access
- Patient principal and patient access across organizations
- Cross-organization staff care-coordination (purpose `CARE_COORDINATION` exists for **identity only** today)

## 4. Platform Admin vs Healthcare Admin

| | Platform Admin | Hospital / Clinic Administrator |
|---|---|---|
| Role today | `PLATFORM_ADMIN` | `ORG_ADMIN` |
| Intent | Operate the SaaS | Administer one tenant |
| Should manage | Organizations as customers, operator users, plans, subscriptions, entitlements, AI providers/routing, system health, platform audit, support | Tenant users, memberships, facilities, identifiers, local configuration |
| Should not (future rule) | Freely browse or write patient clinical facts because they “own the platform” | Manage other tenants, billing of the platform, AI provider credentials |

### Least-privilege finding (existing architecture)

Today `ROLE_PERMISSIONS[PLATFORM_ADMIN] = CATALOG_PERMISSIONS` (all IAM, org, MPI, and **all clinical** permissions). `Wave1PolicyPDP` grants any catalog action when `iam.platform` is in scopes (`policy_reference = pdp.wave1.platform_scope`) **without organization isolation**.

That was acceptable for a staff-only clinical foundation freeze. It is **not** acceptable as the operator model for Platform Admin Web.

**Required future principle:** platform operators default to platform permissions only. Clinical access, if ever required, is a separate break-glass path (`emergency_access_id` already exists on `AuthorizationContext` and is unused). This is **READY FOR DESIGN**, not a silent PDP rewrite in this pass.

`ORG_ADMIN` already has tenant-scoped membership/facility management plus **clinical read**. Whether hospital administrators should read the full chart is a product policy; they must remain org-scoped either way.

## 5. Three-client boundaries

### A. Platform Admin Web

Operator console. Not the hospital administration workspace.

Future surfaces: organizations/tenants, facilities only as support views, users, plans, subscriptions, entitlements, billing/invoices, AI quota/usage/cost/providers/routing, system health, platform audit, configuration.

Must call `/api/v1/platform/...` (or equivalent operator prefix) after that module exists. Must not reuse clinician write APIs as a convenience.

### B. Healthcare Web Platform

One web app for hospitals and clinics. Workspaces (doctor, nurse, registration, pharmacy, laboratory, emergency dispatcher, tenant admin, management) are **views** gated by permission and facility, not separate deployables.

Roles today: `CLINICIAN`, `REGISTRAR`, `IDENTITY_OFFICER`, `AUDITOR`, `ORG_ADMIN`. Missing for later workspaces: nurse vs doctor split (optional; permission bundles can suffice), pharmacist, dispatcher, lab technician. Do not invent those roles in this pass.

### C. Patient Mobile Application

Free patient-facing client. There is **no patient user**, no `PATIENT` role, and `authorize.py` hardcodes `PrincipalType.STAFF`. `PrincipalType.PATIENT`, purpose `PATIENT_ACCESS`, and `DisclosureCategory.PATIENT_VISIBLE` exist as unused hooks.

Patient capabilities (profile, record, reminders, appointments, emergency request, language) are **future**. None are implemented.

### Repository recommendation

Current repo is a backend modular monolith with **no frontend**. Expected team size is small.

**Recommendation:** keep a **monorepo**. Add later (not now):

- `apps/platform-admin-web`
- `apps/healthcare-web`
- `apps/patient-mobile`
- `packages/api-client` (generated from OpenAPI `/api/v1`)
- `packages/i18n`
- optional `packages/ui` design tokens

One generated API client; three auth flows (operator, staff, patient). Do not share refresh tokens across those principals. Separate mobile repo only if a later native-app team requires it.

## 6. SaaS / subscription model

B2B: healthcare organization subscribes. B2C patient access is free and is **not** a tenant subscription.

Conceptual entities (do not create tables in this pass):

| Entity | Role |
|---|---|
| Plan | Catalog of entitlements and included limits (users, AI allowance, modules) |
| Subscription | Binding of a tenant organization to a plan, with period and status |
| Entitlement | Feature flag or limit granted by the plan (and optional overrides) |
| Invoice / Payment | Commercial artifacts behind a billing **port** |
| Usage / quota | Metered consumption, especially AI |

Subscription statuses to design later: `trial`, `active`, `past_due`, `suspended`, `cancelled`. Suspended must deny **entitled capabilities**, not destroy clinical facts.

Do not choose prices. Do not hardcode a payment provider. Billing adapters must be ports. Webhook authenticity is a future security requirement.

Clinic / hospital / enterprise group may map to plan tiers later. Classification (`organization_type`) is not the subscription.

## 7. Feature entitlement vs authorization

Scattered `if plan == "PRO"` is forbidden.

Conceptual chain:

```
Organization (tenant)
    → Subscription
        → Plan
            → Entitlements
                → Feature / Limit
```

| Question | Authority |
|---|---|
| May this user perform this action? | PDP / permission (`clinical.medication.create`, …) |
| Has this tenant purchased/enabled this capability? | Entitlement service |
| Why is this access happening? | `X-Purpose` (context, never a grant) |
| Did the patient permit this use? | Consent fact (not a PDP) |

Both permission **and** entitlement must pass for an entitled capability (e.g. Clinical AI). A clinician in a tenant without AI entitlement is denied even if they have clinical write permission. A platform billing admin must not gain clinical write because a tenant bought AI.

## 8. AI Gateway (future)

Clinical AI is **not** part of Wave 2B. Direct `application → hardcoded GPT` is forbidden.

Target shape:

```
application
    → AI Gateway
        → policy / router (purpose, tenant entitlement, quota, redaction)
            → provider adapter
                → OpenAI | Anthropic | future
```

Core clinical services must not import provider SDKs or model names. The gateway records provider, model, and **versions**. Fallback and provider failure are gateway concerns.

## 9. AI use cases and safety principle

| Audience | Examples | Decision authority |
|---|---|---|
| Clinician | Summarization, differential assistance, medication safety review | Clinician |
| Patient | Medication education, plain-language explanation | Informational only; not a prescription |
| Platform | Routing, quota, cost accounting | Not clinical |

Required chain:

```
AI recommendation → clinician review → final clinical decision
```

Forbidden: AI → autonomous final diagnosis or prescription. Condition remains the diagnosis owner. Medication remains the clinical fact; AI may suggest, not write, without clinician action.

## 10. AI governance and economics

Future AI audit (clinical/safety), separate from billing telemetry:

- provider / model / model version
- prompt/template version
- purpose
- input provenance (which facts, not raw dumps of unnecessary PHI)
- output provenance
- clinician accept / modify / reject
- latency, token usage, estimated cost
- redaction / minimum necessary
- retention and patient privacy

PHI must not be copied into billing analytics. Cost tables may store tenant_id, provider, model, tokens, estimated cost — not notes, NIK, or result values.

Economics: subscription + included AI allowance + metering + optional overage/top-up. Conceptual: `ai_usage`, `ai_quota`, `ai_budget`, `ai_cost`, `provider_usage`, `model_usage`. Do not create them now. Do not promise a fixed platform margin.

The platform must later answer: which tenant, which provider/model, cost, remaining quota, projected monthly usage.

## 11. Patient journey

| Step | Classification | Owner today / later |
|---|---|---|
| Registration / identity | Exists | MPI |
| Appointment | Workflow | Future `scheduling` |
| Arrival / check-in | Workflow | Future care-access; QR is optional UX |
| Queue | Workflow | Future operations |
| Clinical encounter | Native fact | Encounter (`AMB`/`IMP`/`EMER`/…) |
| Doctor assessment | Narrative + facts | Clinical Note + Observation |
| Diagnosis | Native fact | Condition (`ENCOUNTER_DIAGNOSIS` / problem list) |
| Medication / treatment | Native fact | Medication (prescribed/reported). Treatment *workflow* undefined |
| Pharmacy | Workflow | Future; do not duplicate Medication |
| Patient education | Experience + i18n | Future; may use coded Medication |
| Medication reminder | Notification + schedule | Future; not a Medication column dump |
| Follow-up | Workflow | Future scheduling |
| Appointment again | Workflow | Scheduling |

Paperless / “inputless” means: do not re-ask what MPI, appointment, and frozen facts already hold. It does **not** mean skipping identity confirmation, allergy checks, or clinically required verification.

## 12. Appointment / scheduling

Scheduling is its **own macro capability**, not a Wave 2B clinical fact. Encounter `PLANNED` is not an appointment book.

Future needs: physician schedule, specialty, facility, slot, capacity/quota, book / reschedule / cancel, follow-up request, H-1 reminder, patient confirmation, availability.

Example flow (discovery only): clinician follow-up in N days → follow-up request → H-1 notify → patient confirms → show relevant specialists and slots → book.

Depends on: tenant/facility, staff directory (membership is not yet a clinical roster), notifications, patient principal. Does not mutate frozen Encounter as a calendar.

## 13. Medication reminder

Frozen Medication today: coded drug, `PRESCRIBED`/`REPORTED`, optional `dose_numeric`+`dose_unit`, optional `route`, `started_at` / `stopped_at`. **No** frequency, timing (morning/evening), duration, SIG, or reminder schedule.

| Concern | Belongs to |
|---|---|
| That the patient is on a coded drug | Frozen Medication |
| Prescribing workflow / pharmacist verify | Future pharmacy workflow |
| Patient-friendly purpose/benefit text | Education / i18n, keyed by code — not a second drug table |
| 2× daily morning+evening | Instruction / SIG object (new contract) |
| Fire reminder at 07:00 | Reminder schedule + notification platform |

Do **not** force reminder fields onto frozen Medication without a new approved contract. Do not treat Medical Device as a reminder channel.

## 14. Notification platform

Common capability. Channels later: in-app, mobile push, email, then SMS. Events: medication reminder, follow-up, appointment change, lab result availability, ambulance status.

```
event → orchestration → patient preferences → language → channel → delivery
```

Preferences and language live with the patient principal, not in clinical rows. Delivery failures are operational, not clinical EIE.

## 15. Emergency / ambulance

Desired mobile flow: emergency → select hospital → location → request → dispatcher accept → ambulance dispatch → status → hospital handoff.

This is an **operations** domain. Encounter class `EMER` and anonymous MPI identities already support emergency *clinical documentation*. They are not dispatch.

Do not confuse Medical Device (patient–device association) with fleet/vehicle management. Do not implement location tracking or ambulance tables in this pass.

## 16. Pharmacy workflow

Medication is the frozen clinical fact (`PRESCRIBED` ≠ dispensed).

Future workflow objects (new contract): prescribing order, pharmacy queue, pharmacist verification, dispense, counseling handoff.

Prescription / Dispense are **workflow / order** objects, not a second Medication source of truth. Dispense may *reference* `medications.id`. Do not create `fhir_medication_request` or a parallel drug fact.

Laboratory already has a three-object pattern (order / specimen / result). Pharmacy should not copy that schema blindly; it needs its own design approval.

## 17. Patient medical record read model

Patient History remains a **projection**. No `patient_histories` table.

A future patient-facing API aggregates org-attributed facts for the authenticated patient principal:

Encounter, Clinical Note (disclosure-filtered), Condition, Observation, Laboratory, Medication, Allergy, Immunization, Procedure, Medical Device, Adverse Event, Family History.

Requirements for a later contract: chronology, filter by type/org/facility, pagination, organization attribution, privacy (`DisclosureCategory`, consent, legally restricted), patient-safe terminology display.

Staff Healthcare Web may use the same projection engine with **staff** PDP (org-scoped). Patient APIs use **patient** PDP (self only, potentially multi-org of self). Do not expose staff list endpoints to the mobile app.

## 18. Internationalization

Required languages: Indonesian, English, Simplified Chinese. Canonical clinical **codes do not change** with language.

```
clinical concept → stable code → localized display
```

Separate catalogs:

| Layer | Example |
|---|---|
| UI translation | Button labels, workspace names |
| System messages | API `code` stable; localized `message` at the edge |
| Notification templates | H-1 appointment copy |
| Patient education | “Take in the morning” |
| Clinical terminology display | Code `I10` display “Hipertensi” / “Hypertension” |

Do not blindly AI-translate coded clinical data. Do not store one language as the source-of-truth `display` that other locales overwrite.

## 19. API strategy

Continue **`/api/v1/`**. Do not create `/api/v2/`. Do not create `/fhir/`.

Existing: `/api/v1/health`, `/auth`, `/iam`, `/organizations`, `/mpi`, `/clinical`.

Recommended future prefixes (not approved merely by listing):

| Prefix | Module |
|---|---|
| `/api/v1/clinical` | Frozen facts (unchanged ownership) |
| `/api/v1/patient` | Patient principal + read model |
| `/api/v1/scheduling` | Appointments |
| `/api/v1/notifications` | Notification APIs |
| `/api/v1/platform` | Operator |
| `/api/v1/saas` or `/billing` | Subscription after design |
| `/api/v1/ai` | Gateway, never provider passthrough |
| `/api/v1/emergency` | Dispatch after design |
| `/api/v1/pharmacy` | Workflow after design |

Unknown routes stay 404. PUT/PATCH/DELETE on frozen clinical facts remain 405.

## 20. Security (future requirements)

| Surface | Requirement |
|---|---|
| Tenant isolation | Org scope for staff; no implicit all-tenant |
| Least privilege | Split operator vs clinician vs patient principals |
| Patient authorization | Bind account → `patient_identities.id`; no staff token reuse |
| Session/token | Separate issuers or audiences for operator / staff / patient |
| Audit | Keep insert-only; denial audit remains inherited P2 |
| Secrets | Provider and payment credentials not in git; not in clinical rows |
| Payment webhooks | Authenticity and idempotency later |
| AI providers | Egress allow-list, no PHI in logs |
| Abuse | Production rate limit 120/min; fail-open Redis is residual Wave 0 risk |
| Break-glass | Explicit, audited; unused `emergency_access_id` |

Consent does not grant API access. Purpose does not grant API access.

## 21. Inherited findings vs future macros

| Sev | Finding | Blocks a future macro? |
|---|---|---|
| P0 | None | — |
| P1 | None | — |
| P2 | DENIED audit rows roll back with `ForbiddenError` | Weakens security evidence for patient and AI later; does not block first Healthcare Web |
| P2 | Historical `patient_identity_id` not rewritten after MPI merge | Patient read model **must** resolve canonical/survivor identity |
| P2 | Same-org UUID read | Blocks staff cross-org chart and naive global-by-id APIs; **does not** block same-org MVP. Patient multi-org self-access needs a new PDP, not a lift of this restriction for staff |
| P3 | `app_dml` grants outside Alembic | Operational; does not block product macros |
| P3 | Nullable `provenance_id` | Service-set; keep for new domains |
| P3 | Duplicate clinical facts allowed | Read model must not assume uniqueness |
| P3 | Docker `:9100` image lag | Demo/ops; rebuild is not this discovery |

Do not fix these in this pass.

## 22. Macro capability candidates

| ID | Family | Depends on frozen clinical facts? |
|---|---|---|
| A | Platform identity / tenancy foundation | Isolation already; needs operator split + tenant semantics |
| B | Patient experience | Yes (read/project) + patient principal |
| C | Care access / appointment / scheduling | Encounter + identity; new ops domain |
| D | Pharmacy / medication workflow | Medication fact |
| E | Notifications | Cross-cutting |
| F | Emergency / ambulance | EMER encounter + anonymous identity; new ops |
| G | Clinical AI platform | Facts as inputs; gateway + entitlement + governance |
| H | SaaS / subscription / billing | Tenant organization |
| I | Frontend applications | All of the above as they land |

They are not Wave 2B.9.

## 23. Dependency graph (derived)

```
Frozen clinical foundation (closed)
        │
        ▼
A Tenancy + operator least-privilege
        │
        ├──────────────────────────────┐
        ▼                              ▼
Staff IAM (exists)              H SaaS / entitlements
        │                              │
        ▼                              ▼
I Healthcare Web                  G AI Gateway ──► Clinical AI
        │
        ├──────────────► C Scheduling ──► E Notifications
        ├──────────────► D Pharmacy
        └──────────────► F Emergency (dispatcher)

A Tenancy
        ▼
Patient principal
        ▼
B Patient experience / mobile
        │
        ├──────────────► medical-record read model (no new fact table)
        ├──────────────► C booking (patient side)
        ├──────────────► medication reminder (instruction + E)
        └──────────────► F emergency request
```

Notifications are a platform service consumed by scheduling, reminders, results, and emergency. AI Gateway depends on entitlements (quota) and must not depend on a specific frontend. Emergency depends on patient principal + healthcare dispatcher workspace + a **new** location/dispatch contract, not Medical Device.

## 24. Recommended implementation order

Optimize for architectural correctness, tenant security, a launchable MVP, and avoiding rewrites. **Not started.**

| Phase | Capability | Why this order |
|---|---|---|
| 1 | **A — Tenancy + PLATFORM_ADMIN least privilege + patient-principal contract** | Any client built on today’s operator PDP will bake PHI access for platform staff. Tenant grain must be explicit before billing and AI quota. |
| 2 | **I — Healthcare Web (registrar + clinician)** on existing `/api/v1/clinical` + MPI | Fastest clinically safe usability. Proves the frozen chart. One app, permission workspaces. |
| 3 | **B — Patient principal + medical-record read model + Patient Mobile shell** | Product is patient-centric; identity already exists. Same-org self-read first. |
| 4 | **C — Scheduling / appointments** | Closes the care-access loop; Encounter stays the clinical visit, not the calendar. |
| 5 | **E — Notification platform** | Scheduling reminders need a real orchestrator; building ad-hoc push inside appointments causes a rewrite. |
| 6 | **H — SaaS plans / entitlements** (billing port, no hardcoded payer) | Before AI and before selling modules. Manual/admin-granted entitlements can precede payment. |
| 7 | **D — Pharmacy workflow** | Needs Healthcare Web + Medication fact; not required to view a chart. |
| 8 | **Medication instruction + reminders** | Needs SIG contract + E + B. Do not alter frozen Medication first. |
| 9 | **G — AI Gateway, then clinician-in-the-loop assistants** | After entitlement/quota and audit/redaction design. Cost control before clinical AI features. |
| 10 | **F — Emergency / ambulance** | Highest operational and location-privacy complexity. Foundation (EMER + anonymous MPI) already exists. |
| — | **i18n** | Start with ID+EN in phase 2–3 UI; ZH later. Terminology display is ongoing, not a phase that unlocks others. |
| — | **Platform Admin Web** | After phase 1 permission split. Can be thin (org/user/plan) as soon as H exists; never a clinical browser. |

## 25. MVP boundary

Clinically safe first product: staff can document care; patients can see **their** facts; operators cannot casually read PHI; no autonomous AI.

| Feature | Class |
|---|---|
| Shared `/api/v1` backend | MUST (exists) |
| Org isolation Hospital A ↛ B | MUST (exists for staff) |
| Operator clinical least-privilege | MUST before Platform Admin Web |
| Healthcare Web (registration + clinician chart) | MUST |
| Encounter, note, condition, allergy, medication, observation, lab | MUST (facts exist; UI does not) |
| Patient Mobile: account + own record read (same-org first) | MUST |
| UI i18n ID + EN | MUST |
| Platform Admin: org/user provisioning only | SHOULD |
| Appointments | SHOULD |
| Notifications (in-app or push) | SHOULD |
| Medication instructions / reminders | SHOULD |
| Subscription plans / entitlements (manual grant OK) | SHOULD |
| Pharmacy dispense workflow | LATER |
| Payment provider / invoices | LATER |
| Clinical AI | LATER |
| Emergency / ambulance product | LATER |
| Inpatient bed / ward ops | LATER (`IMP` fact exists; ops do not) |
| ZH locale | LATER |
| Hospital-group hierarchy | LATER |
| QR / paperless check-in | LATER |

## 26. Architecture decision register

| Topic | Classification |
|---|---|
| Modular monolith shared backend | APPROVED BY EXISTING ARCHITECTURE |
| `/api/v1` only; no `/api/v2`; no `/fhir/` | APPROVED BY EXISTING ARCHITECTURE |
| Permission PDP; not `if role == doctor` | APPROVED BY EXISTING ARCHITECTURE |
| Frozen 13 clinical facts; Patient History = read model | APPROVED BY EXISTING ARCHITECTURE |
| Diagnosis → Condition; vitals → Observation | APPROVED BY EXISTING ARCHITECTURE |
| Purpose and Consent are not grants | APPROVED BY EXISTING ARCHITECTURE |
| One Healthcare Web; workspace by permission | READY FOR DESIGN |
| Organization as MVP tenant grain | See access/tenancy design (approved for later implementation) |
| PLATFORM_ADMIN least privilege / no default PHI | See access/tenancy design (Option C; approved for later implementation) |
| Patient principal + account↔identity | See access/tenancy design (approved for later implementation) |
| Medical-record projection API (no new fact table) | READY FOR DESIGN |
| Notification platform | READY FOR DESIGN |
| Monorepo three apps + generated client | READY FOR DESIGN |
| i18n: stable code, localized display | READY FOR DESIGN |
| Entitlement service separate from PDP | READY FOR DESIGN |
| Scheduling macro | NEEDS DOMAIN DESIGN |
| Pharmacy prescribe/dispense | NEEDS DOMAIN DESIGN |
| Medication SIG / reminder schedule | NEEDS DOMAIN DESIGN |
| Hospital group / parent org | NEEDS DOMAIN DESIGN |
| Subscription / billing ports | NEEDS DOMAIN DESIGN |
| AI Gateway + governance + economics | NEEDS DOMAIN DESIGN |
| Emergency request / ambulance dispatch | NEEDS DOMAIN DESIGN |
| Patient multi-org self-access PDP | NEEDS DOMAIN DESIGN |
| Paperless check-in / QR / queue | NEEDS DOMAIN DESIGN |
| Break-glass operator clinical access | NEEDS DOMAIN DESIGN |
| Payment provider selection | DEFERRED |
| Exact prices / margin | DEFERRED |
| ZH locale | DEFERRED (after ID+EN) |
| SMS channel | DEFERRED |
| Clinical AI assistants | DEFERRED (after gateway) |
| Inpatient operations | DEFERRED |
| Separate Doctor/Nurse/Hospital web apps | OUT OF SCOPE unless proven |
| Three backends / microservices | OUT OF SCOPE (v2.1) |
| Wave 2B.9 / duplicate clinical domains | FORBIDDEN |
| `patient_histories` table | FORBIDDEN |
| AI autonomous diagnosis or prescription | FORBIDDEN |
| Hardcoded model in clinical logic | FORBIDDEN |
| `if plan == "PRO"` | FORBIDDEN |
| UI as authorization | FORBIDDEN |
| Ambulance as Medical Device | FORBIDDEN |

This discovery does **not** approve implementation of any READY / NEEDS DESIGN topic.

## 27. Next design

Phase 1 access/tenancy design is recorded in `docs/architecture/product-access-tenancy-foundation-design.md` (approval gate: `docs/gates/product-access-tenancy-foundation-design-approval.md`). Implementation of that contract is **not** started in the discovery pass or the design pass. No frontend, no `0018`, no AI, no subscription tables until an implementation pass is separately approved.
