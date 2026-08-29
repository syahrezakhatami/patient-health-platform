# Observation / Vital Signs write workflow — architecture & security design

**Date:** 2026-08-27 (reconciled 2026-08-28 post-OGP)
**Kind:** DESIGN ONLY — not implementation
**Pass:** Terminology & Observation write safety contract; post-OGP provider/site gate reconciliation
**Baseline HEAD:** `d449ffed6bd314edac3964f1c6c69bb51955a8db` (`organization-governance-profile-foundation-frozen`)
**Parent OGP:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)
**Software capability parent:** `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`)
**Alembic:** `current == heads == 20260814_0020` (OGP foundation; Observation write migration **UNASSIGNED**; planned next `20260814_0021`)

This document designs **manual Vital Signs entry** that persists as native **Observation** records (`category = VITAL_SIGNS`). It does not authorize implementation, commit, tag, push, a `vital_signs` table/domain, Clinical Read Core / MPI / ProductAccessPDP / Wave1PolicyPDP changes, Condition/Medication/Allergy/lab/Procedure writes, AI, device ingestion, BP entry, Observation correction/EIE UI, or generic unrestricted Observation authoring.

This is not a HIPAA, ISO 27001, or SOC 2 certification.

**Readiness (post-OGP reconciliation):**

```
MANUAL VITAL SIGNS ENGINEERING DESIGN = APPROVED FOR IMPLEMENTATION
PROVIDER PRODUCTION REGISTRATION = PENDING PROVIDER RELEASE / CLINICAL SAFETY GATE
SITE ACTIVATION = PENDING SITE CLINICAL / TERMINOLOGY APPROVAL
```

Three independent gates — see `docs/gates/observation-vital-signs-provider-site-gate-reconciliation.md`:

| Gate | Question | Status |
|---|---|---|
| **A. Provider engineering** | May engineering implement/test? | **APPROVED FOR IMPLEMENTATION** |
| **B. Provider release** | May provider register production capability? | **PENDING** provider clinical safety review |
| **C. Site activation** | May Organization X activate/use? | **PENDING** — 0 site-approved entries |

**Frozen principle:** `SITE APPROVAL != PROVIDER SOFTWARE IMPLEMENTATION APPROVAL`

Candidate / evidence package (not site approval):

- `docs/architecture/vital-signs-terminology-candidate-catalog.md`
- `docs/gates/vital-signs-terminology-human-approval.md`

```
TERMINOLOGY CANDIDATE CATALOG = READY FOR HUMAN DECISION
SITE-APPROVED TERMINOLOGY ENTRIES = 0
PROVIDER VITAL CATALOG VERSION (proposed) = manual-vitals-mvp-v1
```

Finding LOINC/UCUM codes or SATUSEHAT mappings is **not** site clinical approval. Safety contracts below remain implementation-exact.

**Source version note:** LOINC download/release **2.83** (2026-08-19). LOINC FHIR Terminology Service may still report **2.82** until updated — do not cite FHIR TS as 2.83 without re-verification. Provider engineering subset adopts SATUSEHAT national-profile units for HR/RR (`/min`); provider release gate still records provider clinical safety review **PENDING**.

---

## 1. Baseline verification

| Item | Result |
|---|---|
| HEAD | `d449ffed6bd314edac3964f1c6c69bb51955a8db` |
| Tag | `organization-governance-profile-foundation-frozen` → same SHA |
| Parent OGP | `c3590dd142f60a79aed3d4f042ff1c505cb2371c` |
| Clinical Note | `c55d259180c4864b56ea40e4c24833c9cd438d68` (`clinical-note-write-frozen`) — unchanged |
| Branch | `main` == `origin/main` |
| Alembic | `20260814_0020` (OGP); Observation migration **UNASSIGNED** (planned `20260814_0021`) |
| Provider capability registry | **EMPTY** — no `manual_vital_signs_write` row |
| Frozen Note Write / Chart UI / Clinical Read / Lookup / Shell / IAM / MPI / Product Access / PDPs / Observation production | unchanged by this design pass |

