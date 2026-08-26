# Clinical Read Core — design contract

**Date:** 2026-08-26  
**Kind:** Design only  
**Status:** APPROVED FOR IMPLEMENTATION AFTER THIS DESIGN  
**Baseline:** `product-access-tenancy-foundation-frozen` / `0e0fe22b2b440c8dd44afdd59c80eea9c93c1716`  
**Alembic:** `current == heads == 20260814_0018`  
**Wave1PolicyPDP:** FROZEN — must not be edited  
**ProductAccessPDP:** remains `default_pdp()`; **no adapter required**  

This contract does not implement Clinical Read Core, Healthcare Web, Patient Mobile, migration `0019`, scheduling, notifications, pharmacy, subscription, or AI. It is not a HIPAA certification.

Companion gate: `docs/gates/clinical-read-core-design-approval.md`.  
Authoritative inputs: `docs/architecture/healthcare-web-clinical-chart-discovery.md`, Product Access design/freeze, Wave 2B clinical models.

---

## Decisions (normative)

| # | Topic | Decision |
|---|---|---|
| 1 | Module | New in-process module `clinical_read` inside the FastAPI modular monolith |
| 2 | Patient input | Accept **any org-visible identity UUID**, canonicalize, return canonical id |
| 3 | Cluster | `list_cluster_identity_ids(canonical)` membership `ACTIVE` + `MERGED_IN`; facts `patient_identity_id IN cluster` **and** `organization_id = request org` |
| 4 | Tenant | `X-Organization-Id` required; facts never cross org |
| 5 | Facility | Chart is **organization-wide by default**. Optional `facility_id` query is a filter, not a grant |
| 6 | Shell permission | `php-api` + membership + purpose + `mpi.identity.read` + org-visible identity. **No** `clinical.chart.read` |
| 7 | Sections | Existing `clinical.{domain}.read` (laboratory: three distinct permissions) |
| 8 | Unauthorized section | Shell **omits** the section key. Direct section URL **403**. Never serialize then hide |
| 9 | Header | Staff projection from MPI + optional allergy EXISTS; no NIK/BPJS in header |
| 10 | Summary | Bounded pointers to source facts; no inference |
| 11 | Section DTOs | **Read-specific** projections; do not reuse command response schemas as the chart contract |
| 12 | Notes | Clinical Read Core lists notes by patient (cluster+org) and optionally by encounter; full body stays `GET /clinical/notes/{id}` |
| 13 | Encounter view | Optional `encounter_id` filter on facts that have the column; facts without encounter remain on the longitudinal chart only |
| 14 | Timeline | Projection DTO; no table |
| 15 | Timeline time | Primary occurrence-like field, fallback `recorded_at` / `started_at` / `authored_at` |
| 16 | Pagination | Opaque **cursor**; default 50, max 100 |
| 17 | Filters | `encounter_id`, `status`, `category`, date range, `facility_id`. No PHI text search |
| 18 | Routes | Four staff GETs under `/api/v1/clinical/patients/{id}/chart…` |
| 19 | Errors | 404 conceal identity/cross-org/foreign facility header; 409 retired/unresolvable; 422 purpose/cursor; 403 missing permission on section URL |
| 20 | Audit | `CLINICAL_CHART_ACCESSED` on shell, summary, and timeline SUCCESS. Sections: authorize only. No payload PHI |
| 21 | Provenance | Reads create **no** `clinical_provenances` rows. Provenance viewer DEFERRED |
| 22 | Queries | Dedicated `ClinicalReadQueryRepository`; do not change frozen command list methods |
| 23 | Consistency | One request-scoped session; sequential queries; READ COMMITTED; no snapshot required |
| 24 | Cache | **None** |
| 25 | Migration 0019 | **Not required** |
| 26 | Indexes | Existing single-column indexes are sufficient for MVP; no speculative composites |
| 27 | Patient reuse | Shared query engine later; **staff HTTP is `php-api` only** |
| 28 | IAM shell / today’s encounters | **Not** this module |
| 29 | ProductAccessPDP | Unchanged. No new catalog permission |
| 30 | Dedup | Physical `id` only. No semantic merge of similar facts |

