# Manual Vital Signs — final pre-implementation contract

**Date:** 2026-08-28 (integrity correction 2026-08-29)
**Kind:** FINAL PRE-IMPLEMENTATION CONTRACT — docs only
**Baseline HEAD:** `60eafc5b8454867722cf8738a0f636bb866d3350`
**Parent OGP frozen:** `d449ffed6bd314edac3964f1c6c69bb51955a8db` (`organization-governance-profile-foundation-frozen`)
**Alembic:** `current == heads == 20260814_0020` (Manual Vitals migration **`20260814_0021` assigned**, **not created**)

This document freezes implementation-critical contracts. Implementation must not invent these decisions.

**Integrity correction (2026-08-29):** prior raw-key `scope` string format exceeded frozen OGP `scope String(128)` for the full five-entry subset; replaced with compact scope fingerprint bound to immutable `governance_profile_version_id`.

---

## Verdict

```
MANUAL VITAL SIGNS
FINAL PRE-IMPLEMENTATION CONTRACT = COMPLETE

MANUAL VITAL SIGNS =
READY FOR IMPLEMENTATION
```

Gate B/C remain pending — not implementation blockers.

---

## 1. Provider catalog architecture

```
MANUAL VITALS PROVIDER CATALOG =
STATIC APPLICATION-OWNED IMMUTABLE CATALOG
```

| Decision | Value |
|---|---|
| Storage | static Python module/constants — **no terminology database** |
| Future location | `backend/app/modules/clinical/domain/vital_signs_catalog.py` (or repository-equivalent) |
| Forbidden | `terminology_catalog`, `loinc_codes`, `ucum_units`, `clinical_terms`, generic terminology admin API, site-defined terminology rows |
| Authority | server catalog is sole LOINC/UCUM authority at runtime |

**Label vs semantics:** pure UI localization changes do **not** require a new provider catalog version if LOINC code, canonical unit, and measurement semantics are unchanged.

**Material catalog change** (LOINC, canonical unit, semantics) requires **new provider catalog version** and provider review. Do not mutate `manual-vitals-mvp-v1` in place after provider catalog freeze.

---

## 2. Provider catalog version

```
PROVIDER CATALOG VERSION = manual-vitals-mvp-v1
```

This is **provider product catalog version** — not LOINC version, SATUSEHAT version, UCUM version, or site policy version.

---

## 3. Provider-supported entries (exact five)

Stable keys are machine-safe identifiers. Display labels are never authority.

### 3.1 `heart_rate`

| Field | Value |
|---|---|
| key | `heart_rate` |
| category | `VITAL_SIGNS` |
| code_system | `http://loinc.org` |
| code | `8867-4` |
| canonical concept | Heart rate |
| value_type | `NUMERIC` |
| unit_system | `http://unitsofmeasure.org` |
| unit_code | `/min` |
| display_unit | beats/min |
| provider catalog version | `manual-vitals-mvp-v1` |

### 3.2 `respiratory_rate`

| Field | Value |
|---|---|
| key | `respiratory_rate` |
| category | `VITAL_SIGNS` |
| code_system | `http://loinc.org` |
| code | `9279-1` |
| canonical concept | Respiratory rate |
| value_type | `NUMERIC` |
| unit_system | `http://unitsofmeasure.org` |
| unit_code | `/min` |
| display_unit | breaths/min |
| provider catalog version | `manual-vitals-mvp-v1` |

### 3.3 `body_temperature`

| Field | Value |
|---|---|
| key | `body_temperature` |
| category | `VITAL_SIGNS` |
| code_system | `http://loinc.org` |
| code | `8310-5` |
| canonical concept | Body temperature |
| value_type | `NUMERIC` |
| unit_system | `http://unitsofmeasure.org` |
| unit_code | `Cel` |
| display | provider-approved UI representation only |
| limitation | measurement site/method **NOT** captured in MVP |
| UI prohibition | must not imply oral / axillary / tympanic / rectal / other site or method |

### 3.4 `body_weight`

| Field | Value |
|---|---|
| key | `body_weight` |
| category | `VITAL_SIGNS` |
| code_system | `http://loinc.org` |
| code | `29463-7` |
| value_type | `NUMERIC` |
| unit_system | `http://unitsofmeasure.org` |
| unit_code | `kg` |
| display_unit | kg |

### 3.5 `body_height`

| Field | Value |
|---|---|
| key | `body_height` |
| category | `VITAL_SIGNS` |
| code_system | `http://loinc.org` |
| code | `8302-2` |
| value_type | `NUMERIC` |
| unit_system | `http://unitsofmeasure.org` |
| unit_code | `cm` |
| display_unit | cm |

