# Healthcare Web and clinical chart — architecture discovery

**Date:** 2026-08-26  
**Kind:** Architecture discovery only  
**Status:** NOT IMPLEMENTATION APPROVAL  
**Baseline:** `product-access-tenancy-foundation-frozen` / `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716`  
**Parent:** `wave-2b-clinical-foundation-complete` / `b1606fe38dfaf4ee24d95775c07e77cb842c3736`  
**Alembic:** `current == heads == 20260814_0018`  
**Wave1PolicyPDP:** FROZEN — must not be edited  
**ProductAccessPDP:** authoritative dispatcher  

This document does not authorize frontend code, a web application, migration `0019`, production APIs, Patient Mobile, Platform Admin Web, subscription, entitlement, AI, scheduling, notifications, pharmacy, emergency, commit, tag, or push.

Companion gate: `docs/gates/healthcare-web-clinical-chart-architecture-discovery.md`.  
Approved follow-on design: `docs/architecture/clinical-read-core-design.md`.  
Companion canvas (review-only, outside git): [healthcare-web-clinical-chart-discovery.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/healthcare-web-clinical-chart-discovery.canvas.tsx)

Frozen contracts that this pass must not reinterpret:

- Wave 2B native clinical facts (Encounter through Family History)
- Product Access & Tenancy (Organization == MVP tenant; patient principal; platform non-clinical)
- Patient History = **read model / timeline**, never a `patient_histories` table

---

## 1. Product target

The platform has **three clients** and **one shared FastAPI modular monolith**.

| Client | This pass |
|---|---|
| Healthcare Web | **In scope (architecture only)** |
| Platform Admin Web | Out of scope |
| Patient Mobile | Out of scope; reuse of a future read core is assessed |

**Healthcare Web is one application** for hospitals, clinics, clinicians, nurses (when a nurse permission bundle exists), registrars, organization administrators, and later pharmacy/lab/emergency staff.

Do **not** split into Doctor Web, Nurse Web, Hospital Web, or Clinic Web. Workspaces are navigation derived from principal + organization + facility + **permissions**. Workspaces are not backend roles.

```
Healthcare Web
    → staff JWT (audience php-api)
    → Principal (STAFF)
    → X-Organization-Id (request context)
    → optional X-Facility-Id (request context)
    → X-Purpose (audit/policy context, never a grant)
    → ProductAccessPDP → Wave1PolicyPDP
    → permission-filtered workspace + chart
```

Frontend-selected org/facility is **request context**, not a security authority. Backend membership and `facility_tenant_decision` remain authoritative.

---

## 2. Shared backend — keep the monolith

Do **not** create a Healthcare Web backend. The existing process already owns IAM, organization/facility, MPI, ProductAccessPDP, clinical facts, audit, provenance, purpose, and PostgreSQL consistency.

Recommended evolution **inside** the same process:

| Module | Role for Healthcare Web |
|---|---|
| `iam` | Staff user, memberships, `GET /api/v1/iam/users/me` |
| `authorization` | ProductAccessPDP + frozen Wave1 + purpose + facility tenant check |
| `organization` | Org/facility metadata (facility **list** HTTP is a small gap) |
| `mpi` | Exact identifier lookup, get-by-id, match (not a directory) |
| `clinical` | Frozen **commands** (create/amend/status/EIE) and existing per-domain lists |
| `clinical_read` (**new, later**) | Query/read module: chart, summary, timeline, cluster-aware projection |
| `audit` | Future chart-open / section-read events (not clinical provenance) |
| `patient_access` | Not used by Healthcare Web; PatientPrincipal only |

No Kafka, no second database as clinical SoT, no `/api/v2`, no `/fhir`.

---

## 3. Workspace model

| Workspace | Visibility source (UI) | Backend authority |
|---|---|---|
| Registration | `mpi.identity.*` + `clinical.encounter.create/read` | REGISTRAR catalog today |
| Clinical / doctor | `clinical.*.read` and matching writes | CLINICIAN catalog today |
| Nursing | **No NURSE role exists** | NEEDS SEPARATE ROLE/PERMISSION DESIGN |
| Organization admin | org/IAM + **existing clinical reads** (see §14) | ORG_ADMIN catalog today |
| Identity / MPI | `mpi.*` (no clinical chart) | IDENTITY_OFFICER |
| Audit / read-only chart | all `clinical.*.read`, no writes | AUDITOR |
| Pharmacy / Lab / Emergency | — | DEFERRED (same app, new permissions later) |

