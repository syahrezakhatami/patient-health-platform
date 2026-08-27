# Patient lookup and selection — architecture / security design

**Date:** 2026-08-27  
**Kind:** DESIGN ONLY — not implemented  
**Status:** COMPLETE  
**Baseline HEAD:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Parent:** `ca675b5a41782732995a4021fb85af7b9b29d5b5` (`iam-shell-context-frozen`)  
**Alembic:** `current == heads == 20260814_0018`  
**Migration 0019:** not created  

This document is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement lookup UI, selection state, clinical chart, clinical forms, new HTTP routes, or MPI/Clinical Read/PDP changes.

Frozen surfaces consumed, not modified: Healthcare Web Shell, IAM Shell Context, multi-org isolation, Clinical Read Core, MPI, Product Access, Wave1PolicyPDP, ProductAccessPDP, clinical domains.

Authoritative prior design: `docs/architecture/healthcare-web-shell-iam-context-design.md`, `docs/architecture/healthcare-web-clinical-chart-discovery.md`, `docs/gates/clinical-read-core-final-freeze.md`.

---

## 1. Baseline

Verified at design time:

| Item | Value |
|---|---|
| `HEAD` / `origin/main` | `1c502950011a168dbb139980ef758f2660561255` |
| Tag | `healthcare-web-shell-frozen` |
| Parent | `ca675b5a41782732995a4021fb85af7b9b29d5b5` |
| Working tree | clean before this uncommitted design |
| Wave1PolicyPDP SHA-256 | `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |
| ProductAccessPDP SHA-256 | `65be80f179c32e57d03542bca3df8156b0e8d36177b5089823e7159eb5d679cc` |

---

## 2. Current MPI read surface (production)

Staff audience `php-api`. Every MPI route requires `X-Organization-Id` and `X-Purpose`. `X-Facility-Id` is optional work context (validated when present), **not** a patient-visibility filter.

`mpi.*` permissions are org-scoped and PHI-classified. Catalog (no `audit.*`, no `mpi.lookup.*`):

| Permission | Seeded roles |
|---|---|
| `mpi.identity.read` | CLINICIAN, REGISTRAR, IDENTITY_OFFICER, AUDITOR, ORG_ADMIN |
| `mpi.identity.create` | REGISTRAR, IDENTITY_OFFICER |
| `mpi.identifier.add` | REGISTRAR, IDENTITY_OFFICER |
| `mpi.identifier.verify` | IDENTITY_OFFICER |
| `mpi.match.evaluate` | REGISTRAR, IDENTITY_OFFICER |
| `mpi.match.review` | IDENTITY_OFFICER |
| `mpi.merge.execute` / `mpi.unmerge.execute` | IDENTITY_OFFICER |

### Routes relevant to finding a patient

| Method | Path | Permission | Lookup-relevant? |
|---|---|---|---|
| `POST` | `/api/v1/mpi/identities/lookup` | `mpi.identity.read` | Closest existing search. POST body: `identifier_system`, `identifier_type`, `identifier_value`, optional `identifier_organization_id`. Returns full `IdentityResponse` or **404**. Does **not** canonicalize MERGED. Active identifiers only (`valid_to IS NULL`, verification not REJECTED/EXPIRED). Includes **UNVERIFIED**. |
| `GET` | `/api/v1/mpi/identities/{identity_id}` | `mpi.identity.read` | UUID resource. Returns MERGED as-is (`surviving_identity_id` set). RETIRED returned if org-visible. Cross-org/unknown → 404 conceal. |
| `POST` | `/api/v1/mpi/match` | `mpi.match.evaluate` | Matching engine, not lookup. May persist candidates. Excludes RETIRED/MERGED candidates. **Not** a chart picker. |
| `GET` | `/api/v1/clinical/patients/{patient_identity_id}/chart` | `mpi.identity.read` + section `clinical.*` | Chart open. **Does** canonicalize MERGED. RETIRED → **409**. Not a lookup API. |

Create/identify/verify/merge/unmerge are mutations. No cluster HTTP routes. No patient directory, no name search, no `/api/v2`, no FHIR.

**Cross-org:** global identifier types (NIK, BPJS, PASSPORT, PHONE, EMAIL, …) are stored with `organization_id IS NULL`. Lookup finds the identifier globally, then `get_identity` enforces org visibility (provenance org **or** an identifier with `organization_id == selected org`, unless platform scope). Missing/other-org → same 404 message. MRN/EXTERNAL are org-scoped.

**Masking (MPI responses):** NIK/BPJS/PASSPORT/PHONE/EMAIL (and other sensitive types) use `mask_identifier` (last 4 visible, at least 8 `*`). MRN/EXTERNAL/OTHER return raw value in `masked_value`.

**Existing lookup is not sufficient** for Healthcare Web selection (see §20).

---

## 3. Repository capabilities (reuse, do not invent matching)

| Need | Existing |
|---|---|
| Exact identifier | `MpiRepository.find_active_identifier(system, normalized_value, organization_id)` — indexed |
| Identity by UUID | `MpiRepository.get_identity` |
| Canonical survivor | `resolve_canonical_id` / `MpiRepository.resolve_canonical_identity` (max 8 hops). Used by Clinical Read and match; **not** by current MPI lookup/get |
| Cluster members | `list_cluster_identity_ids` (chart, not lookup UI) |
| Authoritative count helper | `count_authoritative_by_identifier` — unused |
| Normalization | `normalize_identifier` in `mpi/domain/identifiers.py` |
| Masking | `mask_identifier` |
| Org vs global | `requires_organization` / `is_global_identifier` |

**Indexes (migration 0018 / 0002):** `uq_patient_identifiers_global_active` `(identifier_system, normalized_value)` WHERE org IS NULL and active; `uq_patient_identifiers_org_active` `(identifier_system, organization_id, normalized_value)` WHERE org NOT NULL and active; plus `(identifier_system, normalized_value)` and `organization_id` indexes. Uniqueness is **not** on `identifier_type`.

**Merge graph:** target of a merge must be ACTIVE (not already MERGED). Sequential A→B then B→C **can** form a chain; walker follows up to 8 hops. Direct merge of an already-merged source into a *different* target is rejected. Cycles rejected. Design uses this walker; do not invent a different graph.

**Verification:** `UNVERIFIED` / `VERIFIED` / `REJECTED` / `EXPIRED`. `REQUIRES_REVIEW` is a **match decision**, not an identifier status.

**Lifecycle:** `ANONYMOUS` / `ACTIVE` / `MERGED` / `RETIRED`. Authoritative for writes: ACTIVE or ANONYMOUS. No HTTP retire API today.

**Logging:** no HTTP body logger. Structlog redacts key `"nik"` only. Uvicorn access logs suppressed to WARNING. Successful MPI **reads are not success-audited** (DENY only).

**Rate limit:** global IP `120/min` (`RateLimitMiddleware`). No per-user MPI lookup limiter.

---

## 4. Name search

**FORBIDDEN.** No `LIKE`/`ILIKE` name, fuzzy name, browse-all, alphabetical directory, or autocomplete. Frozen: “search is not matching.” Name directory requires a separate privacy design.

---

## 5. Use-case decisions

| Identifier | Decision | Rationale |
|---|---|---|
| Organization-scoped MRN | **MVP** | Primary operational lookup; org-scoped uniqueness; least extra-national sensitivity |
| Canonical patient identity UUID | **MVP** | Trusted internal/deep-link after prior authorized access; backend still authorizes |
| NIK | **MVP** | Exact only; verified preferred for selection; high sensitivity; already in frozen MPI lookup |
| BPJS | **MVP** | Same as NIK |
| Passport | **DEFER** | Less common in first clinical workflow; same sensitivity class as national IDs |
| Drivers license / NATIONAL_ID / OTHER / EXTERNAL | **DEFER** | Not first-line Healthcare Web intake |
| Verified phone | **DEFER** | Shared/recycled numbers; exact-only would still be high false-positive risk |
| Verified email | **DEFER** | Same |
| Unrestricted name | **REJECT** | Enumeration |
| Prefix/contains/wildcard | **REJECT** | Enumeration |

Do not expose every MPI type merely because storage supports it.

---

## 6. Exact-match and normalization

Reuse frozen `normalize_identifier`. No new matching semantics.

| Type | Normalization (existing) | Match |
|---|---|---|
| MRN | collapse whitespace, trim | equality on `normalized_value` + selected org |
| NIK | digits only; 16 digits or 422 | equality; canonical system `id.nik` |
| BPJS | digits; length 10–16 or 422 | equality; canonical system `id.bpjs` |
| UUID | parse UUID or 422 | PK + org visibility + canonicalize |

**No** prefix, contains, regex, or fuzzy match.

**MRN case:** not case-folded today (whitespace only). Do not add case-folding in this design (would change frozen MPI semantics). Leading zeros are significant after trim.

**MRN system string:** frozen lookup requires `identifier_system` (often a local code such as `hospital-mrn`). Staff must not be asked for that. Healthcare Web lookup queries **`identifier_type = MRN` + selected `organization_id` + normalized value**. If multiple active rows (different systems, same normalized MRN) map to **different canonical identities** → ambiguous (see §12). Same canonical identity → one result.

**Body must not override org.** Frozen `identifier_organization_id` on `POST /mpi/identities/lookup` can substitute another org for MRN scope. The Healthcare Web lookup **ignores** any body org id. Scope is **only** `X-Organization-Id`.

---

## 7. Verified vs unverified

`find_active_identifier` today includes UNVERIFIED (excludes REJECTED/EXPIRED only).

| Type | UNVERIFIED | VERIFIED |
|---|---|---|
| MRN | **Selectable** after confirmation (operational id) | Selectable |
| NIK / BPJS | **Not** deterministic clinical selection. Outcome `review_required`. Registrar/clinician see “needs identity review”; IDENTITY_OFFICER may open MPI review later. Do not auto-select | Selectable after confirmation |
| UUID | N/A (identity resource) | Canonical identity if org-visible |

Never treat match-engine `REQUIRES_REVIEW` as confirmed identity. Lookup **must not** call `/mpi/match`, create candidates, or merge.

---

## 8. Authorization and roles

**Lookup permission:** existing `mpi.identity.read`. Do **not** invent `mpi.lookup.*`.

**Not** `clinical.*` (those gate chart sections). **Not** Audit-nav `clinical.condition.read`. Lookup UI follows `mpi.identity.read` for the **selected org**.

Purpose is **required** (PHI). Catalog only. Staff **must not** send `PATIENT_ACCESS` (403, already frozen on staff clinical routes). Workspace mapping:

| Workspace | `X-Purpose` |
|---|---|
| Registration | `REGISTRATION` |
| Clinical | `TREATMENT` |
| Identity | `IDENTITY_RESOLUTION` |
| Audit | `AUDIT` |

`EMERGENCY` / `CARE_COORDINATION` remain valid catalog values for later workspaces, not MVP chrome. `ADMINISTRATION` is not the default lookup purpose (org-admin IAM work ≠ patient search).

| Role (label only) | Should lookup/select? | Chart later? |
|---|---|---|
| CLINICIAN | Yes if `mpi.identity.read` | Yes, section-gated |
| REGISTRAR | Yes | Encounter/header only |
| IDENTITY_OFFICER | Yes | Header/MPI only, no clinical sections |
| AUDITOR | Yes **if** `mpi.identity.read` (catalog grants it) **and** purpose `AUDIT` | Read-only chart later if UI exposes it |
| ORG_ADMIN | Catalog includes `mpi.identity.read`. Admin workspace is **not** the lookup home. If they open Registration/Clinical, permission applies — **no role hardcode** |

Do not change role grants. Frontend hides lookup where `mpi.identity.read` is absent.

---

## 9. Tenant and facility

Lookup runs in **exactly one** selected organization: `X-Organization-Id` + `Principal.for_organization(selected_org)`. No cross-org union. No “exists in Hospital B” signal.

**Facility:** lookup is **organization-wide**. Do **not** filter identities by work facility. Clinical Read Core chart default is org-wide; work `X-Facility-Id` is command attribution, not identity visibility. Optional header may still be sent as work context; it must not shrink results.

---

## 10. Clinical Read alignment

Selection stores **canonical** `patient_identity_id` compatible with Clinical Read (`requested` vs `canonical_patient_identity_id`). Frontend **must not** walk merge chains. Backend lookup returns the survivor.

---

## 11. MERGED / RETIRED / ANONYMOUS

**MERGED:** identifier or UUID of X that merged into Y → return **Y** as the only selectable identity. Optional `resolved_from_merged: true` (boolean only; no merge graph). Do not offer X. Do not rewrite historical clinical rows.

**RETIRED:** identifier search → same as not found (`200` empty). Direct UUID of a retired identity → **409** (align Clinical Read; caller already has a UUID). Unresolvable merge chain (walker returns `None`) → treat as not selectable: identifier search empty; UUID 409.

**ANONYMOUS:** **MVP allow** when an exact org MRN (or UUID) hits `ANONYMOUS` / `TEMPORARY`. Show `identity_kind` and display label (`UNKNOWN-…` / `TEMP-…`). Needed for emergency/identify. No national identifiers expected. Defer richer anonymous-intake UX.

---

## 12. Cardinality

Unique active indexes imply at most one row per `(system, value[, org])`. Healthcare Web type-based MRN query can still yield multiple rows.

| Outcome | Behavior |
|---|---|
| 0 | `200` `{ outcome: "none", results: [] }` — unknown, other-org, retired-via-identifier, rejected identifier |
| 1 selectable | `200` `{ outcome: "one", results: [summary] }` — UI **confirmation card**, not silent auto-open chart |
| >1 distinct canonical ids | `200` `{ outcome: "ambiguous", results: [...≤5] }` — no auto-select; IDENTITY_OFFICER may use MPI later |
| >5 | `outcome: "ambiguous"`, results truncated, `truncated: true` — not a directory |

Never silently pick one of many.

---

## 13. Result DTO (PHI) and masking

Lookup responses **are PHI**.

**Include:** `patient_identity_id` (canonical), `requested_patient_identity_id` if different, `lifecycle_status`, `identity_kind`, `display_name` (given + family, or `display_label` if unnamed), `birth_date`, `administrative_sex`, org MRN **unmasked** (operational, same as Clinical Read header), `resolved_from_merged`, `identifier_verification` for the hit type, `review_required` boolean.

**Exclude:** full identifier list, NIK/BPJS/passport/phone/email values (even masked, unless the **lookup type** was that identifier — then return **masked** confirmation of the type searched, not other sensitive ids), addresses, merge internals, match scores, cluster member lists, clinical facts.

Minimum wrong-patient set: **name, DOB, sex/gender, org MRN**, plus visible **active organization** in the shell. Mask NIK/BPJS with existing `mask_identifier` if shown as confirmation of the query type.

Do not echo the raw lookup value in the response. Do not duplicate Clinical Read `PatientHeaderDTO` (no allergy flags, encounters).

---

## 14. GET vs POST (critical)

**Recommend `POST /api/v1/mpi/patients/lookup`** as a **read command**.

Identifier values in GET query strings leak to browser history, reverse-proxy access logs, APM, Referer, and screenshots. Frozen MPI already uses POST for `/mpi/identities/lookup` for this reason. This new route is **not** a mutation: no identity/match/merge writes.

Do not put MRN/NIK/BPJS in URLs.

---

## 15. Proposed API (not implemented)

```
POST /api/v1/mpi/patients/lookup
```

Headers: `Authorization`, `X-Organization-Id` (required), `X-Facility-Id` (optional, not a filter), `X-Purpose` (required catalog value), `X-Correlation-ID`.

Request body (header org is authority):

```json
{
  "lookup_type": "MRN | NIK | BPJS | PATIENT_IDENTITY_ID",
  "lookup_value": "string"
}
```

No `organization_id` in body.

Response `200`:

```json
{
  "outcome": "none | one | ambiguous | review_required",
  "truncated": false,
  "results": [ { "patient_identity_id": "...", "...": "..." } ]
}
```

Errors: `401` session; `403` no `mpi.identity.read` or forbidden purpose; `422` unknown type / failed normalization; `409` retired/unresolvable **UUID**; `429` later rate limit (generic message). Identifier miss is **not** 404.

Max results: **5**.

Implementation must reuse `normalize_identifier`, `find_active_identifier` / type+org query, `get_identity`, `_is_visible`, `resolve_canonical_identity`. **No** `/mpi/match`. **No** MPI state change.

`GET /mpi/identities/{id}` remains for identity officers; Healthcare Web selection should use this lookup (or UUID branch of it) so canonicalization is consistent.

---

## 16. Audit and rate limit

**Lookup ≠ chart.** Do not emit `CLINICAL_CHART_ACCESSED` on search.

Frozen MPI has **no** success-read audit. Implementation should add `PATIENT_LOOKUP_ACCESSED` (MPI `AuditAction`, not a PDP change) on completed lookup: metadata purpose, selected org, `lookup_type`, `outcome`, canonical id **only on hit** — **never** raw identifier, never NIK/BPJS. DENY already audited via `authorize`. Same event for none/one/ambiguous (outcome field). Do not implement in this pass.

**Rate limit:** keep global IP limit. Implementation should add a **per-principal + organization** lookup throttle (e.g. tens per minute). `429` UX: generic “try again later” — no remaining-count. Do not implement here.

---

## 17. URL, state, cache (frontend — not implemented)

**Lookup/selection routes:** no UUID required. Use existing `/app/registration` and `/app/clinical` placeholders. **PATIENT UUID IN URL for lookup = NO.**

**Future chart** (separate pass): frozen helper already allows `/app/clinical/patients/{canonicalUuid}` only. Backend remains authority. After logout/org-switch, in-memory selection is gone; UUID route must re-auth and re-authorize (404/403), never show cached PHI.

**Selected patient (memory only):** `canonicalPatientIdentityId`, safe display summary (name, DOB, MRN), `organizationId`, `selectedAt`. No identifier bag. Tenant-bound: if org id ≠ current org, discard.

**Do not persist** lookup inputs or results in `localStorage` / `sessionStorage` / URL / analytics. Shell may keep org/facility UUIDs in sessionStorage (already frozen); **patient PHI must not**.

**F5:** memory-only auth already forces re-login. Re-select patient. **P3 UX.** Do not persist PHI to survive refresh.

**TanStack:** **`useMutation`**, not a cached query. Reasons: POST body, no identifier in query keys, no refetch-on-focus, no automatic retries of PHI search, easy clear. Do **not** refetch lookup on window focus.

If any cache is used: key `["patient-lookup", organizationId]` holding **results only**, never raw input. Prefer none.

Retries: none on 401/403/404/409/422/429; bounded transient 5xx only (≤1), cautious.

Clear on: successful selection (clear input + mutation data), org switch, logout, 401, membership loss. Abort in-flight lookup on org switch and on new submit (`AbortSignal` + generation, same idea as `TenantLoadCoordinator`).

**Org-switch + late A response = P1 if it renders.** Prevention: abort + generation + commit only if `organizationId` still equals selected org. Never display Hospital A PHI under Hospital B.

**Rapid MRN A then B:** abort A; show B.

**Tabs:** patient state memory-only so a duplicated tab does not clone live PHI (tenant sessionStorage clone does not include patient). Assume duplicate tab starts with no selected patient.

**Query keys for later chart:** `["clinical-chart", organizationId, canonicalPatientId]` — out of this pass.

---

## 18. UX (not implemented)

Components (conceptual): `PatientLookupForm`, `LookupTypeSelector` (MRN / NIK / BPJS / UUID), `PatientLookupResult`, `PatientConfirmationCard`, `NoMatchState`, `AmbiguousMatchState`, in-memory `PatientSelectionContext`.

Explicit submit only — **no per-keystroke search**. Paste allowed; no clipboard helpers. Clear input after selection. No copy-sensitive-data control.

**Always confirmation card** before treating the patient as selected for future chart open (including exact single MRN). Visible: name, DOB, MRN, sex, identity kind if ANONYMOUS, **and** active organization chip.

Registrar no-match: optional later “Start registration” only if `mpi.identity.create`. Identity officer ambiguity: later MPI review, not merge from this screen. Clinician: no merge internals.

No recent-patients list. No today’s roster. No autocomplete.

Shared workstation: clear on logout/401/org switch. Banner of selected patient is future shell/chart work; lookup pass only needs confirmation + in-memory selection.

Frontend must not `console.log` lookup values or result objects. No analytics SDK. CSP unchanged.

---

## 19. Registration vs lookup vs matching

Lookup never creates a patient. Not-found is not registration. Matching (`POST /mpi/match`) is a separate IDENTITY_OFFICER/REGISTRAR tool, not this form.

---

## 20. New backend capability decision

**B — new endpoint required.**

Frozen `POST /api/v1/mpi/identities/lookup` is the wrong Healthcare Web contract:

1. Requires `identifier_system` (staff cannot supply org MRN system codes).
2. Does not canonicalize MERGED (Clinical Read does; selection would store obsolete X).
3. Returns full identifier arrays (excess PHI).
4. Uses 404 for miss (weaker uniform search semantics).
5. Allows `identifier_organization_id` body override.
6. Changing that frozen route would modify MPI public behavior — **forbidden**.

New `POST /api/v1/mpi/patients/lookup` wraps existing repository functions. No PDP change. No Wave1PolicyPDP / ProductAccessPDP / Clinical Read Core edits. No MPI matching mutation.

---

## 21. Migration 0019

**NOT REQUIRED** for MVP exact lookup. Org-scoped equality can use existing `organization_id` and unique active indexes. Optional later index on `(identifier_type, organization_id, normalized_value)` is a performance nicety, not a freeze blocker. Do not create 0019 in implementation unless measurement shows sequential scans at production volume.

---

## 22. Threat model

| Threat | Mitigation |
|---|---|
| Patient enumeration | Exact submit only; no name/prefix; bounded results; uniform empty for miss/cross-org; rate limit |
| Cross-org disclosure | Header org only; visibility check; no “exists elsewhere” |
| Identifier in URL/logs | POST body; no access-log body dump; no echo of raw value |
| Wrong patient | Confirmation card: name, DOB, MRN, sex, org chip |
| Stale lookup after org switch | Abort + generation + org-id guard (P1) |
| Ambiguous auto-select | Forbidden |
| Merged confusion | Return survivor only |
| Retired selection | Empty on identifier; 409 on UUID |
| Excess identifier disclosure | Minimal DTO |
| Permission misuse | `mpi.identity.read` + purpose; backend authoritative |
| Brute force | Existing IP limit + recommended per-user lookup limit |
| Browser cache / shared workstation | Memory-only PHI; clear on logout/org switch; no persist |
| Query-key leak | useMutation; no NIK/MRN in keys |
| Unverified national ID as identity | `review_required`, no auto-select |

---

## 23. Deferred

Passport/phone/email lookup; name search; recent patients; today’s roster; scheduling; silent-renew page; per-section chart; Patient Mobile; Platform Admin; autocomplete; clipboard helpers; changing frozen `/mpi/identities/lookup`.

---

## 24. Implementation next scope (when a later pass is authorized)

1. `POST /api/v1/mpi/patients/lookup` + tests (canonical MERGED, empty miss, org isolation, purpose, no mutation).
2. Optional `PATIENT_LOOKUP_ACCESSED` audit (no PHI in metadata).
3. Healthcare Web lookup form + confirmation + memory selection; reuse shell wipe/abort; `useMutation`; purpose by workspace.
4. **Stop before** Clinical Read chart UI, clinical forms, patient list, migration 0019, PDP edits.