---

## 1. Module boundary

```
HTTP  GET /api/v1/clinical/patients/{id}/chart*
        ↓
ClinicalReadService          # staff presenter + authorization
        ↓
ProductAccessPDP.authorize   # existing permissions only
        ↓
ClinicalReadQueryEngine      # canonical + cluster + org SQL
        ↓
frozen tables via new query repository
        ↓
Staff chart DTOs
```

**Is:** read-only query module.  
**Is not:** source of truth, second database, event store, FHIR server, `patient_histories` domain, CQRS framework, Redis clinical store.

**Layout (future implementation, not created now):**

- `backend/app/modules/clinical_read/` — service, query repository, staff DTOs, `ClinicalReadAuditAction`
- `backend/app/api/v1/clinical_read.py` — additive router
- include from `backend/app/api/v1/router.py`

Do **not** add list methods onto frozen command repositories in a way that silently changes `list_*_for_patient(canonical_id)` semantics used by existing APIs.

Frozen `/api/v1/clinical/{domain}` command and per-id/list routes remain. Clinical Read Core is **additive**.

---

## 2. Canonical patient input

**Recommendation: accept any known identity UUID, then canonicalize.**

This matches frozen clinical services (`_require_canonical_identity`) and avoids forcing clients to know the survivor id after merge.

### Algorithm (staff chart)

1. Require staff audience `php-api` (`require_staff_audience`). Patient tokens → 401 invalid audience.
2. Require `X-Organization-Id` (422 `organization_required` if missing).
3. Parse `X-Purpose` via existing `parse_purpose` (422 if missing/unknown).
4. If purpose is `PATIENT_ACCESS` → **403** `purpose_principal_mismatch` **before** identity lookup (staff/patient public boundary; does not leak existence).
5. `authorize(..., action=mpi.identity.read, resource_type=PatientIdentity, organization_id, facility_id=X-Facility-Id, patient_id=requested id, purpose)`.
6. Load identity. Missing → 404 `"Patient identity not found"`.
7. Org visibility (same rule as MPI/clinical): provenance `source_organization_id == org` **or** an identifier with `organization_id == org`. Else 404 (same message). Do **not** use the platform-scope visibility bypass: ProductAccessPDP already forbids platform PHI; Clinical Read Core must not reintroduce it.
8. If lifecycle `RETIRED` → 409 `identity_not_usable` (frozen clinical wording).
9. `resolve_canonical_identity(requested)`. `None` → 409 `canonical_resolution_failed`.
10. Expand cluster: `list_cluster_identity_ids(canonical.id)` (`ACTIVE` + `MERGED_IN` only; **exclude** `UNMERGED`).
11. All subsequent fact queries: `organization_id = request org` AND `patient_identity_id IN cluster_ids`.
12. Every response includes `canonical_patient_identity_id` and `requested_patient_identity_id` so the client can switch to Y.

**Do not rewrite** clinical or MPI rows.

Merged source **X → Y**: request `/chart` with X returns Y’s chart plus org-scoped facts still stored on X. Do not HTTP-redirect.

---

## 3. Cluster vs organization

| Layer | Scope |
|---|---|
| MPI person / cluster | Platform-wide identity graph |
| Clinical facts | `organization_id` tenant |

Hospital A never receives Hospital B rows, even when the cluster contains the same person.

Unmerge: source membership becomes `UNMERGED` and is omitted from expansion; Y’s chart stops including X’s facts. Correct.

---

## 4. Facility

**Default = organization-wide chart** (discovery option A). Longitudinal history must not silently collapse to one site.