**workspace visibility ≠ authorization.** Never `if role == "DOCTOR"` in the backend. UI may hide a nav item when a permission is absent; the API must still deny.

---

## 4. Clinical chart — ownership (no new SoT tables)

Every chart section **projects** a frozen fact. Vital signs remain Observation (`VITAL_SIGNS`). Diagnosis remains Condition. Patient History remains this read model, not a table.

| Chart section | Source of truth | Staff read permission | List API today |
|---|---|---|---|
| Header identity | `patient_identities` + identifiers | `mpi.identity.read` | `GET /mpi/identities/{id}`, lookup |
| Encounter context | `encounters` | `clinical.encounter.read` | `GET /clinical/encounters?patient_identity_id=` |
| Conditions / diagnosis | `conditions` | `clinical.condition.read` | list by patient (+ optional encounter) |
| Observations / vitals | `observations` | `clinical.observation.read` | list by patient |
| Laboratory | orders / specimens / results | matching `clinical.laboratory.*.read` | three lists |
| Medications | `medications` | `clinical.medication.read` | list by patient |
| Allergies | `allergies` | `clinical.allergy.read` | list by patient |
| Immunizations | `immunizations` | `clinical.immunization.read` | list by patient |
| Procedures | `procedures` | `clinical.procedure.read` | list by patient |
| Medical devices | `medical_devices` | `clinical.medical_device.read` | list by patient |
| Adverse events | `adverse_events` | `clinical.adverse_event.read` | list by patient |
| Family history | `family_histories` | `clinical.family_history.read` | list by patient |
| Clinical notes | `clinical_notes` | `clinical.note.read` | **GET by id only**; repo can list by encounter |
| Consent (not in the sketch, exists) | `consents` | `clinical.consent.read` | list by patient |

The read layer must not redefine statuses, immutability, or coded semantics.

---

## 5. Read-model architecture (MVP recommendation)

Compare:

| Option | Verdict |
|---|---|
| **A.** Frontend fans out to every clinical list endpoint | Reject for MVP chart. N+1, no cluster expansion, notes gap, inconsistent auth UX, poor mobile reuse |
| **B.** One mega “give me the whole chart” endpoint with a single permission | **Forbidden.** Authorization bypass |
| **C.** Query / read module in the modular monolith | **Recommend for MVP** |
| **D.** Materialized projection tables | Later optimization only. Must not become a second SoT |

**MVP: Option C — `clinical_read` (name illustrative) inside the monolith.**

- **Commands** stay on frozen `/api/v1/clinical/{domain}` mutations. Healthcare Web must not invent `/web/conditions/create`.
- **Reads** for chart/summary/timeline go through the query module so cluster-aware, org-scoped, per-section-authorized aggregation exists once.
- Existing per-domain `GET` lists remain for command UIs and debugging; they are **not** sufficient as the longitudinal chart engine (they resolve to **canonical id only** and miss historical `patient_identity_id` rows — inherited P2).

This is **not** a CQRS product rewrite, not an event store, and not Redis-as-chart.

### Recommended API boundary (names subject to a later **design** pass)

Stay on `/api/v1`. Illustrative, not approved identifiers:

- `GET /api/v1/clinical/patients/{identity_id}/summary`
- `GET /api/v1/clinical/patients/{identity_id}/chart/sections/{section}`
- `GET /api/v1/clinical/patients/{identity_id}/timeline`

Do **not** use `/api/v1/patient/...` for staff (that prefix is PatientPrincipal + `php-patient`). Do not use `/fhir`. Do not use `/api/v2`.

A later Patient Mobile projection can call the **same query engine** with PatientSelfAccessPDP + `patient.record.read` + `PATIENT_ACCESS` + same-org filter. Staff and patient **DTOs stay distinct**.