---

## 2. Hard invariant — vitals remain Observation

**DO NOT** introduce: `vital_signs` table, VitalSign ORM, `/api/v1/clinical/vitals`, duplicate persistence.

UI label “Vitals” is presentation only. Persistence: `observations` with `category = VITAL_SIGNS`.

Wave 2B architecture already forbids a separate `vital_signs` table (`FORBIDDEN_TABLES`).

---

## 3. Findings classification (corrected)

| Item | Classification |
|---|---|
| Historical `patient_identity_id` not rewritten after MPI merge | **Frozen clinical/MPI invariant** — **not P2** |
| Observation create uses exact `encounter.patient_identity_id == identity.id` (no cluster same-person) | **P1 gap** — insufficient for historical merged encounters; target: cluster-aware same-person while preserving stored historical identity |
| DENIED-audit rollback with `ForbiddenError` | **Inherited P2** |
| No enforced vital code+unit catalog | **P1 / blocking** for this capability |
| Facility header mismatch / absent-header widening on Observation create | **P1 gap** vs Note Write safety |
| No Observation create idempotency | **P1 gap** for Chart write |
| Free-string units; no category/code/`effective_at` indexes; grants outside Alembic | **P3** |

---

## 4. Terminology infrastructure inventory (source)

| Asset | Present? |
|---|---|
| Terminology tables / registry / service | **No** |
| Migrations seeding clinical code catalogs | **No** |
| LOINC / UCUM packages or seed scripts | **No** |
| Observation code allowlist | **No** |
| Unit allowlist / unit-system field | **No** |
| Wave 2A terminology stub | **Yes** — `app/modules/clinical/domain/terminology.py` (`CodeableConcept`: `system` + `code` + optional `display`) |
| Product-native governed Vital Signs catalog | **No** |

Conclusion: there is **no** repository place that already governs Vital Signs codes/units. Only a syntax stub.

**In-repo LOINC appearance:** test fixture only — `http://loinc.org` / `8867-4` / unit `beats/min`. **Not** catalog authority.

---

## 5. Observation coding contract (actual)

Stored columns:

| Column | DB | Null | Notes |
|---|---|---|---|
| `code_system` | `String(128)` | NOT NULL | length > 0 check |
| `code` | `String(64)` | NOT NULL | length > 0 check |
| `code_display` | `String(255)` | NULL | optional |

API: `code: { system, code, display? }` via `CodeableConceptRequest` / `parse_codeable_concept`. Empty system or code → 422. No uniqueness on `(system, code)` per patient/time. Display is not authority. Immutable after insert (trigger). Read DTO: `code_system`, `code`, `code_display`.

Normalization: strip; empty display → None. No case-folding catalog.

---

## 6. Unit contract (actual)

| Column | DB | Null | Notes |
|---|---|---|---|
| `unit` | `String(32)` | NULL | **required** when `value_type=NUMERIC` |

Representation: **free string**, not system+code, not enum, not terminology FK. Strip; empty → None; max length 32. No UCUM validation today.

**MVP design:** keep the string column; **server validates** exact equality against approved catalog unit values. No new unit representation for Vitals alone. **No free-text units** on the Manual Vital product path.

---

## 7. Vital terminology source decision

**VITAL TERMINOLOGY SOURCE = C — site/product clinical activation approval still missing for runtime use.**

Post-OGP reconciliation separates **provider-supported terminology** from **site-approved terminology**:

| Dimension | Meaning | Current state |
|---|---|---|
| `NATIONAL_INTEROPERABILITY_PROFILE` | SATUSEHAT / national LOINC+UCUM mapping evidence | PASS for first engineering subset |
| `PROVIDER_SUPPORTED` | software validates exact code+unit contract | proposed `manual-vitals-mvp-v1` subset — provider release gate **PENDING** |
| `SITE_APPROVED` | organization accepts catalog version + subset for clinical use | **0 entries** |
| `ACTIVE_FOR_ORGANIZATION` | runtime activation + entitlement + permission | none |

