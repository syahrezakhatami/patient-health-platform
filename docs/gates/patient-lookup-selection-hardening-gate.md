# Patient lookup and selection — hardening gate

**Date:** 2026-08-27  
**Kind:** HARDENING GATE — not freeze  
**Baseline HEAD:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Parent:** `ca675b5a41782732995a4021fb85af7b9b29d5b5` (`iam-shell-context-frozen`)  
**Alembic:** `current == heads == 20260814_0018` (exactly one head)  
**Migration 0019:** not created  

This document is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, push, or freeze in this pass.

Authoritative design: `docs/architecture/patient-lookup-selection-design.md`.  
Approval: `docs/gates/patient-lookup-selection-design-approval.md`.  
Implementation: `docs/architecture/patient-lookup-selection-implementation.md`.

Dedicated tests:

- `backend/tests/integration/test_patient_lookup_hardening.py` (25)
- `apps/healthcare-web/src/hardening/patient-lookup-hardening.test.tsx` (9)
- existing implementation tests were not weakened

---

## Verdict

**PATIENT LOOKUP BACKEND = IMPLEMENTED**

**PATIENT SELECTION UI = IMPLEMENTED**

**PATIENT LOOKUP & SELECTION HARDENING = COMPLETE**

**PATIENT LOOKUP & SELECTION = NOT FROZEN**

**MIGRATION 0019 = NOT CREATED**

**CLINICAL CHART UI = NOT IMPLEMENTED**

**CLINICAL FORMS = NOT IMPLEMENTED**

**NAME SEARCH = NOT IMPLEMENTED**

**NO COMMIT / NO TAG / NO PUSH**

---

## 1. Baseline

| Item | Result |
|---|---|
| HEAD / tag | `1c502950011a168dbb139980ef758f2660561255` = `healthcare-web-shell-frozen` |
| Parent | `ca675b5a41782732995a4021fb85af7b9b29d5b5` is ancestor |
| Working tree | design + backend lookup + selection UI + implementation tests + this hardening pass |
| Frozen `POST /api/v1/mpi/identities/lookup` | unchanged (additive `POST /api/v1/mpi/patients/lookup` only) |
| Wave1PolicyPDP / ProductAccessPDP | not modified |
| Clinical Read Core | not modified |
| Alembic | one head `20260814_0018`; no `0019` files |

---

## 2. Route / request / response

Healthcare Web endpoint remains **POST** `/api/v1/mpi/patients/lookup`.

Request (`PatientLookupRequest`, `extra = forbid`): only `lookup_type`, `lookup_value`.

Response: `outcome`, `truncated`, `results[]` with approved minimal fields only.

---

## 3. Defects found and fixed

| Defect | Fix |
|---|---|
| Dedicated `/app/patients/select` silently defaulted to first workspace (`registration` → `REGISTRATION`) when the user could open several workspaces | Require explicit workflow selection when more than one lookup workspace is available. Single-workspace roles remain locked. Mapping stays the approved table. |
| TanStack mutation cache could retain lookup variables after org switch | `mutationKey: ["patient-lookup"]`, `gcTime: 0`, `clearPatientLookupMutations` on org switch / tenant reset |
| Late lookup callbacks could remain current after panel abort | `abortAndInvalidate()` on the **lookup** coordinator only (tenant `abort()` stays signal-only so org activation is not invalidated) |
| Ambiguous identifier rows had no deterministic SQL order | `ORDER BY patient_identity_id, id` |
| Lookup error fallback could render `error.message` | Generic `errors.generic` except known 409/429/403/422 |
| Structlog redaction omitted `lookup_value` / `identifier_value` / `bpjs` | Added to `_REDACT_KEYS` |

422 bodies already omit Pydantic `input` (`del exc` in `validation_handler`). Hardening tests prove raw NIK is not echoed.

---

## 4. Request-schema isolation