---

## 6. MPI cluster-aware reads (required for a correct chart)

Frozen behavior: merge does **not** rewrite clinical `patient_identity_id`. Facts for merged source **X** still say X. Canonical survivor is **Y**.

**Safe query semantics for staff chart of Y in organization A:**

1. Authorize actor for org A (membership + purpose + facility tenant rule if facility present).
2. Resolve canonical identity (Y). Conceal if the identity is not visible in org A (existing provenance/identifier org rule).
3. Expand **cluster member ids** `{Y, X, …}` using frozen MPI cluster membership (`ACTIVE` / `MERGED_IN`).
4. Select clinical rows where `organization_id = A` **and** `patient_identity_id IN cluster_ids`.
5. Do not return another organization’s rows even if the person UUID is global.
6. Deduplicate by fact `id`, not by code.
7. RETIRED standalone identity: no new writes (frozen 409); chart read of a retired-only id remains conceal/409 per existing identity rules.
8. MERGED source id: follow canonical for the chart key; include historical facts via cluster expansion.

This expansion belongs in **`clinical_read`**, not in rewriting frozen command services, and not in a new fact table.

---

## 7. Tenant and facility isolation

- Tenant = `organization_id`. Hospital A must not read Hospital B facts.
- Empty `actor_facility_ids` = all facilities **in that organization** (frozen).
- Foreign facility UUID = deny/conceal (frozen `facility_tenant_decision`).
- Chart **default grain is organization-wide** (facts already store `organization_id`). Facility is request context and optional fact metadata, not a second tenant.
- Facility-bound membership: Healthcare Web **should** send `X-Facility-Id` for the selected site. Frozen Wave1 only applies the allow-list when `facility_id` is present; this discovery does **not** redesign that. Optional UX filter of facts by `facility_id` is not a new PDP.

Independent org/facility FKs on frozen tables remain P3; production mutations already go through `authorize()`. Chart queries must filter `organization_id` in SQL, not trust the client.

---

## 8. Purpose

Existing catalog (do not extend unless a later contract requires it):

`REGISTRATION`, `IDENTITY_RESOLUTION`, `EMERGENCY`, `CARE_COORDINATION`, `ADMINISTRATION`, `PATIENT_ACCESS`, `AUDIT`, `SYSTEM_OPERATION`, `TREATMENT`.

Purpose is required context, never a grant.

| Healthcare Web activity | Typical purpose |
|---|---|
| Clinician chart + writes | `TREATMENT` |
| Registrar lookup / encounter open | `REGISTRATION` |
| Org admin operational + if they use chart | `ADMINISTRATION` (does not create extra rights) |
| Auditor chart | `AUDIT` |
| Patient Mobile (later) | `PATIENT_ACCESS` only |

`PATIENT_ACCESS` is not a staff chart purpose.

---

## 9. Patient header (MVP)

Derive only from existing fields. No new persistence.

| Field | Source | MVP | Notes |
|---|---|---|---|
| Display name | `given_name`, `family_name`, `display_label` | MUST | Anonymous identities have limited labels |
| Age / DOB | `birth_date` | MUST | Compute age in presentation; do not store |
| Administrative sex | `administrative_sex` | SHOULD | Nullable |
| Lifecycle | `lifecycle_status` | MUST | MERGED/RETIRED/ANONYMOUS affect UX |
| Canonical id | identity UUID | MUST | Not in page title if it leaks in shared screens; allowed in clinical URL with access control |
| Org-scoped MRN | identifier type MRN, `organization_id` match | MUST when present | Masking already used on identifier APIs; header may show operational MRN to authorized staff |
| NIK | identifier type NIK | LATER / minimize | High-sensitivity; do not put in URL; lookup allowed, display masked |
| Selected encounter | client selection + `GET encounter` | MUST | Encounter ≠ appointment |
| Allergy signal | count/presence of non-EIE allergies | SHOULD | Presentation of documented fact, **not** CDS |
| Active conditions | problem-list conditions | SHOULD | Overview, not a new table |
| Facility name | `facilities` via encounter or header context | SHOULD | Needs facility read/list |