| Outcome | Status |
|---|---|
| A. Existing repository terminology catalog sufficient | **False** — none exists |
| B. National interoperability + provider engineering contract | **PASS for bounded subset** — see §7.1 |
| C. Site/product clinical activation approval for organization use | **PENDING** — Gate C |

**Do not conflate:** national mapping ≠ site clinical approval ≠ provider production registration.

**SITE-APPROVED CATALOG = (empty — zero SITE_APPROVED entries)**
**PROVIDER VITAL CATALOG VERSION (proposed) = `manual-vitals-mvp-v1`**
**Candidate research package id:** `php-vital-catalog-candidate-2026-08-27`

### 7.1 Provider engineering subset (national-profile-aligned)

Classification of evidence: **`NATIONAL_INTEROPERABILITY_PROFILE`**. Not site-approved for all organizations.

| Measurement | LOINC | UCUM | Display |
|---|---|---|---|
| Heart rate | `8867-4` | `/min` | beats/min |
| Respiratory rate | `9279-1` | `/min` | breaths/min |
| Body temperature | `8310-5` | `Cel` | (Cel) |
| Body weight | `29463-7` | `kg` | kg |
| Body height | `8302-2` | `cm` | cm |

**Body temperature limitation:** generic `8310-5` + `Cel` only. MVP does **not** capture measurement site or method. UI must **not** imply oral / axillary / tympanic / rectal when not captured.

**SpO₂ (`59408-5`):** **DEFERRED** — pending explicit provider/site semantic review. Not in first engineering subset.

**Partial site approval model:** only **SITE_APPROVED** entries may activate for an organization. Provider may support more codes than any given site approves.

**Site cannot invent code:** site may approve provider-supported entries only; new LOINC/UCUM pairs require provider terminology governance first.

---

## 8. Catalog enforcement (when catalog exists)

**CATALOG ENFORCEMENT = static application-owned immutable catalog/constants** (preferred once product approves entries).

Conceptual future module (do not create until implementation after approval):
`backend/app/modules/clinical/domain/vital_signs_catalog.py` (or equivalent under `clinical/domain/`).

Justification:

- No terminology DB exists; introducing one for a small MVP is unnecessary schema surface.
- Codes change by deliberate release, not clinician runtime edits.
- Aligns with frozen “no terminology server” Observation boundary.
- Keeps Observation idempotency migration **free of terminology rows** (separate from catalog tables).

**Not chosen now:** database-backed terminology table.

Backend must enforce: `(code_system, code)` ∈ **active approved** vital catalog **and** `unit` ∈ that entry’s approved units. Frontend dropdown is UX only. Unknown code → 422. Wrong unit → 422 (no silent replace/convert).

**Catalog change governance:** provider release gate + site activation evidence + code review + tests + gate updates. No casual alias/code/unit additions.

**AUTOMATIC UNIT CONVERSION = NO.**

**Human approval dependency (Gate C — site activation):** organization runtime activation requires site-approved catalog version + subset bound to `manual_vital_signs_write`. Engineering (Gate A) may proceed before any site approval exists.

---

## 9. Blood pressure

**BLOOD PRESSURE WRITE WORKFLOW = DEFERRED.**

**BP TERMINOLOGY EVIDENCE = PASS** (national interoperability profile):

- Systolic: `8480-6`, UCUM `mm[Hg]`
- Diastolic: `8462-4`, UCUM `mm[Hg]`

Reasons for workflow deferral (unchanged):

- Separate Observation facts only (no composite).
- Command model SINGLE → two POSTs; no fake atomicity.
- Paired/atomic measurement semantics require separate design.
- FORM MODEL = one measurement at a time → half-pair UX forbidden.

**Do not include BP in first Manual Vitals implementation.**

