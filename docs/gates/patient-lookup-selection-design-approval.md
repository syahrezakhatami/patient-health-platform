# Patient lookup and selection — design approval gate

**Date:** 2026-08-27  
**Kind:** DESIGN APPROVAL — not implemented  
**Baseline:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Parent:** `ca675b5a41782732995a4021fb85af7b9b29d5b5` (`iam-shell-context-frozen`)  
**Alembic:** `20260814_0018` (one head). Migration **0019 not created**.  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, or push in this pass.

Design: `docs/architecture/patient-lookup-selection-design.md`.

---

## Explicit decisions

| Decision | Value |
|---|---|
| **PATIENT LOOKUP TRANSPORT** | **POST** `POST /api/v1/mpi/patients/lookup` (new read-command). Do **not** use GET query strings. Do **not** change frozen `POST /api/v1/mpi/identities/lookup`. |
| **SUPPORTED MVP IDENTIFIERS** | **MRN** (org-scoped), **NIK**, **BPJS**, **PATIENT_IDENTITY_ID** (UUID) |
| **NAME SEARCH** | **FORBIDDEN** |
| **LOOKUP SCOPE** | **ORGANIZATION-WIDE** (selected `X-Organization-Id` only) |
| **WORK FACILITY FILTER** | **NO** (work `X-Facility-Id` is not an identity filter) |
| **LOOKUP PERMISSION** | existing **`mpi.identity.read`**. No new permission. |
| **PURPOSE REQUIRED** | **YES**. Catalog values by workspace: Registration `REGISTRATION`; Clinical `TREATMENT`; Identity `IDENTITY_RESOLUTION`; Audit `AUDIT`. Staff `PATIENT_ACCESS` forbidden. Purpose is context, not a grant. |
| **MERGED IDENTITY** | Return **canonical survivor Y**; do not offer merged X; optional `resolved_from_merged`; no historical row rewrite |
| **RETIRED IDENTITY** | Identifier search: **same as not found** (`200` empty). Direct UUID: **409** (Clinical Read alignment) |
| **ANONYMOUS IDENTITY** | **Allow** when exact hit (typically org MRN or UUID); show kind/label; no national-id expectation |
| **AMBIGUOUS RESULTS** | **No auto-select**. `outcome: "ambiguous"`, max 5 rows; truncated flag if more |
| **PATIENT UUID IN URL** | **NO** for lookup/selection. Future chart path UUID remains a **separate** frozen helper (`/app/clinical/patients/{uuid}`) and is out of this implementation scope |
| **LOOKUP RESULT CACHE** | **No Query cache of PHI search.** **`useMutation`**. Memory-only selection. Clear on org switch, logout, 401, new search, selection. No `localStorage`/`sessionStorage` PHI. No refetch-on-focus |
| **AUDIT** | Do **not** emit `CLINICAL_CHART_ACCESSED`. Implementation should add **`PATIENT_LOOKUP_ACCESSED`** (success + miss + ambiguous) **without** raw identifiers. DENY already audited. Not implemented this pass |
| **MIGRATION 0019** | **NOT REQUIRED** |

---

## Additional locked rules

- Exact match only; reuse frozen MPI normalization.
- Unverified **NIK/BPJS** → `review_required`, not clinical auto-select. Unverified **MRN** may be confirmed.
- Lookup **must not** merge, match, or create MPI state.
- Confirmation card required before selection (name, DOB, MRN, sex, org chip).
- Stale Hospital A lookup must never render under Hospital B (**P1** if it did).
- Passport / phone / email: **DEFER**. Prefix/wildcard: **REJECT**.
- Recent patients / today’s roster / autocomplete: **DEFER / FORBIDDEN** as specified in the design.

---

## P0 / P1 / P2 / P3 (design findings)

| Severity | Notes |
|---|---|
| P0 | None |
| P1 | Using frozen `/mpi/identities/lookup` as-is would select MERGED X and allow body org override. **Mitigated by new endpoint + canonicalization + header-only org.** Org-switch × late lookup is P1 if unimplemented in the frontend pass |
| P2 | No success-read audit today; AUDITOR/ORG_ADMIN hold `mpi.identity.read` (permission-driven, privacy-sensitive). Inherited DENIED-audit rollback unchanged |
| P3 | F5 re-select patient; Docker `:9100` IAM lag inherited; optional lookup rate-limit not built yet |

No unresolved design P0. Implementation must include the P1 race guards.

---

## Implementation readiness

**PATIENT LOOKUP & SELECTION DESIGN = APPROVED FOR IMPLEMENTATION**

Next implementation scope (separate pass):

1. Backend `POST /api/v1/mpi/patients/lookup` reusing MPI repository + canonical resolver. Tests for org isolation, MERGED, miss/empty, purpose, 403.
2. Optional `PATIENT_LOOKUP_ACCESSED` audit without PHI values.
3. Healthcare Web lookup + confirmation + in-memory selection; shell abort/generation; `useMutation`; workspace purpose.
4. **Do not** implement Clinical Chart UI, Clinical Read Core calls, clinical forms, patient directory, migration 0019, or PDP/catalog grant changes.

---

## Forbidden this pass (observed)

No patient lookup endpoint, no UI, no chart, no forms, no 0019, no commit/tag/push.