Security: `mpi.identity.read` + org visibility. Cross-org UUID → 404 conceal.

---

## 10. Patient selection (not scheduling)

Wave 1 policy: **search is not matching**. Name directory and unrestricted patient list are **FORBIDDEN** without a separate privacy design.

| Capability | Classification |
|---|---|
| Exact identifier lookup (`POST /mpi/identities/lookup`) | **READY** (MRN, NIK, etc. as stored) |
| Get identity by UUID | **READY** (404 conceal) |
| MPI match evaluate | **READY** for registrar/identity officer, not a chart picker |
| UUID typed from clipboard after prior care | **READY** if authorized |
| Recently accessed patients | **NEEDS DESIGN** (local staff UX vs server audit-derived list; PHI cache risk) |
| “Today’s patients” = `IN_PROGRESS` encounters for org/facility | **NEEDS DESIGN** (query on frozen `encounters`, **not** appointments) |
| Open name search / global directory | **FORBIDDEN** |
| Appointment roster | **DEFERRED** (scheduling domain) |
| Cross-tenant lookup | **FORBIDDEN** |

**Encounter ≠ Appointment.** `EncounterStatus.PLANNED` is an encounter lifecycle state, not a booked slot. Do not fake a schedule from encounters.

Healthcare Web can ship a usable chart **before scheduling** using: identifier lookup → open chart → list that patient’s encounters (including `IN_PROGRESS`). A “Today’s Patients” board is a later encounter-index query, still not scheduling.

---

## 11. Encounter context

Use frozen Encounter as-is:

- Patient-level longitudinal chart (default)
- Selected encounter as a **filter** on facts that carry `encounter_id` (optional)
- Status, class (`AMB`/`IMP`/`EMER`/…), started/ended, optional `facility_id`
- Writes already require purpose + org + permissions

No appointment semantics inside Encounter.

---

## 12. Authorization for aggregated reads

**Recommend: chart shell + per-section PDP.**

1. Shell: staff audience, org membership, purpose, `mpi.identity.read`, identity visible in org. Missing identity → 404 conceal.
2. Each section: **that section’s** `clinical.{domain}.read` (laboratory: the specific order/specimen/result permission for included objects).
3. Absent permission → omit section in DTO + UX hide; never leak counts of unauthorized domains.
4. One permission must never dump all domains.

Do not implement field-level ABAC in MVP. Staff clinical DTO vs later patient-facing DTO is enough. Platform operator: **no PHI** (frozen).

---

## 13. ORG_ADMIN (existing catalog, not assumed)

Live `ROLE_PERMISSIONS[ORG_ADMIN]` includes **every** `clinical.*.read` plus `mpi.identity.read`, IAM membership, and org/facility administration. It does **not** include clinical writes.

Healthcare Web **must not invent** extra PHI. It also **must not silently strip** these reads in the backend during this discovery. Document:

- **Today:** a tenant ORG_ADMIN can open a staff chart (read-only) if the UI exposes it.
- **Future tightening** (org-admin without chart) is **NEEDS SEPARATE DOMAIN DESIGN**, not a stealth Product Access change.

---

## 14. REGISTRAR

Live catalog: MPI create/read/add identifier/match evaluate; encounter create/read; org/facility read. **No** condition, medication, allergy, note, lab, etc.

Safe initial workspace: registration, identifier lookup, identity create, open/list **encounters for a selected patient**, not a full chart. Frontend must not show clinical sections the API will 403.

---

## 15. Clinician workflow (conceptual)

Login (`php-api`) → select org (and facility if bound) → patient lookup → chart (read core) → optional encounter → create facts via **existing** mutation APIs.

Write APIs are ready for a command UI. Duplicate write routes are forbidden.

---

## 16. Nursing

**No NURSE role or nurse permission bundle exists.** Vital signs remain Observation. Do not create `vital_signs`. Nursing workspace = **NEEDS SEPARATE ROLE/PERMISSION DESIGN**. Until then, do not pretend CLINICIAN == nurse.

---

## 17. Clinical write strategy — inventory

Existing `/api/v1/clinical/*` commands remain the write surface.