No batch route.

---

## 10. Numeric storage & request contract

**Path:** JSON number → Pydantic `Decimal | None` on `CreateObservationRequest.value_numeric` → `parse_decimal` → `ObservationValue.numeric: Decimal` → SQLAlchemy `Numeric(14, 4)` → PostgreSQL `NUMERIC(14,4)`.

Authoritative type: **Decimal**, not float.

`parse_decimal` rejects non-finite (NaN/Infinity/-Infinity) → `422 invalid_observation_value`.

**NUMERIC API:** JSON numeric `12.5` is the intended contract. Backend may also coerce via `Decimal(str(raw))` today (can accept surprising strings including scientific notation).

**Healthcare Web Manual Vital contract:**

- Serialize JSON number after frontend validation (or a single normalized decimal string if OpenAPI requires — prefer JSON number).
- Frontend **rejects** scientific notation (`1e2`).
- Backend must still fail safely if scientific / non-finite / overflow reaches it (422).

**Locale decimal input (ID):**

- UI may accept `12,5` as typing aid.
- Normalize **only** simple forms: one decimal comma XOR one decimal point, no thousands separators.
- `12,5` → `12.5` before command assembly.
- Reject ambiguous: `1,234.5`, `1.234,5`, multiple separators.
- API remains locale-independent.

**Precision / no silent rounding:**

- Storage scale 4.
- Frontend must not silently round.
- Backend: if value scale > 4 fractional digits → **reject 422** before any normalization/quantize (do not silently round). Integer and ≤4 fractional digits accepted within precision 14.
- Example: `1.23456` → **rejected**, not rounded to `1.2346`.

**NUMERIC FINGERPRINT CANONICALIZATION:** after validation passes, use `Decimal.normalize()` to produce plain non-exponent decimal text. `1`, `1.0`, `1.00`, `1.0000` → `"1"`. `1.2300` → `"1.23"`. `0.0000` → `"0"`. Never `float` stringification. **No quantize-before-reject.**

**CLINICAL NORMAL-RANGE VALIDATION = NO.** No invented per-vital technical ranges beyond precision/scale/finiteness.

Reference ranges: omit on Manual Vital create (do not let clinician invent ranges on the form).

---

## 11. Patient / same-person / RETIRED

**PATIENT CONTEXT PRECONDITION:**

- Required field: `expected_patient_identity_id` on the Manual Vital / hardened create contract (preferred explicit name; may be additive on existing create DTO).
- **Precondition only** — never authority for persisted `patient_identity_id`.
- Persisted binding: `encounter.patient_identity_id` (historical clinical identity convention).

**Same-person validation order:**

1. Current-org visibility of expected identity (before canonical oracle).
2. Canonical expected.
3. Load encounter (FOR UPDATE).
4. Canonical encounter-bound identity.
5. Visible ACTIVE + MERGED_IN cluster membership; canonicals equal.
6. Historical bound id unchanged on write.

Wrong same-org patient → **404 conceal**. Cross-org → **404 conceal**.

**RETIRED / unusable** expected or bound → **409 `identity_not_usable`**. Zero Observation.

Reuse Note Write `_assert_same_person_context` pattern (adapt mismatch resource messaging for Observation).

**Encounter picker:** cluster-aware `GET .../chart/sections/encounters` only. Backend reloads Encounter. Picker is not authority.

---

## 12. Encounter policy (Manual Vitals) — governance classification

Observation product workflow: **encounter required** (product contract; aligned with documented clinical practice / national profile documentation patterns — **not** falsely claimed as a standalone SATUSEHAT statutory mandate).