| Input | Effect |
|---|---|
| `X-Facility-Id` absent | PDP facility allow-list not applied (frozen). Chart still org-wide |
| `X-Facility-Id` present | Frozen `facility_tenant_decision` + Wave1 allow-list. Foreign UUID → 404 conceal. Chart still org-wide |
| Query `facility_id` | Optional **filter** on `facts.facility_id`. If the actor’s `actor_facility_ids` is non-empty and the filter is not in that list → 404 conceal. If the UUID is not a facility of this org → 404 conceal. Never expands access |

`NULL` facility facts: included in the org-wide chart; **excluded** when a facility filter is set (they are not site-tagged).

---

## 5. Chart shell authorization

**Minimum to open the shell:**

- Audience `php-api`
- Provisioned staff principal
- Valid purpose (not `PATIENT_ACCESS` on these routes)
- Organization membership (`X-Organization-Id` ∈ `actor_organization_ids`)
- `mpi.identity.read`
- Identity visible in that organization

**Forbidden:** a new `clinical.chart.read` that dumps all domains.

`authorized_sections` in the shell is **actor permission metadata** (which section keys this principal may request), not a patient data leak.

| Role (catalog today) | Shell | Sections |
|---|---|---|
| CLINICIAN | yes | all clinical sections |
| ORG_ADMIN | yes | all clinical **reads** (frozen catalog; tightening is a **separate** security design) |
| AUDITOR | yes | all clinical reads; no writes (writes are not this module) |
| REGISTRAR | yes | `encounters` only |
| IDENTITY_OFFICER | yes | none (header/MPI only) |
| PLATFORM_ADMIN | no | ProductAccessPDP denies `mpi.*` / `clinical.*` |
| NURSE | n/a | **no role**; do not invent |

---

## 6. Per-section authorization

**Combination:**

| Surface | Unauthorized behavior |
|---|---|
| `GET .../chart` (shell) | Omit section from `authorized_sections`. Do **not** call `authorize()` for missing section permissions (avoids DENIED-audit flood) |
| `GET .../summary` | Include only buckets the actor can read. Omit others entirely (no `authorized: false` stubs with counts) |
| `GET .../chart/sections/{section}` | `authorize()` the section’s permission(s). Missing → **403** `"Not authorized"` |
| `GET .../timeline` | Emit only rows whose `source_type` the actor can read. Empty page if none |

**Never** load unauthorized rows into memory and strip in a presenter.

Laboratory: three permissions. Nested DTO includes only layers the actor may read. Section URL is allowed if **at least one** of `clinical.laboratory.order.read`, `.specimen.read`, `.result.read` is present; 403 if none.

---

## 7. Patient header DTO (staff)

Computed at read time. No new persistence.

| Field | Source | Permission | MVP | Notes |
|---|---|---|---|---|
| `requested_patient_identity_id` | path | shell | MUST | |
| `canonical_patient_identity_id` | MPI resolve | shell | MUST | |
| `lifecycle_status` | **canonical** identity | shell | MUST | |
| `identity_kind` | canonical | shell | MUST | |
| `display_label` | canonical | shell | MUST | |
| `given_name` / `family_name` | canonical | shell | MUST | nullable |
| `birth_date` | canonical | shell | MUST | nullable |
| `age_years` | derived from `birth_date` vs UTC **date** of the request | shell | MUST | null if no DOB; not stored |
| `administrative_sex` | canonical | shell | SHOULD | nullable |
| `mrn` | identifier type `MRN` with `organization_id = request org` | shell | MUST when present | unmasked (org operational id). If several, return all matching as a list |
| `selected_encounter` | optional query `encounter_id` after visibility | `clinical.encounter.read` | MUST when requested | omit if no permission or no query |
| `documented_allergy_exists` | EXISTS allergy `status != ENTERED_IN_ERROR` AND `clinical_status = ACTIVE` in org+cluster | `clinical.allergy.read` | SHOULD | **omit field** if no allergy permission (do not send `false`) |