Extra body fields `organization_id`, `identifier_organization_id`, `tenant_id`, `facility_id`, `purpose`, `role`, `permission`, and extra `patient_identity_id` → **422** `validation_error`. Organization is never client-body authority.

Call graph: route passes header `organization_id` into the service; repository `find_active_identifiers_for_lookup` has **no** `facility_id` argument; lookup-value is used only for frozen `normalize_identifier`.

---

## 5. Header organization / facility

`X-Organization-Id` → membership → `Principal.for_organization(org)`.

Same patient identity is returned for `X-Facility-Id` A1, A2, and omitted. No `facility_id` predicate on identity rows. Work facility is attribution, not visibility.

---

## 6. Audience

`php-api` allowed when otherwise authorized. `php-patient`, `php-platform`, missing aud, wrong aud, mixed aud, malformed JWT, wrong signature → **401**. `PatientPrincipal` cannot reach repository lookup (staff router `require_staff_audience`).

---

## 7. Permission / purpose matrix

Permission remains `mpi.identity.read`. No role-name checks.

| Combination | Result |
|---|---|
| Clinical permission without `mpi.identity.read` (custom test role) | 403 |
| Catalog `ORG_ADMIN` | still has `mpi.identity.read`; permission remains authoritative |
| Valid catalog purpose + no `mpi.identity.read` | 403 |
| `mpi.identity.read` + invalid / missing purpose | 422 |
| `mpi.identity.read` + `PATIENT_ACCESS` | 403 `purpose_principal_mismatch` |
| `mpi.identity.read` + `TREATMENT` / `REGISTRATION` / `IDENTITY_RESOLUTION` / `AUDIT` | 200 |
| Whitespace / case (` treatment `, `IDENTITY-RESOLUTION`) | accepted via frozen `parse_purpose` |

Purpose does not grant `mpi.identity.read`. Invalid purpose does not emit `PATIENT_LOOKUP_ACCESSED`.

---

## 8. Exact match / normalization

Full exact normalized value matches. Prefix, suffix, substring, `%`, `_`, and regex-looking MRN values → `200` `none`. Short NIK/BPJS fail frozen length rules (**422**) without echoing the value. No `LIKE` / `ILIKE` / fuzzy / `/mpi/match`.

Normalization reuses frozen `normalize_identifier`. MRN: whitespace collapse/trim, not case-fold; leading zeros preserved (`00123-…`). Frontend does not apply a second normalizer.

---

## 9. Tenant isolation

Same MRN `00123-…` in Hospital A and B returns only the selected org’s patient.

NIK known only in B, lookup under A: `200` `outcome: none`, `results: []`. Same for BPJS. Unknown NIK and foreign NIK share that shape. No “exists elsewhere”, no foreign name, no foreign org id.

---

## 10. Canonicalization ordering

Production order:

1. Exact identifier candidate (equality, bounded)
2. Current-org visibility on the identifier-bearing identity (`_is_org_visible`, **no** platform bypass)
3. Frozen `resolve_canonical_identity` (max 8 hops)
4. Current-org visibility revalidated on the survivor
5. Minimal DTO

Global uniqueness is not authority.

### Cross-org adversarial matrix

| Shape | Result |
|---|---|
| A. foreign source X → local survivor Y | `none` (source not visible; no hop oracle) |
| B. local source X → foreign survivor Y | `none` (survivor not visible) |
| C. foreign source X → foreign survivor Y | `none` |
| D. local source X → local survivor Y | canonical Y, `resolved_from_merged` |

---

## 11. Merge walker / frozen MPI

Frozen MPI **rejects** merging into an already-merged **target**, and rejects a merged **source** unless it is the idempotent same survivor. Sequential **A → B** (B ACTIVE) then **B → C** (C ACTIVE) is allowed by frozen merge creation; the walker follows that chain.

Lookup **uses** that walker. It does not create chains, unmerge, or promise hops frozen MPI cannot persist. Defensive loop/depth remains the frozen walker (`MAX_SURVIVOR_HOPS = 8`). Corrupt A↔B cycle: UUID lookup **409** `identity_not_usable` (no identifier dump); not selectable.