| Status | Manual Vital create | Classification |
|---|---|---|
| `IN_PROGRESS` | **ALLOWED** (provider safe default) | `VENDOR_SAFETY_DEFAULT` |
| `CANCELLED` | **REJECTED** (`409 encounter_not_documentable`) | `VENDOR_SAFETY_DEFAULT` |
| `ENTERED_IN_ERROR` | **REJECTED** | `VENDOR_SAFETY_DEFAULT` |
| `PLANNED` | **SITE_CLINICAL_POLICY** — not universally allowed by vendor assumption | Pending site/product human sign-off |
| `FINISHED` | **SITE_CLINICAL_POLICY** / late-documentation policy — not universally allowed by vendor assumption | Pending site/product human sign-off |

Do **not** hard-code PLANNED/FINISHED as universally allowed merely because an earlier design draft proposed it or because Wave 2B.2a Observation technically permits them. Frozen Observation domain documentable set remains a technical capability; **Manual Vital product activation** of PLANNED/FINISHED requires site clinical policy approval.

**ENCOUNTER REQUIRED = YES** for Healthcare Web Manual Vitals. Missing `encounter_id` → reject on this product path. Encounter-null facility rows: N/A (reject missing encounter first).

Until PLANNED/FINISHED site policy is approved for an organization, Manual Vitals deny those encounter statuses for that organization (fail closed). Overall product remains implementable under Gate A while site policies are pending.

---

## 13. Facility matrix (Observation create for Manual Vitals)

Align Note Write safety (current Observation create is weaker — P1 gap).

| Case | Result | Stored `facility_id` |
|---|---|---|
| Enc A / Header A | allow | A |
| Enc A / Header B | **409** facility mismatch | — |
| Enc A / Header absent; actor authorized for A | allow | A |
| Enc A / Header absent; actor **explicit Facility B only** | **403** | — |
| Enc null / … | reject (encounter required) | — |

Header omission never widens scope. Facility immutable after create.

---

## 14. Measurement time — governance classification

| Field | Meaning | Who | Classification |
|---|---|---|---|
| `effective_at` | Clinical measurement time | **Client required** for Manual Vitals | `VENDOR_SAFETY_DEFAULT` — **not** falsely SATUSEHAT-mandatory |
| `recorded_at` | Server recording time | Server `utc_now()` only | `VENDOR_SAFETY_DEFAULT` |

Do **not** silently set `effective_at = request receive time`.

**Timezone:** timezone-aware ISO 8601 internally; no naive stored clinical time. Frontend converts local input → offset-aware ISO. SATUSEHAT transport formatting follows applicable national profile in the interoperability adapter (`NATIONAL_INTEROPERABILITY_PROFILE`).

**Future `effective_at` / skew tolerance:** **`SITE_CLINICAL_POLICY` / technical configuration**. Source has no future-skew policy. **Do not invent** a universal “5-minute” national rule.

**Backdating:** **`SITE_CLINICAL_POLICY`**. Provider may technically allow historical `effective_at` with current `recorded_at` + current actor audit/provenance; site SOP decides whether late documentation is permitted.

---

## 15. Status / create-only / correction

Create status: **FINAL** (existing Observation). Manual Vitals use FINAL create.

**CREATE-ONLY MVP = YES.** No amend / EIE / generic update UI.

Existing backend amend may change value/unit/range/`effective_at`/status/version until EIE; trigger freezes patient/encounter/org/facility/category/code/value_type/recorder/recorded/provenance. First MVP does not expose amend.

**CORRECTION UI = DEFERRED.** Operational limitation: incorrectly recorded vital cannot be corrected through this MVP UI.

---

## 16. Command & form model

**COMMAND MODEL = SINGLE** — one measurement → one `POST /api/v1/clinical/observations`.

**FORM MODEL = ONE MEASUREMENT AT A TIME.**

Fields: encounter, vital type (catalog), value, unit (catalog-driven), measurement time (`effective_at`).

No multi-vital Save All. No BP. No fake atomicity.

Entry: Clinical Chart → Observations/Vitals → Add Manual Vital. PatientSafetyBanner visible. No second patient context.

---

## 17. Idempotency & Observation write migration