| Domain | Command UI |
|---|---|
| Encounter create/status | READY FOR WEB COMMAND UI |
| Note create/update draft/finalize/EIE | READY; **list-by-patient HTTP missing** (query gap) |
| Condition create/status/EIE | READY FOR WEB COMMAND UI |
| Observation create/amend/EIE | READY (vitals = category) |
| Lab order/specimen/result | READY as documented facts; LIS/instrument workflow LATER |
| Medication create/stop/EIE | READY as **documented medication fact**; prescribe/dispense **DEFERRED** (pharmacy) |
| Allergy create/amend/EIE | READY |
| Consent create/amend/revoke/EIE | READY |
| Immunization / Procedure / Device / Adverse event / Family history | READY as documented facts |

Gaps that are **workflow domains**, not missing REST verbs: prescription pad, pharmacy dispense, appointments, notifications, AI.

---

## 18. Staff vs patient projection

| | Staff chart | Patient record (later) |
|---|---|---|
| PDP | ProductAccessPDP → Wave1 | PatientSelfAccessPDP |
| Permissions | `clinical.*.read` | `patient.record.read` only |
| Purpose | TREATMENT / AUDIT / … | PATIENT_ACCESS |
| DTO | coded clinical | simplified / redacted / education later |
| Engine | shared `clinical_read` queries | same engine, different presenter |

Do not serve one JSON blob to both clients.

---

## 19. Patient Mobile reuse

```
Clinical Read Core (org + cluster + pagination)
        ├── StaffChartPresenter (clinical.* + staff DTO)
        └── PatientRecordPresenter (later: self + same-org + patient.*)
```

Authorization and presentation **must** remain distinct. Patient multi-org remains **FORBIDDEN** until a separate PDP design.

---

## 20. Internationalization

Target: Indonesian, English, Simplified Chinese. **MVP: ID + EN.** Architecture must not block ZH.

- Canonical **codes stay stable**. Do not translate code tokens. Do not store language-specific copies of clinical rows.
- UI strings: frontend catalogs (i18next).
- API error `code` stable; localized `message` at the edge later.
- Terminology display: later catalog/service keyed by code+locale; until then, persist frozen `code_display` as authored, not as the only locale.
- User locale: staff preference later; browser `Accept-Language` is a hint, not authorization.
- Notifications: out of scope (separate later).

---

## 21. Frontend technology (recommendation)

**Vite + React + TypeScript SPA**, React Router, TanStack Query, React Hook Form, i18next, OpenAPI-generated types from FastAPI.

Rationale: small team, form-heavy clinical UI, already-FastAPI backend, no need for SSR of PHI (CDN/cache risk). Not chosen for fashion. Next.js is not required and is a poorer default for authenticated PHI UIs.

Auth: `Authorization: Bearer` staff access token, audience **`php-api` only**. Never `php-platform` or `php-patient`. No refresh endpoint exists; session = IdP/login again when JWT expires. Do not persist tokens in `localStorage` on shared workstations; prefer memory (and treat any `sessionStorage` as a residual-PHI risk). `GET /iam/users/me` drives navigation. Org/facility headers on every API call.

Accessibility: keyboard, contrast, dense tables, clear status hierarchy — design standard for a later UI pass, not this discovery.

Responsive: **desktop + tablet primary**. Limited mobile browser for on-call is optional; **Patient Mobile remains a separate product**.

---

## 22. Repository and design system

**Recommend A/B: keep one git repository; later add `apps/healthcare-web` (and later `apps/platform-admin-web`) beside `backend/`.** Do not split Healthcare Web into its own repo at current team size. Do not reorganize now.

Shared design tokens/accessibility between Healthcare Web and Platform Admin Web: **later**. Patient Mobile will not share React DOM components. Do not create a component library in this pass.

Independent deploy: static SPA + existing API process.

---

## 23. Org/facility HTTP gaps

- `GET /organizations/{id}` exists.
- **No** `GET .../facilities` list route (repository `list_facilities` exists). Facility switcher needs a thin **organization query** in a later design. Not migration `0019`, not a clinical table.