### 3.6 Not in provider MVP catalog

Blood Pressure (terminology evidence documented separately; **write workflow DEFERRED**), SpO₂ (**DEFERRED**), BMI, pain score, GCS, other observations.

---

## 4. Site terminology configuration

### 4.1 Site must not send terminology

Future site configuration must **NOT** accept arbitrary LOINC code, UCUM code, unit string, category, or value type from clients.

Site selects **provider catalog entry keys only**. Backend derives all clinical terminology from immutable provider catalog.

### 4.2 Site subset requirement

Organizations may enable a **subset** of the five provider-supported keys. Examples:

- Org A: `heart_rate`, `body_temperature`, `body_weight`
- Org B: all five keys

All five are not required.

### 4.3 Site subset storage

```
SITE SUBSET STORAGE =
VERSIONED OGP GOVERNANCE POLICY (schema v2)
```

Site subset is stored in **organization governance profile version** policy document — not a mutable standalone terminology allowlist table.

Preserves: version history, `changed_by`, `changed_at`, `reason`, effective policy reconstruction.

---

## 5. OGP policy schema evolution

Frozen OGP foundation: **policy schema version 1** (`GovernancePolicyDocumentV1`). Do **not** mutate v1 semantics silently.

```
OGP POLICY SCHEMA FOR MANUAL VITALS = version 2
```

Introduce `GovernancePolicyDocumentV2` with `schema_version: 2`. v1 profiles remain valid unchanged. Organizations on v1 without `manual_vital_signs` block → Manual Vitals **DENIED** without breaking non-governed capabilities. **No organization bootstrap/migration required.**

### 5.1 Manual Vitals policy block (bounded, strongly typed)

```yaml
schema_version: 2
encounter_status_policy: ...      # same bounded blocks as v1
backdating_policy: ...
late_documentation_policy: ...
correction_policy: ...
manual_vital_signs:
  catalog_version: manual-vitals-mvp-v1
  approved_measurements:
    - heart_rate
    - body_temperature
```

Rules:

- `approved_measurements`: unique list/set of provider entry keys only
- unknown key → profile validation/publish **rejection**
- empty list → Manual Vitals **DENY**
- absent block (v1 profile or v2 without block) → Manual Vitals **DENY**
- unknown `catalog_version` → **DENY**

### 5.2 Policy configuration ≠ approval ≠ activation

| Layer | Meaning |
|---|---|
| **Policy configuration** | published profile version declares intended subset |
| **Approval evidence** | append-only human governance record binding exact subset |
| **Feature activation** | `organization_feature_activations` state = `ACTIVE` |

Policy alone does **not** prove clinical approval. Runtime requires all three layers plus provider/entitlement/permission checks.

---

## 6. Approval evidence binding (inspected frozen OGP)

### 6.1 Frozen `governance_approval_evidence` columns (0020)

Relevant fields: `organization_id`, `feature_id`, `provider_feature_version`, `governance_profile_version_id`, `approval_type`, `scope` (String **128**), `decision_by_name`, `recorded_by_user_id`, `approval_date`, `approver_role_category`, `expires_at`, `status`.

Platform OGP API supports **record** only — no arbitrary capability creation API (`platform_governance.py`: list + transition only).

`approval_type` is a free string (max 128) in frozen OGP — not a closed enum. Minimum Manual Vitals site clinical approval convention:

```
approval_type = CLINICAL_GOVERNANCE
```

### 6.2 Evidence storage decision

```
APPROVAL EVIDENCE SUBSET BINDING =
REUSE EXISTING scope COLUMN (no new evidence table or column in 0021)
```

**Rejected:** raw measurement-key list in `scope` — full five-entry format exceeds `String(128)` (132 characters for prior proposed format). **No truncation. No OGP 0020 column widening.**

Approval binds: **organization + feature_id + provider_feature_version + governance_profile_version_id + approval_type + compact scope fingerprint**. The immutable profile version is the source from which the exact approved measurement subset is reconstructed.

### 6.3 Canonical approval payload (logical)

Only these fields participate in Manual Vitals terminology-subset approval fingerprint:

```json
{
  "catalog_version": "manual-vitals-mvp-v1",
  "approved_measurements": ["body_height", "body_temperature", "body_weight", "heart_rate", "respiratory_rate"]
}
```

Rules:

- `approved_measurements` sorted **lexicographically ascending** before serialization
- duplicates impossible after policy validation
- no display labels, LOINC, or UCUM in payload