**Observation write migration revision:** **`UNASSIGNED`** — planned **`20260814_0021`** (parent `20260814_0020` OGP foundation) when implementation is approved. Assign only at implementation pass; **do not create in design/reconciliation passes**.

Do **not** reuse `clinical_note_write_idempotency`.

**Table (design name):** `clinical_observation_write_idempotency` (match `clinical_note_write_*` naming).

Logical columns:

- `id`
- `organization_id`
- `actor_id`
- `operation` (e.g. `OBSERVATION_CREATE`)
- `idempotency_key`
- `request_fingerprint`
- `observation_id` (FK, deferred as with notes)
- `created_at`

No raw clinical numeric value. Unique `(organization_id, actor_id, operation, idempotency_key)`. Insert-only posture like notes. Grants in `grant_dev_privileges.sql` (outside Alembic).

**Fingerprint (canonical JSON → SHA-256):**
`expected_patient_identity_id`, `encounter_id`, `category`, `code_system`, `code`, canonical numeric, `unit`, `effective_at` (normalized ISO), plus any other material mutation field.

**Replay order:**
authenticate → org/membership → permission (`clinical.observation.create`) → valid purpose → expected patient visibility → encounter lock → same-person → RETIRED → encounter status → facility authority/consistency → **code/unit catalog** → value validation → fingerprint → replay/conflict/create.

Revoked facility/permission or RETIRED → deny replay. Atomic commit: observation + audit + provenance + idempotency. Replay: no duplicate audit/provenance.

**Idempotency migration scope (required when implemented):**

1. `clinical_observation_write_idempotency` table + unique scope + insert-only protection + deferred observation FK (as designed).
2. **Not** terminology catalog tables (static catalog when approved).
3. **Optional P3 indexes** (document; include only if product accepts in same migration): e.g. `(organization_id, patient_identity_id, category, effective_at DESC)` supporting Clinical Read vitals/summary — **proposed, not created**. Default recommendation: **idempotency-only migration**; indexes as separate follow-up unless scale evidence demands them in the same change set.

Revision identifier: **`UNASSIGNED`** until implementation sequencing pass at approval time.

No Observation trigger rewrite required for create-only MVP beyond existing immutability (patient/facility already immutable). Facility/same-person are **service** hardenings, not necessarily trigger changes.

---

## 18. Audit / provenance / privacy

`OBSERVATION_CREATED` — resource/action/category/status/version/purpose metadata; **no numeric value**.

Provenance: existing insert-only `clinical_provenances`, `subject_type=OBSERVATION`.

Logs: treat value (+ unit + code with patient context) as PHI; extend redaction if needed (`unit` with value). No routine value logging.

422: global handler already strips Pydantic `input`. Tests for malformed value/unit/code/`effective_at`.

---

## 19. Frontend PHI / races / cache

Reuse Clinical Note unsaved-work primitive (patient/close/org/facility/nav/logout). 401 = immediate wipe. `retry: false`. Ambiguous retry = same Idempotency-Key.

Capture org/patient/encounter/generation before command. Late A never under B.

**POST-WRITE INVALIDATION (captured context only):**

- observations section
- timeline (Observation source)
- **summary** — **required** because frozen summary includes `recent_vitals` (`category == VITAL_SIGNS`, excludes EIE)

No all-chart fan-out.

---

## 20. No interpretation / BMI

No fever/hypertension/hypoxia/tachycardia/normal labels. No BMI. Facts only.

---

## 21. Accessibility

Explicit measurement label; unit visible/announced; numeric error association; measurement time label; encounter context; save/pending status; keyboard — no placeholder-only clinical form.

---

## 22. Threat model (updated)