Memberships already carry `organization_id` and optional `facility_id`; `GET /iam/users/me` today returns roles/permissions, not membership org list — **NEEDS DESIGN** to expose allowed org/facility ids to the shell without making the client authoritative.

---

## 24. Performance

Current lists: `LIMIT 100`, indexed `patient_identity_id` + `organization_id`. Chart of many domains = many queries.

MVP: parallel section queries in `clinical_read`, pagination/cursors on timeline, no Redis clinical cache (Redis is not SoT). Later: optional short-TTL cache of **non-authoritative** summaries keyed by org+patient+permission hash — only after a design. Avoid N+1 from the browser (that is why not Option A).

---

## 25. Longitudinal timeline

Projection only. Sort key per fact type (do not invent a unified clinical table):

| Fact | Time fields (existing) |
|---|---|
| Encounter | `started_at`, `ended_at` |
| Note | `authored_at` |
| Condition | `recorded_at`, `onset_at` |
| Observation | `recorded_at` |
| Lab | order `ordered_at`, specimen `collected_at`, result `recorded_at` |
| Medication | `recorded_at` |
| Allergy / consent / immunization / procedure / device / AE / family history | `recorded_at` / occurrence fields as frozen |

Timeline DTO: `{ occurred_at, domain, fact_id, title/code, status }` referencing source ids. Filter EIE per existing read conventions.

---

## 26. Overview / alerts

MVP overview **may** show documented: active conditions, current medications, allergy presence, recent labs/vitals/procedures — each as pointers to source facts.

**Forbidden:** drug–drug engine, diagnosis suggestion, risk scores, AI recommendations. “Allergy documented” is data display, not CDS.

Print/PDF/export: **DEFERRED** (READY FOR DESIGN later). Not MVP. Paperless ≠ no future printable record.

---

## 27. Audit vs provenance

- Opening a chart **should** emit an audit event later: actor, org, facility, purpose, canonical patient id, sections authorized — **no** NIK, no token, no clinical payload.
- Per-section reads: optional, volume-sensitive; start with chart-open + write audits (writes already audit).
- Inherited P2: DENIED-audit rollback — does not block Healthcare Web MVP.
- Chart read **must not** insert `clinical_provenances`.

---

## 28. Errors and concealment

| Case | Behavior |
|---|---|
| Unknown / cross-org patient | 404 Resource not found |
| Foreign facility on request | 404 conceal (frozen) |
| Unauthorized section | omit / 403 on direct section URL — do not reveal other sections’ existence via errors |
| Missing/unknown purpose | 422 |
| Wrong purpose | 403 |
| MERGED id as chart key | resolve canonical or 409 per frozen identity rules |
| RETIRED | no new clinical writes; read conceal/409 |
| Frontend permission spoof | API deny |

---

## 29. Threat model (mitigations — not implemented here)

| Threat | Mitigation direction |
|---|---|
| Patient UUID guessing | 404 conceal; org visibility |
| Org/facility header tamper | membership + facility_tenant_decision |
| Stale session / privilege change | short JWT TTL; re-resolve principal every request (already DB-backed) |
| XSS / token theft | CSP later; no token in localStorage; sanitize |
| CSRF | low while Bearer-only; if cookies later, CSRF tokens |
| Shared workstation | logout, no PHI in durable browser storage, idle timeout later |
| Cached PHI | Cache-Control on chart responses later; TanStack Query memory only |
| URL PHI | prefer opaque ids; no NIK in query string |
| UI permission spoof | backend deny |
| Direct API bypass of UI | assumed attacker; PDP is the boundary |
| Print/export leakage | defer export; later watermark/audit |

---

## 30. Frozen P2/P3 impact on this product

| Finding | Blocks Healthcare Web MVP? |
|---|---|
| P2 DENIED audit rollback | No |
| P2 historical `patient_identity_id` non-rewrite | **Blocks a correct longitudinal chart if using current list APIs alone.** Solved by `clinical_read` cluster expansion, not by rewriting clinical history |
| P3 grants outside Alembic | No |
| P3 nullable provenance | No |
| P3 Docker image lag | No (web will call a current API) |
| P3 independent org/facility FKs | No if queries filter `organization_id` |