### 6.4 Canonical serialization

Deterministic canonical JSON:

- UTF-8
- object keys sorted (`sort_keys=True`)
- compact separators `(",", ":")` — no insignificant whitespace
- equivalent to Python: `json.dumps(payload, separators=(",", ":"), sort_keys=True, ensure_ascii=False)`

Example canonical bytes for full MVP subset (147 bytes — **not stored in `scope`**):

```
{"approved_measurements":["body_height","body_temperature","body_weight","heart_rate","respiratory_rate"],"catalog_version":"manual-vitals-mvp-v1"}
```

### 6.5 Scope fingerprint (stored in `scope`)

```
scope = <catalog_version>#sha256:<64-lowercase-hex>
```

Where `<64-lowercase-hex>` = SHA-256(canonical approval payload UTF-8 bytes).

**Frozen prefix:** catalog version literal + `#sha256:` + lowercase hex digest.

Example (full five-entry subset):

```
manual-vitals-mvp-v1#sha256:7f034c6ea0c1b6adb3f030aca106d4829eb1fc26528afac207b63e2085819eef
```

| Format | Length |
|---|---|
| Maximum for this design | **92 characters** |
| Prior rejected raw-key format (5 entries) | 132 characters (**exceeds 128**) |

Subset examples produce the same **92-character** `scope` length (catalog prefix + `#sha256:` + 64 hex); digest differs.

### 6.6 Scope hash is not sole authority

Runtime approval matching requires **all**:

1. same `organization_id`
2. `feature_id = manual_vital_signs_write`
3. `provider_feature_version` matches registered capability (e.g. `1.0.0`)
4. `governance_profile_version_id` matches effective immutable published profile version used for policy resolution (**exact match** — no silent carry between profile versions in MVP)
5. `approval_type = CLINICAL_GOVERNANCE`
6. `status = APPROVED`, not expired, not withdrawn/superseded per frozen OGP semantics
7. stored `scope` equals scope fingerprint **recomputed from** the effective profile version's `manual_vital_signs` policy block

Do **not** treat the hash string alone as approval authority without profile version binding and policy recomputation.

### 6.7 Exact subset semantics

Approval for `heart_rate` + `body_temperature` does **not** approve `body_weight`. If `approved_measurements` changes, scope fingerprint changes. Existing evidence does not automatically cover the new subset.

### 6.8 Profile version binding

Because evidence is bound to `governance_profile_version_id`, a different effective governance profile version requires evidence appropriate to **that exact profile version**. Approval portability across policy-only changes is **out of scope for MVP**.

---

## 7. Catalog version mismatch

If site policy references `manual-vitals-mvp-v1` but provider runtime expects `manual-vitals-mvp-v2`:

- **do not** silently carry approval forward
- site governance requirement **unsatisfied** until explicit compatibility/reapproval decision

---

## 8. Site activation runtime intersection

Manual Vitals write availability requires **ALL**:

1. provider capability row exists
2. provider state = `AVAILABLE`
3. `governance_required = true`
4. entitlement permits feature
5. required deployment gates satisfied (per capability metadata)
6. organization feature activation state = `ACTIVE`
7. effective published OGP policy exists with `schema_version >= 2` and non-empty `manual_vital_signs.approved_measurements`
8. policy `catalog_version` matches provider-supported catalog version in runtime
9. required `CLINICAL_GOVERNANCE` approval evidence whose `scope` fingerprint matches policy recomputation for the bound profile version
10. actor has `clinical.observation.create`
11. request-specific patient / encounter / facility / numeric / catalog-key validation passes

Any missing requirement → **deny**.

Missing Manual Vitals policy, empty subset, unknown catalog version, unknown measurement key → **deny** (fail closed).

---

## 9. Provider capability registration

| Item | Status |
|---|---|
| Production registry | **EMPTY** |
| `manual_vital_signs_write` | **NOT REGISTERED** |
| Provider clinical safety review | **PENDING** |

### 9.1 Registration mechanism (frozen)

```
PRODUCTION REGISTRATION MECHANISM =
DETERMINISTIC ALEMBIC SEED (Option A)
```

OGP foundation has **no** platform API to create provider capabilities — only list + state transition. First governed clinical capability uses reproducible migration seed.

| Phase | Registration |
|---|---|
| Engineering / hardening | **no production seed** — tests use controlled fixture insert |
| Provider release freeze (Gate B complete) | deterministic Alembic seed in migration **`20260814_0022`** (parent `20260814_0021`) |