Merged visible source X returns canonical Y only (`patient_identity_id`, status, label, MRN, summary are Y).

---

## 12. RETIRED / unknown UUID / ANONYMOUS

| Case | Result |
|---|---|
| Identifier → RETIRED only | `200` `none` |
| UUID of RETIRED | `409`; error payload `code` / `message` / `correlation_id` only |
| Unknown UUID vs foreign UUID | identical `200` empty |
| ANONYMOUS exact UUID | kind/label/temporary summary; no invented NIK/BPJS/MRN |

---

## 13. Verified / unverified / ambiguity

Unverified NIK/BPJS → `review_required`, `selectable: false`. Verified NIK → `one` selectable. Deterministic confirmed lookup does not prefer unverified national-id evidence. No match scoring. No implicit merge.

Ambiguity: 0 → `none`; 1 selectable → `one`; 2–5 → `ambiguous`; 6+ → `truncated`, max **5**, ordered by identity id. UI: no Select on ambiguous or review-required. No first-result auto-select. No pagination / directory.

---

## 14. Response minimization / masking / 422 privacy

Success DTO has only approved fields. Absent: full identifiers, raw NIK/BPJS, phone, email, address, merge operation, cluster ids, match score, clinical data, audit/provenance metadata, org secrets.

NIK/BPJS confirmation uses frozen `mask_identifier`. Short/malformed inputs are padded with `*`; they are not returned bare. Org MRN unmasked per design.

Submitted `lookup_value` is not in success, 409, 422, 429, or audit metadata. Framework 422 does not serialize `input`.

---

## 15. Logging / access log / audit

Application middleware does not log request bodies. Redaction keys now include `lookup_value`, `identifier_value`, `bpjs`. POST path contains no identifier.

Audit `PATIENT_LOOKUP_ACCESSED` on authorized executions (including zero-result). Metadata: `lookup_type`, `outcome`, `result_count`, `truncated`, purpose. Canonical `patient_id` only for outcome `one`. No raw MRN/NIK/BPJS. No `CLINICAL_CHART_ACCESSED`. Zero-result rows have null `patient_id`.

Success audit is recorded in the same request session as the lookup; serialization runs after audit staging. Inherited DENIED-audit rollback remains P2. Reverse-proxy body logging is an operations assumption; this pass does not add body logging.

---

## 16. Provenance / read-only / rate limit

Zero new `clinical_provenances`. Identity/cluster/match/merge/verification counts unchanged across lookup. Only expected write: `audit_events`.

Global IP limiter still wraps the app; lookup is not exempt (only `/health/live`). 429 body is `Too many requests` with no identifier. Per-principal lookup throttle remains **deferred P3**.

---

## 17. Frontend mutation PHI / selected patient / wipe

Raw lookup value lives in component state + in-flight mutation variables only. Not in `localStorage`, `sessionStorage`, URL, query keys, or console.

Selected patient fields: canonical id, org id, display name/label, DOB, sex, org MRN, kind, lifecycle, `selectedAt`. No NIK/BPJS, lookup input, full response, or audit data.

401 / logout / org switch / membership loss: `clearSensitiveClientState` / `clearPatientAndChartFilter` / mutation cache clear. Org switch clears **before** B context fetch. Org B context **failure** does not restore patient A.

Same-org race: B wins; generation discards A. Cross-org: A abort+invalidate; A is not rendered or selected under B. A→B→A: first-A response does not overwrite second-A. `AbortSignal` is passed to `fetch`.

Confirmation is required; no auto-select; no clinical navigation. Active organization remains visible in the shell chip and lookup panel.

---

## 18. Workspace-embedded lookup / generic route purpose

Registration / Clinical / Identity / Audit embed the **same** `PatientLookupPanel` (permission, purpose mapping, race, storage, confirmation). Admin has no panel.

