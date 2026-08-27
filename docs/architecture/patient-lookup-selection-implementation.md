# Patient lookup and selection — implementation

**Date:** 2026-08-27  
**Kind:** IMPLEMENTATION — not hardened, not frozen  
**Status:** COMPLETE  
**Baseline HEAD:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Parent:** `ca675b5a41782732995a4021fb85af7b9b29d5b5` (`iam-shell-context-frozen`)  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** not created  

This document is not a HIPAA, ISO 27001, or SOC 2 certification. Clinical Chart UI, Clinical Read Core frontend calls, clinical forms, name search, recent/today patients, scheduling, Patient Mobile, Platform Admin, AI, and PDP/frozen MPI route changes are out of scope.

Authoritative design: `docs/architecture/patient-lookup-selection-design.md`. Approval: `docs/gates/patient-lookup-selection-design-approval.md`.

---

## 1. Frozen baseline

| Item | Value |
|---|---|
| HEAD / `origin/main` | `1c502950011a168dbb139980ef758f2660561255` |
| Tag | `healthcare-web-shell-frozen` |
| Parent | `ca675b5a41782732995a4021fb85af7b9b29d5b5` |
| Alembic | exactly one head: `20260814_0018` |
| Migration 0019 | **not created** |
| Wave1PolicyPDP / ProductAccessPDP | not modified |
| Frozen `POST /api/v1/mpi/identities/lookup` | not modified |
| Clinical Read Core | not modified |

---

## 2. Backend route

**POST** `/api/v1/mpi/patients/lookup`

Read-command (PHI in body). Not a mutation. Coexists with frozen identity lookup.

**POST vs GET:** identifier values never appear in the URL, so they are absent from normal HTTP access-log paths, browser history, and Referer. Application middleware does not log request bodies. No body-logging middleware was added.

Staff audience `php-api` via existing MPI router `require_staff_audience`. Rejects `php-patient`, `php-platform`, missing/wrong/mixed `aud`.

**Permission:** existing `mpi.identity.read` through `authorize` + `Principal.for_organization(X-Organization-Id)`. No new permission. No role-name checks.

**Purpose:** required `X-Purpose` from the existing catalog. Staff `PATIENT_ACCESS` → 403 `purpose_principal_mismatch`. Unknown/missing → 422. Purpose is context, not a grant.

Workspace mapping (frontend only):

| Workspace | `X-Purpose` |
|---|---|
| Registration | `REGISTRATION` |
| Clinical | `TREATMENT` |
| Identity | `IDENTITY_RESOLUTION` |
| Audit | `AUDIT` |

---

## 3. Request / response DTO

Request (`PatientLookupRequest`, `extra=forbid`):

```json
{ "lookup_type": "MRN | NIK | BPJS | PATIENT_IDENTITY_ID", "lookup_value": "string" }
```

No `organization_id`, `identifier_organization_id`, `tenant_id`, or facility override in the body. Organization authority is **only** `X-Organization-Id`. Extra body fields → 422.

Response (`PatientLookupResponse`):

```json
{
  "outcome": "none | one | ambiguous | review_required",
  "truncated": false,
  "results": [ { "patient_identity_id": "...", "...": "..." } ]
}
```

Result fields: canonical `patient_identity_id`, `requested_patient_identity_id` when distinct, `lifecycle_status`, `identity_kind`, `display_name`, `display_label`, `birth_date`, `administrative_sex`, org MRN (unmasked operational), `masked_identifier` only when the lookup type was NIK/BPJS, `identifier_verification`, `resolved_from_merged`, `review_required`, `selectable`.

Not returned: full identifier list, full NIK/BPJS, address, phone/email, merge graph, match scores, clinical data, audit metadata, provenance internals. Submitted raw identifier is never echoed.

---

## 4. Tenant, facility, identifiers

Lookup is **organization-wide**. `X-Facility-Id` may be sent as work context and is passed to existing `authorize` / facility-tenant checks; it is **not** an identity visibility filter. No `facility_id` query predicate.

Supported MVP types only: MRN, NIK, BPJS, patient identity UUID. Unknown type → 422. No name, passport, phone, email, prefix, contains, wildcard, autocomplete, or fuzzy matching.

Exact match after frozen `normalize_identifier`:

| Type | Normalization | Scope |
|---|---|---|
| MRN | collapse whitespace, trim (not case-fold) | selected org + `identifier_type=MRN` |
| NIK | digits; 16 or 422; system `id.nik` | global row then current-org visibility |
| BPJS | digits 10–16 or 422; system `id.bpjs` | global row then current-org visibility |
| UUID | parse UUID or 422 | PK + visibility + canonicalize |

MRN of Hospital A does not find Hospital B. Unknown and cross-org NIK/BPJS share the same `200` empty outcome. No “exists in another organization.”

Unverified **MRN** is selectable after confirmation. Unverified **NIK/BPJS** → `review_required`, not deterministic Select. Lookup does not call `/mpi/match`.

---