| Threat | Mitigation |
|---|---|
| Wrong patient | `expected_patient_identity_id` + same-person + 404 |
| Wrong encounter | reload + status + same-person |
| Cross-org | org header + 404 |
| Facility omission bypass | 403 when absent would widen |
| Unsupported code / invalid unit pair | server catalog (when approved) |
| Numeric precision / NaN / Inf / sci notation | Decimal path + 422 |
| Idempotency replay after revoke | re-check full order |
| Duplicate create | Idempotency-Key + unique scope |
| Stale response | generation/context capture |
| Measurement-time confusion | required `effective_at` ≠ `recorded_at` |
| PHI logging / 422 echo | redact + stripped validation |
| Partial multi-vital / BP pair | one-at-a-time; BP deferred |
| Invented terminology | blocked until product approval |

---

## 23. Permissions / purpose / routes

Permission: `clinical.observation.create`. Purpose: **TREATMENT** (context, not grant).

**NEW BACKEND ROUTES = NONE** — harden existing `POST /api/v1/clinical/observations`. Amend/EIE remain backend-only, no MVP UI.

---

## 24. Deferred

Generic Observation authoring; BP; amend/EIE UI; device/Bluetooth/RPM; unit conversion; BMI; clinical interpretation; future `effective_at` clinical policy; DB terminology service; multi-measurement Save All; other clinical writes; AI.

---

## 25. OGP integration (required — unlike Clinical Note)

Manual Vital Signs must be designed from inception as **OGP-integrated**. Clinical Note remains frozen **without** OGP runtime dependency; Manual Vitals is the inverse.

| Item | Value |
|---|---|
| Feature ID | `manual_vital_signs_write` |
| `governance_required` | `true` when production-registered |
| Production registration | **NOT registered** — registry remains empty until provider release gate |
| Missing provider row | **deny** — feature unavailable (`NOT_REGISTERED`) |
| Provider `SUSPENDED` / `RETIRED` | **deny** (`DENIED_PROVIDER`) |
| Site activation missing | **deny** |
| Client `site_approved` claim | **forbidden** — server resolves OGP records |

### Future runtime acceptance intersection

For a governance-required Manual Vitals request:

```
PROVIDER_SUPPORTED
AND PROVIDER_CAPABILITY_AVAILABLE
AND SITE_FEATURE_ACTIVE
AND SITE_TERMINOLOGY_APPROVED (catalog version + subset)
AND DEPLOYMENT_GATES_SATISFIED (as declared on capability)
AND ENTITLED
AND ACTOR_PERMISSION (clinical.observation.create)
AND REQUEST/CLINICAL SAFETY VALIDATION
```

**Entitlement ≠ site approval ≠ permission.** OGP activation does not grant `clinical.observation.create`.

**No global registry effect:** Clinical Note and other non-integrated capabilities unaffected by Manual Vitals provider row presence/absence.

### Site terminology approval (follow-up)

OGP foundation deferred generic terminology enforcement. First Manual Vitals implementation should prefer **bounded vital catalog approval** bound to `manual_vital_signs_write` + provider catalog version + measurement subset via feature-specific approval evidence, rather than a broad terminology administration engine unless separately approved.

### Development-before-registration policy

Engineering may implement dark/inactive Manual Vitals while provider row is absent, treating `NOT_REGISTERED` as deny at runtime. No site can activate until Gates B and C complete.

---

## 26. Implementation readiness

```
MANUAL VITAL SIGNS ENGINEERING DESIGN = APPROVED FOR IMPLEMENTATION
PROVIDER PRODUCTION REGISTRATION = PENDING PROVIDER RELEASE / CLINICAL SAFETY GATE
SITE ACTIVATION = PENDING SITE CLINICAL / TERMINOLOGY APPROVAL
TERMINOLOGY CANDIDATE CATALOG = READY FOR HUMAN DECISION
SITE-APPROVED TERMINOLOGY ENTRIES = 0
```

Gate A (engineering) is **approved** when technical contracts in this document remain implementation-exact. Gate B (provider registration) requires provider clinical safety review — **PENDING**. Gate C (site activation) requires per-organization approval evidence — **PENDING**. Engineering must not self-approve site activation or provider production registration.

Implementation pass may begin under Gate A. **No Observation code in this design/reconciliation pass.**