**Not in header:** NIK, BPJS, passport, phone, email, `surviving_identity_id` internals beyond canonical id, identifier `normalized_value`, tokens.

Age: Gregorian calendar, timezone UTC date. `age_years = year_diff` with birthday-not-yet-occurred adjustment. Do not localize the integer. Date display is a frontend locale concern.

Allergy indicator is **presence of documented Allergy facts**, not CDS.

---

## 8. Summary DTO (staff)

Optional MVP aggregation. Each item is `{ source_type, source_id, code_system, code, code_display, status, occurred_at }`. No AI, no synthesized diagnosis, no drug interaction.

| Bucket | Inclusion | Bound | Permission |
|---|---|---|---|
| `active_conditions` | `clinical_status ∈ {ACTIVE, RECURRENCE, RELAPSE}`, verification ≠ EIE | 10 | `clinical.condition.read` |
| `active_medications` | `status = ACTIVE` | 10 | `clinical.medication.read` |
| `active_allergies` | `status ≠ EIE`, `clinical_status = ACTIVE` | 10 | `clinical.allergy.read` |
| `recent_vitals` | Observation `category = VITAL_SIGNS`, status ≠ EIE | 5 | `clinical.observation.read` |
| `recent_lab_results` | result status ≠ EIE | 5 | `clinical.laboratory.result.read` |
| `recent_procedures` | status ≠ EIE | 5 | `clinical.procedure.read` |

Sort each bucket by that domain’s timeline timestamp descending, then `id` descending. Omit empty **and** unauthorized buckets.

---

## 9. Section ownership matrix

Cluster-aware: **yes for every clinical fact table**. Facility filter: optional query as in §4.

Pagination: cursor on all list sections. Default 50 / max 100 (existing command lists use a hard `LIMIT 100` with no cursor; read core must not return unbounded records).

| Section slug | Source | Read permission | Primary time | Fallback | MVP |
|---|---|---|---|---|---|
| `encounters` | `encounters` | `clinical.encounter.read` | `started_at` | — | MUST |
| `notes` | `clinical_notes` | `clinical.note.read` | `authored_at` | — | SHOULD (query gap) |
| `conditions` | `conditions` | `clinical.condition.read` | `onset_at` | `recorded_at` | MUST |
| `observations` | `observations` | `clinical.observation.read` | `effective_at` | `recorded_at` | MUST |
| `laboratory` | orders + specimens + results | three lab read permissions | result `effective_at` / specimen `collected_at` / order `ordered_at` | result `recorded_at` | SHOULD |
| `medications` | `medications` | `clinical.medication.read` | `started_at` | `recorded_at` | MUST |
| `allergies` | `allergies` | `clinical.allergy.read` | `onset_at` | `recorded_at` | MUST |
| `consents` | `consents` | `clinical.consent.read` | `period_start` | `recorded_at` | SHOULD |
| `immunizations` | `immunizations` | `clinical.immunization.read` | `occurrence_at` | `recorded_at` | LATER API (implement with core) |
| `procedures` | `procedures` | `clinical.procedure.read` | `occurrence_at` | `recorded_at` | SHOULD |
| `medical-devices` | `medical_devices` | `clinical.medical_device.read` | `occurrence_at` | `recorded_at` | LATER API |
| `adverse-events` | `adverse_events` | `clinical.adverse_event.read` | `occurrence_at` | `recorded_at` | LATER API |
| `family-histories` | `family_histories` | `clinical.family_history.read` | `occurrence_at` | `recorded_at` | LATER API |

**Implement all section slugs in Clinical Read Core** even if Healthcare Web defers tabs. Same engine, same tests. UI MVP may hide LATER tabs.

Vitals: **not a domain**. `GET .../sections/observations?category=VITAL_SIGNS` using frozen `ObservationCategory.VITAL_SIGNS`.

Diagnosis: **Condition**. UI may label “diagnosis”; DTO `source_type` remains `condition`.