Rationale: keeps engineering migration `0021` publishable without registration; seed authored only when provider release gate passes.

Alternative rejected: platform create API (not available in frozen OGP).

### 9.2 Expected production row (when Gate B completes)

| Field | Value |
|---|---|
| `feature_id` | `manual_vital_signs_write` |
| `feature_version` | `1.0.0` |
| `provider_state` | `AVAILABLE` |
| `governance_required` | `true` |
| `frozen_release_tag` | assigned at provider capability freeze pass |

Also seed `provider_capability_required_gates` (see §10). **No** site activation rows, **no** approval evidence generated by migration.

**Provider capability version (`1.0.0`) is separate from provider catalog version (`manual-vitals-mvp-v1`).**

---

## 10. Required deployment gates

Per frozen OGP design (`organization-governance-profile-design.md` §8), deployment gates are **capability-declared** via `provider_capability_required_gates`.

For `manual_vital_signs_write` at provider registration seed:

| Required gate | Rationale |
|---|---|
| `CONTROLLER_PROCESSOR_ASSESSMENT` | first governed clinical PHI write capability |
| `DPA` | first governed clinical PHI write capability |

Resolver checks org-level gate state rows. These are **deployment prerequisites** (controller/processor assessment, DPA satisfaction) — **not** site clinical terminology approval and **not** per-request clinical sign-off.

---

## 11. Write request contract

### 11.1 Terminology authority

```
WRITE REQUEST TERMINOLOGY AUTHORITY = SERVER CATALOG
CLIENT SUPPLIES LOINC = NO
CLIENT SUPPLIES UNIT = NO
CLIENT SUPPLIES measurement_key = YES
```

### 11.2 Frozen create DTO

```json
{
  "expected_patient_identity_id": "<uuid>",
  "encounter_id": "<uuid>",
  "measurement_key": "heart_rate",
  "value": 72,
  "effective_at": "2026-08-28T10:15:00+07:00"
}
```

Header: `Idempotency-Key` (required)

Server derives at mutation time (never trusts prior catalog response):

- `category = VITAL_SIGNS`
- `code_system`, `code`, `code_display`
- `unit_system`, `unit` (canonical UCUM code)
- `value_type = NUMERIC`

### 11.3 Product routes (Manual Vitals product path)

Dedicated constrained routes — generic `POST /clinical/observations` remains separate:

| Method | Path |
|---|---|
| GET | `/api/v1/organizations/{org_id}/clinical/manual-vitals/measurements` |
| POST | `/api/v1/organizations/{org_id}/clinical/manual-vitals/measurements` |

GET returns **intersection** of provider-supported keys and organization-effective subset (only keys usable in ordinary clinical workflow). POST validates `measurement_key` against server catalog + effective policy at mutation time.

Backend write validation **never** trusts catalog data returned earlier to the frontend.

---

## 12. Idempotency

Table: `clinical_observation_write_idempotency` (feature-specific; do not reuse note or governance idempotency tables).

### 12.1 Fingerprint material

SHA-256 over canonical JSON (`sort_keys=True`, compact separators):

| Key | Source |
|---|---|
| `expected_patient_identity_id` | request UUID string |
| `encounter_id` | request UUID string |
| `measurement_key` | request key |
| `value` | canonical validated decimal string (see §12.2) |
| `effective_at` | offset-aware ISO-8601 via `datetime.isoformat()` after repository timezone normalization |
| `provider_catalog_version` | active provider catalog version at write time |

No client-supplied LOINC/unit in fingerprint.

### 12.2 Decimal validation order (NO SILENT ROUNDING)

1. parse as `Decimal` using repository/Pydantic safe mechanism (`parse_decimal` or equivalent)
2. reject NaN
3. reject positive/negative Infinity
4. validate total precision compatible with `Numeric(14,4)` (max 14 digits, max scale 4) — reject values requiring DB rounding/overflow
5. inspect submitted decimal **scale** (fractional digit count)
6. if scale > 4 → **REJECT 422** (e.g. `1.23456` is rejected — **not** rounded to `1.2346`)
7. only after validation → derive canonical semantic representation for fingerprint/persistence
8. persist using existing `Numeric(14,4)` contract

**Forbidden:** quantize-before-reject; any silent rounding.

### 12.3 Semantic decimal fingerprint canonical form

After steps 1–6 pass, derive canonical decimal text for idempotency:

- use `Decimal.normalize()` to remove insignificant trailing fractional zeros
- emit non-exponent plain decimal string (no `float`, no scientific notation)
- special-case zero consistently: `Decimal("0.0000")` → `"0"`