## 5. Canonicalization, RETIRED, ANONYMOUS, cardinality

Uses frozen `resolve_canonical_identity` (max 8 hops). MERGED X with survivor Y returns **Y**, never selectable X. After walking, **current-org visibility is required on both the identifier-bearing identity and the canonical survivor**. Platform-scope visibility bypass is **not** used for this endpoint. A foreign identifier cannot hop to a local survivor.

RETIRED via identifier → `200` `none`. Direct UUID of RETIRED or unresolvable chain → `409` `identity_not_usable`. ANONYMOUS exact hit allowed; kind/label returned.

| Outcome | Behavior |
|---|---|
| 0 | `none`, `results: []` |
| 1 selectable | `one` — confirmation required in UI |
| >1 canonical | `ambiguous`, max **5**, `truncated` if more |
| unverified national ID only | `review_required` |

---

## 6. Masking, audit, rate limit, logging

NIK/BPJS confirmation uses existing `mask_identifier`. Org MRN unmasked.

Audit action **`PATIENT_LOOKUP_ACCESSED`** on authorized executions (none / one / ambiguous / review / canonicalized). Metadata: `lookup_type`, `outcome`, `result_count`, `truncated`, purpose. Canonical `patient_id` only for outcome `one`. **Never** raw MRN/NIK/BPJS. Does **not** emit `CLINICAL_CHART_ACCESSED`. Zero `clinical_provenances`. DENY remains existing `authorize` audit.

Rate limit: existing global IP limiter only. Lookup-specific per-principal throttle is **deferred P3** (design had no exact numeric policy). 429 message is generic.

---

## 7. Query shape (existing indexes)

No migration 0019. Bounded fetch `LIMIT 6` (5 + 1 truncation probe). Equality only.

- **NIK/BPJS:** `identifier_type` + canonical `identifier_system` + `normalized_value` + `organization_id IS NULL` + active/not rejected — uses unique global active index `(identifier_system, normalized_value)`.
- **MRN:** `identifier_type = MRN` + selected `organization_id` + `normalized_value` + active/not rejected — uses `ix_patient_identifiers_organization_id`. Not a full patient directory scan.
- Then `get_identity`, org-visibility (provenances / org-scoped identifiers), `resolve_canonical_identity` for at most six hits.

---

## 8. Frontend

| Item | Value |
|---|---|
| Route | `/app/patients/select` (no UUID/MRN/NIK/BPJS/name in URL) |
| Also | Registration / Clinical / Identity / Audit workspaces embed the same panel with locked purpose |
| Permission UX | `mpi.identity.read` (nav/guards only; backend authoritative) |
| Command | TanStack `useMutation`, `retry: false` |
| Purpose | explicit per workspace; not injected globally in `apiRequest` |
| Selection | memory-only `SelectedPatientSummary` bound to `organizationId` |
| Confirmation | always required for a single selectable hit |
| Chart | **not implemented**; zero `/clinical/patients/...` calls |

Org switch / logout / 401 / membership loss abort lookup (`AbortSignal` + generation via `TenantLoadCoordinator.begin`/`abort`) and clear input, result, and selected patient. Late Hospital A PHI is discarded when the selected org is Hospital B. Lookup A then B: generation guard keeps B.

Selected patient is not written to `localStorage`, `sessionStorage`, IndexedDB, or BroadcastChannel. F5 requires re-select. Duplicate tabs do not inherit PHI.

Accessibility: labeled type + value, keyboard submit, confirmation button, `aria-live` status, focus on result heading. No `dangerouslySetInnerHTML`. No clipboard helpers. No frontend audit fabrication.

---

## 9. OpenAPI

Types generated from **source** FastAPI (`scripts/export_iam_openapi.py` + `generate_iam_types.py`), not Docker `:9100`. Wrapper: `src/api/patients.ts` using `PatientLookupRequest` / `PatientLookupResponse`.

---

## 10. Quality results (this pass)

| Gate | Result |
|---|---|
| Backend pytest | **417 passed** (was 403) |
| Backend ruff | pass |
| Backend mypy | pass |
| Frontend tests | **81 passed** (19 files; was 72 / 18) |
| Frontend lint | 0 errors, 0 warnings (`oxlint --deny-warnings`) |
| Frontend typecheck | pass |
| Production build | pass |
| `npm audit --omit=dev` | 0 vulnerabilities |
| OpenAPI drift | pass (backend venv Python) |
| Alembic | `20260814_0018`, one head |
| Health | live 200, ready 200, postgres/redis/object_storage ok |
| Docker `:9100` lookup | **404** — P3 image lag; not rebuilt |

---

## 11. Deviations from approved design

- Dedicated route `/app/patients/select` in addition to embedding lookup in existing workspace pages (prompt example + design workspace placeholders).
- Per-user lookup throttle not implemented (no exact approved numeric policy).
- Docker image not rebuilt; new route absent on `:9100`.

No product-policy invention. Frozen MPI lookup, merge rules, Clinical Read Core, and PDPs were not changed.