Medication: frozen fact only (`PRESCRIBED` / `REPORTED` category, dose/route/started/stopped). No SIG, dispense, reminder, or pharmacy workflow.

---

## 10. Laboratory projection

Do not flatten away order → specimen → result.

MVP laboratory section page = **page of orders** (cluster+org, optional encounter/facility/date on `ordered_at`), each with:

- order fields (if `clinical.laboratory.order.read`)
- nested `specimens[]` for that order (if specimen read)
- nested `results[]` for that order (if result read)

If the actor has result read but not order read: page **results** as the top-level collection with `laboratory_order_id` / `laboratory_specimen_id` references only (no order code/display). Same idea if only specimen read.

Do not over-fetch sibling orders beyond the page.

---

## 11. Clinical notes

Frozen HTTP: `GET /clinical/notes/{id}` only. Repository: `list_notes_for_encounter`.

**Read Core:**

- Patient-level list: notes where `patient_identity_id IN cluster` AND `organization_id = org` (notes always have `encounter_id` NOT NULL).
- Encounter-level: additional `encounter_id =` filter (encounter must be visible in org and belong to the cluster patient).

List DTO: `id`, `encounter_id`, `note_type`, `record_status`, `version`, `authored_at`, `finalized_at`, `author_id`. **No `body_text`.** Full narrative: existing GET by id (already authorized).

---

## 12. Encounter view

- Longitudinal chart: default (no `encounter_id`).
- Selected encounter: query `encounter_id` on shell (header summary), summary, sections, and timeline.
- Encounter must exist, `organization_id` match, and `patient_identity_id IN cluster`. Else 404 `"Encounter not found"`.
- Filter applies only where the frozen column exists. Facts with `encounter_id IS NULL` appear on the longitudinal chart and **drop out** of the encounter-scoped view.
- Encounter is a care episode. `PLANNED` is lifecycle, not an appointment.

---

## 13. Timeline

No persistence. Item DTO:

| Field | Required |
|---|---|
| `source_type` | yes (`encounter`, `note`, `condition`, …) |
| `source_id` | yes |
| `occurred_at` | yes (mapped timestamp) |
| `organization_id` | yes |
| `facility_id` | if present on row |
| `canonical_patient_identity_id` | yes |
| `source_patient_identity_id` | yes (may be historical cluster member) |
| `code_system` / `code` / `code_display` | when the source has them |
| `status` | domain status / clinical_status as applicable |
| `encounter_id` | if present |

Do **not** embed note body, lab values, or medication text on the timeline row.

**Ordering:** `occurred_at DESC`, `source_type ASC`, `source_id DESC` (stable).

**Tie-break:** if primary nullable, use fallback before sort.

**Entered-in-error:** include on timeline and section lists (frozen lists do not strip EIE). Summary/header allergy indicator exclude EIE.

**Implementation of merge:** application-level merge of per-domain pages (bounded) **or** SQL `UNION ALL` of mapped columns. Either is allowed; must apply per-type permission **before** serialization. Prefer per-domain queries + k-way merge in the service so unauthorized domains are never queried.

---

## 14. Pagination and filters

**Cursor, not offset.** Concurrent writes would make offset unstable.

Opaque cursor: URL-safe base64 of JSON `{"t":"<iso8601>","k":"<source_type>","id":"<uuid>"}` with no PHI. Unsigned is acceptable: tampering cannot widen authorization. Malformed / semantically impossible → 422 `invalid_cursor`.

`limit`: default **50**, max **100**, min **1**.

`has_more` + `next_cursor` (omit cursor when complete).

Safe filters (AND, never OR-across-tenants):

- `encounter_id`
- `status` (domain-valid enum only; unknown → 422)
- `category` (domain-valid; observations include `VITAL_SIGNS`)
- `recorded_from` / `recorded_to` on the **timeline timestamp** of that section
- `facility_id` as §4