Examples:

| Submitted (valid) | Canonical fingerprint text |
|---|---|
| `1`, `1.0`, `1.00`, `1.0000` | `"1"` |
| `1.2300` | `"1.23"` |
| `0.0000` | `"0"` |

`1.23456` → **rejected before normalization** (step 6).

---

## 13. Observation persistence

Persist using existing Observation domain/fields:

- patient identity from encounter binding
- encounter, category `VITAL_SIGNS`, LOINC concept, numeric value, UCUM unit
- `effective_at`, server `recorded_at`, recorder, status `FINAL`

No shadow vital record. Audit/provenance capture where frozen architecture supports: provider feature version, provider catalog version, OGP profile version id, measurement key — prefer audit/provenance metadata over Observation schema duplication.

---

## 14. Policy / provider / entitlement change at submit

Frontend cache is never authority. Server resolves **current** state at mutation time:

| Change while form open | Expected |
|---|---|
| site policy removes measurement key | **deny** |
| provider becomes SUSPENDED/RETIRED | **deny** |
| entitlement revoked | **deny** |
| `clinical.observation.create` revoked | **deny** |
| approval evidence withdrawn/expired | **deny** |
| catalog version mismatch | **deny** |

---

## 15. Frontend authority model

Healthcare Web Manual Vitals:

- selected patient required
- effective feature context must show Manual Vitals available
- effective site subset loaded from server
- only site-active provider-supported keys shown
- no local bypass of governance/catalog
- reuse Clinical Note PHI safety: memory-only values, no localStorage/sessionStorage for clinical value, navigation guards, 401 wipe, `retry: false`, late-response protection, generation capture

---

## 16. Migration sequencing

| Revision | Parent | Alembic DDL scope | When |
|---|---|---|---|
| `20260814_0021` | `20260814_0020` | `clinical_observation_write_idempotency` table + constraints/indexes/immutability protections as required by design | engineering implementation start |
| `20260814_0022` | `20260814_0021` | deterministic seed: `manual_vital_signs_write` + `provider_capability_required_gates` | **only** when provider release gate (Gate B) passes |

**0021 must NOT seed** `manual_vital_signs_write` while Gate B is PENDING.

**0021 must NOT create:** `vital_signs`, terminology tables, BP tables, AI tables, facility override tables, evidence schema changes.

**APP_DML GRANTS = OUTSIDE ALEMBIC** per repository convention. Update `backend/scripts/grant_dev_privileges.sql` during implementation — **do not** execute GRANT/REVOKE inside migration `0021` unless a separate architectural decision changes the frozen convention.

### 16.1 Planned `clinical_observation_write_idempotency` app_dml privileges

Expected (subject to exact implementation design):

| Privilege | Allowed |
|---|---|
| SELECT | yes |
| INSERT | yes |
| UPDATE | no |
| DELETE | no |
| TRUNCATE | no |

Policy schema v2 is application validation against existing JSONB profile column — **no 0021 DDL** for policy evolution.

---

## 17. Gate statuses (unchanged)

| Gate | Status |
|---|---|
| Provider engineering (Gate A) | **APPROVED FOR IMPLEMENTATION** |
| Provider release (Gate B) | **PENDING** — provider clinical safety review |
| Site activation (Gate C) | **PENDING** — 0 site-approved entries |

---

## 18. Findings

| Severity | Item |
|---|---|
| **P0** | none |
| **P1** | none |
| **P2** | inherited DENIED-audit rollback |
| **P3** | provider clinical review pending; site approvals pending; correction UI deferred; BP workflow deferred; SpO₂ deferred; governance rate-limiting deferred |

Gate-classified (not P1):

- `PROVIDER_RELEASE_GATE` = PENDING
- `SITE_ACTIVATION_GATE` = PENDING

---

## 19. Explicit non-actions

No production code or migration in contract passes. Provider registration remains absent until Gate B.

---

## Sources

- Frozen OGP: `backend/alembic/versions/20260814_0020_organization_governance_foundation.py`
- Frozen policy schema: `backend/app/modules/governance/domain/policy_schema.py`
- Frozen approval evidence: `backend/app/modules/governance/domain/models.py`, `governance_schemas.py`
- Frozen resolver: `backend/app/modules/governance/domain/resolver.py`
- `docs/architecture/observation-vital-signs-write-workflow-design.md`
- `docs/gates/observation-vital-signs-provider-site-gate-reconciliation.md`