Fixed mappings: Clinical → `TREATMENT`; Registration → `REGISTRATION`; Identity → `IDENTITY_RESOLUTION`; Audit → `AUDIT`.

**Generic `/app/patients/select`:** purpose is **not** free text and **not** a silent `TREATMENT` (or `REGISTRATION`) default for multi-workspace users. The user must pick a workspace they can already open; purpose is the approved mapping for that workspace. A registrar with only Registration is locked to `REGISTRATION`. Backend still validates catalog purpose, so a tampered frontend purpose cannot grant capability.

This is consistent with the approved workspace-purpose table. Hardening is **not** blocked on generic-route purpose.

---

## 19. Permission-gated UI / UUID URL / history / tabs / XSS / a11y

Lookup UI requires `mpi.identity.read` in the selected org. Switching to an org without it hides the form and clears selected patient.

No `/patients/{uuid}` in this pass. `APP_PATHS.patientSelect` is `/app/patients/select`. Memory-only selection; Back after logout/org-switch cannot restore PHI from storage. No `BroadcastChannel` / IndexedDB sharing of selected patient.

Patient names render through React text. `<script>`, quotes, and RTL names do not execute. No `dangerouslySetInnerHTML` / `innerHTML` / `eval` in `src/patient`. No PHI `console.*`. `aria-live` uses status strings, not raw identifiers.

No focus/reconnect refetch. `retry: false` on the mutation; 401/403/409/422/429 are not retried.

---

## 20. OpenAPI / indexes / quality

OpenAPI generated from **source** FastAPI (not `:9100`). `--check` export and types: **ok**.

| Lookup | Index / access path |
|---|---|
| NIK/BPJS | unique `uq_patient_identifiers_global_active` `(identifier_system, normalized_value)` WHERE org IS NULL |
| MRN | org-scoped `ix_patient_identifiers_organization_id` + equality on type/value; not a global directory scan |
| UUID | PK `patient_identities.id` |

Bounded `LIMIT 6`. No sequential full-table patient directory. **Not index-blocked.** No migration 0019.

| Gate | Result |
|---|---|
| Frontend tests | **91 passed**, 20 files (was 81 / 19) |
| Frontend lint | 0 errors, 0 warnings (`oxlint --deny-warnings`) |
| Typecheck | pass |
| Production build | pass |
| `npm ci` + `npm audit --omit=dev` | 0 vulnerabilities |
| Backend pytest | **442 passed** (was 417) |
| ruff check/format | pass |
| mypy app | pass |
| Alembic | `20260814_0018`, one head |
| Health | live 200, ready 200, postgres/redis/object_storage ok |
| Docker `:9100` lookup | **404** — P3 image lag; not rebuilt |
| Secret/PHI scan | synthetic fixtures only; no JWT/OIDC/DB secrets in this diff |

---

## 21. P0 / P1 / P2 / P3

| Severity | Notes |
|---|---|
| P0 | None |
| P1 | Cross-org NIK/BPJS concealment, canonical hop matrix, body tenant override, audience, raw identifier return, late Org A PHI under Org B — **tested; blocked by implementation + this pass** |
| P2 | 422/audit/log identifier echo **tested absent**; selected-patient wipe on 401/logout/org-switch **including failed B context**; unverified national id not selectable; ambiguous not auto-selected; generic route purpose now **explicit workspace choice** (no silent default) |
| P3 | Per-principal lookup throttle deferred; F5 re-select; Docker `:9100` lag; source OpenAPI environment (backend venv Python); inherited DENIED-audit rollback |

No unresolved security/policy blocker. Do not freeze in this pass.

---

## 22. Reverse-proxy / Docker assumptions

Access logs of the POST URL do not contain identifiers. Operators must not enable request-body logging at the proxy for this route. Docker image on `:9100` does not yet serve `POST /api/v1/mpi/patients/lookup` (404). Source OpenAPI remains authoritative.