**Forbidden:** name/body/code-display free text search.

---

## 15. API contract (staff)

Prefix: `/api/v1`. Audience: `php-api`. **Not** `/api/v1/patient`. **Not** `/api/v2`. **Not** `/fhir`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/clinical/patients/{patient_identity_id}/chart` | Shell + header + `authorized_sections` |
| GET | `/clinical/patients/{patient_identity_id}/chart/summary` | Bounded summary |
| GET | `/clinical/patients/{patient_identity_id}/chart/timeline` | Timeline page |
| GET | `/clinical/patients/{patient_identity_id}/chart/sections/{section}` | One section page |

Unknown `{section}` → 404 `"Resource not found"` (do not enumerate via error text).

Headers: `Authorization`, `X-Organization-Id`, `X-Purpose`, optional `X-Facility-Id`, correlation id as today.

Rate limit: existing **120 req/min**. Aggregation **reduces** client fan-out versus Option A; do not change the limiter in this implementation.

---

## 16. DTO strategy

**B + presenter: read-specific DTOs.** Do not bind Healthcare Web to frozen `ConditionResponse` / `ClinicalNoteResponse` (command schemas can grow independently; notes include `body_text`).

Internal query rows may be simple dataclasses. `StaffChartPresenter` maps to HTTP models.

Later `PatientRecordPresenter` maps the **same query rows** to a different schema. Do not ship one JSON to both clients.

i18n: DTOs expose `code_system`, `code`, `code_display` as stored (authored). Do not translate codes in this module. Frontend ID/EN for chrome. Terminology service LATER.

No `card_color`, `icon_name`, `css_class`.

Minimum necessary: no ORM dump, no `provenance_id`, no `content_hash`, no identifier `matching_value`. Attribution: `organization_id`, `facility_id`, `recorded_at` / domain time, `recorder_id` UUID without joining user display names in MVP.

---

## 17. Staff vs Patient Mobile

Shared later: canonical resolve, cluster expansion, org-scoped SQL, timestamp map, pagination.

Distinct: HTTP routes, audience, PDP (`ProductAccessPDP` / `PatientSelfAccessPDP`), purpose (`PATIENT_ACCESS` only on patient routes), DTO, redaction.

Staff chart routes **must** keep `require_staff_audience`. Patient tokens cannot call them.

---

## 18. Purpose

Existing catalog only. Purpose never grants.

Healthcare Web **should** send: `TREATMENT` (clinician), `REGISTRATION` (registrar), `AUDIT` (auditor), `ADMINISTRATION` (org admin). `CARE_COORDINATION` and `EMERGENCY` remain valid catalog values if the principal has permissions.

Staff chart routes reject `PATIENT_ACCESS` (403, before lookup).

The same request purpose is recorded on every audit for that request. Sections do not re-parse a different purpose.

---

## 19. Audit vs provenance

New action string (module enum, **not** an edit of frozen `ClinicalAuditAction`):

`CLINICAL_CHART_ACCESSED`

Fits existing `SCREAMING_SNAKE` audit actions. Stored on `AuditEvent.action` (string). **No catalog table → no migration.**

| Event | When |
|---|---|
| SUCCESS `CLINICAL_CHART_ACCESSED` | Successful shell, summary, or timeline |
| DENIED | `authorize()` as today (section 403, shell missing `mpi.identity.read`, org/facility) |
| Section GET SUCCESS | **No** extra audit (same as frozen domain lists) |

Metadata (strings only): `purpose`, `canonical_patient_identity_id` (also `patient_id` column), `requested_patient_identity_id` if different, `surface` = `shell` \| `summary` \| `timeline`, `authorized_sections` = comma-separated slugs the actor could access (not what the patient has).

**Never log:** NIK, BPJS, note text, lab values, medication text, JWT, raw demographics.

`resource_type`: `ClinicalChart`. `resource_id`: canonical identity.

**Provenance:** chart reads insert **zero** `clinical_provenances` rows.

Inherited P2 DENIED-audit rollback: unchanged.

---

## 20. Error / concealment matrix

| Case | HTTP | Code / message |
|---|---|---|
| Unknown UUID | 404 | Patient identity not found |
| Cross-org identity | 404 | Patient identity not found |
| Platform staff PHI | 403 | Not authorized (PDP) |
| Missing `mpi.identity.read` | 403 | Not authorized |
| Foreign `X-Facility-Id` | 404 | Resource not found (`facility_tenant_decision`) |
| Invalid facility query | 404 | Resource not found |
| `RETIRED` visible identity | 409 | `identity_not_usable` |
| Canonical walk fails | 409 | `canonical_resolution_failed` |
| Missing/unknown purpose | 422 | existing purpose errors |
| `PATIENT_ACCESS` on staff chart | 403 | `purpose_principal_mismatch` |
| Missing org header | 422 | `organization_required` |
| Bad cursor | 422 | `invalid_cursor` |
| Bad limit/status/category | 422 | domain validation |
| Unknown section slug | 404 | Resource not found |
| Section lacking permission | 403 | Not authorized |
| Unknown / other-patient / other-org encounter | 404 | Encounter not found |
| Patient audience on staff route | 401 | Token audience is invalid |

---

## 21. Query, performance, cache

**Dedicated `ClinicalReadQueryRepository`** using SQLAlchemy `select` with `IN (cluster_ids)` + `organization_id`. Do not alter frozen `list_*_for_patient(single id)` used by command lists.

One `AsyncSession` per request (existing pattern). **Do not** `asyncio.gather` on the same session. Sequential queries. Header: identity + identifiers + optional allergy EXISTS. Summary: one bounded query per authorized bucket. Timeline: one query per authorized domain + merge.

Isolation: default READ COMMITTED. Independent sections may disagree by a concurrent write; clinically acceptable for MVP. No Redis. No repeatable-read snapshot.

N+1: no per-row provenance fetch; no browser fan-out.

Duplicates: `DISTINCT` / de-dupe by primary key if a join could double a row. **Do not** merge two different medication rows that “look similar.”

Immutability: no updates except the approved audit insert.

---

## 22. Indexes and migration

Existing indexes on `patient_identity_id` and `organization_id` (plus domain time columns) support MVP `IN` + org filter via bitmap AND.

`clinical_notes` has no `organization_id` index today; frozen `list_notes_for_encounter` already filters org. Not blocking.

**Migration 0019: not required.** No new tables, no audit catalog table, no required indexes.

Optional later (separate approval, after load tests): composite `(organization_id, patient_identity_id, recorded_at)` on hot tables. Do not create them in the first Clinical Read Core implementation.

---

## 23. Healthcare Web backend contract

After this module is implemented and frozen, Healthcare Web may assume:

- Staff `php-api` session + org/purpose headers
- Chart shell with canonical header and `authorized_sections`
- Summary, paginated sections, paginated timeline
- Encounter-scoped variant via `encounter_id`
- Writes remain frozen `/api/v1/clinical/*` mutations
- Lookup remains MPI exact identifier APIs (not this module)

Healthcare Web still **cannot** assume: membership picker payload, HTTP facility list, in-progress encounter index, name search, scheduling.

Those remain **HEALTHCARE WEB SHELL API DESIGN** (IAM/org) and a **separate small encounter-index design** (“in-progress encounters”, never “appointment roster”).

---

## 24. Threat model

| Threat | Impact | Mitigation | Test |
|---|---|---|---|
| UUID guessing | Existence leak | 404 conceal | random UUID → 404 |
| Merged id misuse | Wrong person / surprise Y | Canonicalize; return canonical; cluster ∩ org | X→Y includes X facts in org only |
| Cross-org cluster | Tenant breach | SQL `organization_id` | org B facts absent |
| Facility tamper | Cross-site | Header conceal; query filter ⊆ allow-list | foreign facility 404 |
| Mega-permission | Over-read | No `clinical.chart.read` | registrar shell has no conditions |
| Serialize-then-hide | Over-read | Query only permitted domains | mock repo never called |
| Cursor tamper | Skip/reorder only | Auth still applied; 422 malformed | forged cursor |
| Encounter tamper | Cross-patient | Encounter in cluster+org else 404 | other patient encounter 404 |
| Audit PHI | Log leak | metadata allow-list | audit row has no NIK/body |
| Query over-fetch | Extra PHI | bounded pages; no ORM dump | page size ≤ 100 |
| Patient token on staff chart | Wrong PDP | `require_staff_audience` | 401 |
| Staff token on `/api/v1/patient` | Out of scope here | existing patient router | unchanged |
| Weak shell permission | Full chart | per-section PDP | IDENTITY_OFFICER empty sections |

---

## 25. Test contract (preview — do not add tests now)

**Unit:** canonicalization; section permission matrix; timestamp map; cursor encode/decode; allergy EXISTS rules; DTO omission of unauthorized fields.

**Integration:** ACTIVE chart; MERGED X→Y includes historical X facts in org; unmerged excludes X; Hospital A/B isolation; facility header/query; purpose 422/403; registrar encounters only; notes patient+encounter list without body; pagination cursors; `CLINICAL_CHART_ACCESSED` on shell/summary/timeline; **no** new provenance rows; retired 409; unknown 404; no duplicate physical ids.

**Security:** no mega-dump; UUID guess; foreign org/facility; malformed cursor; `php-patient` on staff routes; `PATIENT_ACCESS` rejected on staff chart.

---

## 26. Classification

| Topic | Class |
|---|---|
| Clinical Read Core | **APPROVED FOR IMPLEMENTATION** (after this design) |
| Patient header | APPROVED FOR IMPLEMENTATION |
| Clinical summary | APPROVED FOR IMPLEMENTATION |
| Section reads (all domains) | APPROVED FOR IMPLEMENTATION |
| Timeline | APPROVED FOR IMPLEMENTATION |
| Encounter-scoped chart | APPROVED FOR IMPLEMENTATION |
| Clinical Note list (read core) | APPROVED FOR IMPLEMENTATION |
| Healthcare Web shell | READY FOR SEPARATE DESIGN |
| IAM membership / facility list APIs | READY FOR SEPARATE DESIGN |
| In-progress encounters index | READY FOR SEPARATE DESIGN (not appointments) |
| Patient Mobile presenter | DEFERRED |
| Patient cross-org record | FORBIDDEN until separate PDP |
| Name search | FORBIDDEN |
| Scheduling / notifications / pharmacy / AI | DEFERRED / OUT OF SCOPE |
| FHIR / `/api/v2` | FORBIDDEN |
| Materialized chart tables | DEFERRED (separate architecture) |
| `patient_histories` / VitalSign / Diagnosis tables | FORBIDDEN |
| Nurse permissions | OUT OF SCOPE (separate role design) |
| ORG_ADMIN catalog tightening | READY FOR SEPARATE DESIGN |
| Print/export | DEFERRED |
| Redis clinical cache | FORBIDDEN for MVP |
| ProductAccessPDP / Wave1PolicyPDP edits | FORBIDDEN in this implementation |

---

## 27. Future implementation scope (exact)

When a later pass is authorized, it may:

1. Add `clinical_read` module + query repository + staff DTOs + `CLINICAL_CHART_ACCESSED`.
2. Add the four GET routes and include the router.
3. Authorize with **existing** permissions only.
4. Add unit/integration/security tests listed above.

It may **not**: create migration `0019` unless a new blocker appears; edit Wave1PolicyPDP; add `clinical.chart.read`; rewrite historical `patient_identity_id`; create Healthcare Web; create Patient routes that share staff URLs; introduce Redis SoT; create projection tables.