P0/P1: none unresolved on the frozen foundation.

---

## 31. MVP boundary (derived from repo readiness)

**MUST**

- Staff login (`php-api`)
- Org (and facility) request context
- Exact identifier lookup + get identity
- Patient header from MPI fields
- Chart shell with per-section permission filtering
- Encounter list/view for that patient (not a schedule)
- Conditions, observations/vitals, medications, allergies as first clinical sections
- Use existing mutations for those domains
- ID + EN UI strings

**SHOULD (same release train if read core exists)**

- Labs, procedures, notes (after notes list query)
- Overview/summary
- Consent section
- Timeline

**LATER**

- Immunization, devices, AE, family history as extra tabs (APIs already exist)
- Today’s-patients encounter index
- Recently accessed
- Scheduling, pharmacy, notifications, AI, billing, messaging, export
- Nurse-specific workspace
- ZH locale
- ORG_ADMIN chart tightening

**FORBIDDEN in this product slice**

- Name search directory
- `patient_histories` table
- Platform Admin inside Healthcare Web
- Patient token on staff APIs
- FHIR / `/api/v2`
- Encounter-as-appointment
- CDS / AI-required workflow

---

## 32. Classification index

| Topic | Class |
|---|---|
| One Healthcare Web shell | READY FOR DESIGN |
| Staff auth `php-api` | APPROVED BY FROZEN FOUNDATION |
| Org/facility as request context | APPROVED BY FROZEN FOUNDATION |
| Facility list + memberships-for-shell APIs | READY FOR DESIGN (thin IAM/org queries) |
| Exact identifier patient lookup | APPROVED BY FROZEN FOUNDATION |
| Open name search | FORBIDDEN |
| Patient chart read model (`clinical_read`) | READY FOR DESIGN |
| Clinical summary / timeline | READY FOR DESIGN |
| Cluster-aware org-scoped queries | READY FOR DESIGN (required) |
| Existing clinical mutation UI | READY FOR DESIGN (APIs frozen) |
| Notes list-by-patient/encounter HTTP | READY FOR DESIGN (repo exists) |
| Registrar workspace | READY FOR DESIGN (narrow) |
| ORG_ADMIN chart (read-only via catalog) | APPROVED BY FROZEN FOUNDATION (tightening later) |
| Nursing workspace | NEEDS SEPARATE ROLE/PERMISSION DESIGN |
| Scheduling | DEFERRED |
| Notifications | DEFERRED |
| Pharmacy workflow | DEFERRED |
| AI | DEFERRED (chart must work without it) |
| Platform Admin Web | DEFERRED (separate client) |
| Patient Mobile | DEFERRED (separate client; shared read core later) |
| Multilingual UI ID+EN | READY FOR DESIGN |
| ZH | DEFERRED (architecture must allow) |
| Print/export | DEFERRED |
| Materialized read tables | DEFERRED |
| `patient_histories` / VitalSign table / Diagnosis table | FORBIDDEN |

---

## 33. Recommended implementation sequence

Safest order (dependencies, not fashion):

1. **Clinical Read Core design + implementation approval** — cluster expansion, org filter, per-section auth, pagination. Unblocks a truthful chart.
2. **IAM/org shell APIs** — allowed organizations/facilities for the principal; facility list.
3. **Healthcare Web shell** — login, context, permission-driven nav, i18n ID/EN. Still no fake data.
4. **Patient selection** — lookup + header.
5. **Summary + first sections** (conditions, allergies, medications, observations).
6. **Encounter filter + notes list query**.
7. **Mutation forms** bound to frozen command APIs.
8. **Timeline + remaining sections**.
9. **Later:** encounter “today” index, nurse bundle, scheduling, patient presenter.

Do not start the SPA before the read-core **design** is approved if the first screen is a longitudinal chart. A registrar-only shell could theoretically precede read core, but the product target is the chart — so read core is first.

---

## 34. What this pass does not do

No production code, tests, migration `0019`, frontend app, commit, tag, or push. Frozen clinical domains, Product Access semantics, and Wave1PolicyPDP remain untouched.
