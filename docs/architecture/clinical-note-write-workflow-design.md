# Encounter-linked Clinical Note write workflow — architecture / security design

**Date:** 2026-08-27  
**Kind:** DESIGN ONLY — not implementation  
**Status:** APPROVED FOR IMPLEMENTATION (see companion gate; pre-implementation safety contract correction)  
**Baseline HEAD:** `3157ad9947f3f46d084df84982ee3b370f1c1a29` (`clinical-chart-ui-frozen`)  
**Parent:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Alembic:** heads `20260814_0018` (exactly one head; no `0019` file)  
**Migration 0019:** REQUIRED (idempotency table + attribution-immutability trigger extension). **Not created on this pass.**

This document is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement Clinical Note writes, clinical forms, other clinical mutations, AI, attachments, templates, voice, commit, tag, or push.

Authoritative frozen contracts (not reinterpreted):

- `docs/gates/clinical-chart-ui-final-freeze.md`
- `docs/gates/clinical-read-core-final-freeze.md`
- `docs/gates/patient-lookup-selection-final-freeze.md`
- `docs/clinical/wave2a-clinical-foundation.md`
- `docs/gates/wave2a-final-freeze.md`
- `backend/app/api/v1/clinical.py`
- `backend/app/modules/clinical/`
- `backend/alembic/versions/20260814_0004_wave2a_clinical_foundation.py`
- `backend/alembic/versions/20260814_0005_wave2a_clinical_hardening.py`

Frozen and not modified by this pass: Clinical Chart UI, Clinical Read Core, Patient Lookup & Selection, Healthcare Web Shell, IAM Shell Context, Encounter, Clinical Note backend, MPI, Product Access, ProductAccessPDP, Wave1PolicyPDP, all frozen clinical domains.

---

## 1. Baseline

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` |
| HEAD | `3157ad9947f3f46d084df84982ee3b370f1c1a29` |
| Tag | annotated `clinical-chart-ui-frozen` peels to the same SHA |
| Parent | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Working tree at inspection | published tree clean; this series only adds/updates the two design docs |
| Alembic heads | exactly one: `20260814_0018` |
| Migration `0019` | **not present / not created** |
| Local `alembic current` | not re-verified against a live DB in this pass (local DSN auth failed); freeze publication already recorded `current == heads == 20260814_0018` |

If this table were materially wrong, this pass would STOP.

---

## 2. Product boundary

This is the **first production-grade clinical write workflow** for Healthcare Web.

**In scope (design only):** encounter-linked Clinical Note documentation:

1. Select a currently authorized, org-visible encounter for the memory-only selected patient.
2. Create a `DRAFT` note (`POST /api/v1/clinical/notes`).
3. Optionally update draft body (`POST /api/v1/clinical/notes/{note_id}`).
4. Explicitly finalize (`POST /api/v1/clinical/notes/{note_id}/finalize`).
5. Unsaved-work guards, context-safe mutation handling, notes/timeline refresh.

**Out of scope:** Condition / Medication / Allergy / Observation / Lab / Procedure / Consent / prescription writes; AI; voice; templates; attachments; note-body chart viewing; amendment/addendum/co-sign; Patient Mobile; Platform Admin; FHIR; `/api/v2`; Encounter create/status UI unless already required as a tiny existing dependency (it is not — notes attach to an existing encounter).

Clinical Chart remains the frozen read surface. This workflow **must not** start calling `GET /api/v1/clinical/notes/{note_id}` from Chart or from a notes-list click. Mutation responses include `body_text` for **same-session** draft continuation only (memory). No Chart note-detail view. Draft reopen-by-id is deferred.

---

## 3. Encounter contract (frozen, inventory)

Table `encounters` (`EncounterModel`):

| Field | Source | Mutability |
|---|---|---|
| `id` | UUID PK | immutable |
| `patient_identity_id` | FK `patient_identities.id` RESTRICT, NOT NULL | immutable after insert (trigger `prevent_clinical_encounter_history_mutation`) |
| `organization_id` | FK organizations, NOT NULL | from `X-Organization-Id` on create, not request body |
| `facility_id` | FK facilities, **nullable** | from optional `X-Facility-Id` on create |
| `encounter_class` | `String(16)` enum `EMER` `IMP` `AMB` `VR` `HH` | set on create |
| `status` | `String(32)` | application transitions only |
| `display_label` | `String(64)` | server-generated `ENC-{hex}` |
| `started_at` | timestamptz NOT NULL | create (`started_at` or now) |
| `ended_at` | nullable | set when status becomes `FINISHED` / `CANCELLED` / `ENTERED_IN_ERROR` |
| `reason_system` / `reason_code` / `reason_display` | optional terminology stub | create |
| `actor_id` | nullable UUID | authenticated principal on create |
| `provenance_id` | nullable UUID | server-written |
| `created_at` / `updated_at` | mixin | server |

Participants: `encounter_participants` (`actor_id`, `participation_type` `ATTENDING` `ADMITTING` `CONSULTANT` `OTHER`).

**Status enum (actual):** `PLANNED`, `IN_PROGRESS`, `FINISHED`, `CANCELLED`, `ENTERED_IN_ERROR`.

**Create defaults:** `EMER` starts `IN_PROGRESS`; other classes start `PLANNED`.

**Transitions:** `PLANNED` → `IN_PROGRESS` \| `CANCELLED` \| `ENTERED_IN_ERROR`; `IN_PROGRESS` → `FINISHED` \| `CANCELLED` \| `ENTERED_IN_ERROR`; `FINISHED` / `CANCELLED` → `ENTERED_IN_ERROR` only.

**Indexes:** patient, organization, `started_at`, `status`.

**DML:** `app_dml` has `DELETE`/`TRUNCATE` revoked. Trigger blocks DELETE and rewriting `patient_identity_id`. `ENTERED_IN_ERROR` status is immutable.

### Encounter routes (staff `php-api`, prefix `/api/v1/clinical`)

| Method | Path | Permission | Purpose of route |
|---|---|---|---|
| POST | `/encounters` | `clinical.encounter.create` | Create. Body: `patient_identity_id`, `encounter_class`, optional `started_at`, optional `reason`. Org/facility from headers. |
| GET | `/encounters?patient_identity_id=` | `clinical.encounter.read` | List for **canonical** identity id + org. Limit 100. No unbounded enumeration. |
| GET | `/encounters/{id}` | `clinical.encounter.read` | Get one. Cross-org → 404 conceal. |
| POST | `/encounters/{id}/status` | `clinical.encounter.update_status` | Status command. Body: `{ "status" }`. `SELECT FOR UPDATE`. |

Audience: staff only (`require_staff_audience`). `X-Organization-Id` required. `X-Facility-Id` optional. `X-Purpose` required catalog value. Audit: `ENCOUNTER_CREATED`, `ENCOUNTER_STATUS_CHANGED` (no clinical note body). Provenance row on create. Locking: mutations `get_encounter_for_update()`.

**List caveat (authoritative):** `list_encounters_for_patient` filters `patient_identity_id == canonical.id`. Historical encounters whose `patient_identity_id` was not rewritten after MPI merge are **not** returned by this command list. Clinical Read chart/section/timeline **is** cluster-aware. Encounter picker for note write **must** use the authorized Chart `encounters` section (or equivalent cluster-aware read), not command `GET /encounters` as the sole source.

This pass does **not** modify Encounter.

---

## 4. Clinical Note contract (frozen, inventory)

Table `clinical_notes` (`ClinicalNoteModel`). Actual names only. **There is no `title` column.**

| Field | Constraint / meaning |
|---|---|
| `id` | UUID PK |
| `patient_identity_id` | NOT NULL FK. **Inherited from the encounter at create. Not accepted from the client body.** Immutable after insert. |
| `encounter_id` | NOT NULL FK. **Required. Free-floating notes are not supported by schema.** Immutable after insert. |
| `organization_id` | NOT NULL. From `X-Organization-Id`. |
| `facility_id` | nullable. **Set only at create** per facility matrix (§12). Immutable after insert (designed 0019 trigger + service). |
| `note_type` | `String(32)` check: `PROGRESS` `ADMISSION` `ED` `DISCHARGE` `OTHER` |
| `body_text` | `Text` NOT NULL; check `char_length(body_text) > 0`; service max 20000 after strip |
| `record_status` | `DRAFT` `FINAL` `ENTERED_IN_ERROR` |
| `version` | int ≥ 1; starts 1; incremented on draft body update |
| `supersedes_id` | nullable self-FK. **Present in schema; unused by current routes.** |
| `content_hash` | SHA-256 of `note_type + "\n" + body` |
| `author_id` | nullable UUID; **authenticated principal** on create |
| `authored_at` | required timestamptz |
| `finalized_at` | nullable; set on finalize only |
| `provenance_id` | nullable (inherited P3: may be null in foundation; create currently writes one) |
| `created_at` / `updated_at` | mixin |

**No `signed_at`, `signer_id`, `title`, or rich-text column.** Finalize is the attestation analogue.

**Indexes:** `ix_clinical_notes_patient_identity_id`, `ix_clinical_notes_encounter_id`, `ix_clinical_notes_authored_at`. No status index. No idempotency unique constraint.

**Repository:** `get_note`, `get_note_for_update` (`SELECT … FOR UPDATE`), `add_note`, `list_notes_for_encounter` (internal; **no public list-by-encounter command route**).

---

## 5. Clinical Note routes (frozen)

All under `/api/v1/clinical`, staff audience, org from header, optional facility header, required catalog purpose.

**Frozen today (insufficient for wrong-patient safety):**

| Method | Path | Frozen request DTO | Response | Permission |
|---|---|---|---|---|
| POST | `/notes` | `encounter_id`, `note_type`, `body_text` | `ClinicalNoteResponse` **includes `body_text`** | `clinical.note.create` |
| GET | `/notes/{note_id}` | — | same; **body exposed** | `clinical.note.read` |
| POST | `/notes/{note_id}` | `body_text` only | same | `clinical.note.update_draft` |
| POST | `/notes/{note_id}/finalize` | empty body | same | `clinical.note.finalize` |
| POST | `/notes/{note_id}/entered-in-error` | empty body | same | `clinical.note.finalize` |

**Designed contract (same paths, additive DTO/header fields — §7+).** New resource paths are not required. HTTP remains **200** (FastAPI default; tests also accept 201). Do not switch to 201 in this workflow.

There is **no** DELETE route. Update is **POST**, not PATCH/PUT (project convention for this resource). Finalize is an **explicit command endpoint**, not `PATCH status`.

Create/update/finalize **already exist**. New resource paths are not required for the MVP workflow.

HTTP: FastAPI default for these POSTs is **200** (tests also accept 201). Keep 200 unless a later contract change is separately approved.

Org/facility/patient/encounter scoping:

- Cross-org note or encounter UUID → **404** `"Clinical note not found"` / `"Encounter not found"` (conceal).
- Patient on the note = encounter's stored `patient_identity_id` (not client-supplied).
- Platform-scoped principal may see across orgs (existing Wave 1 platform exception). Healthcare Web is org-scoped staff.

Locking: create locks the encounter (`for_update=True`). Update/finalize/EIE lock the note.

Audit (success, **no body**): `CLINICAL_NOTE_CREATED` metadata `{note_type, purpose}`; `CLINICAL_NOTE_UPDATED` `{purpose}`; `CLINICAL_NOTE_FINALIZED` `{purpose}`; `CLINICAL_NOTE_ENTERED_IN_ERROR` `{purpose}`. Resource type `ClinicalRecord`. `patient_id` = note's identity. `resource_id` = note id.

Provenance on **create only** (`subject_type` `CLINICAL_NOTE`, `authorship_kind` `NATIVE`, `information_source` `CLINICIAN`, `verification_method` `clinical_authorship`). Update/finalize do not insert additional provenance rows today.

---

## 6. Current note read behavior (Chart)

Clinical Chart intentionally lists **metadata only** via Clinical Read `GET …/chart/sections/notes` (`NoteListDTO`: id, encounter_id, org, facility, note_type, record_status, version, authored_at, finalized_at, author_id, patient_identity_id). Frontend `facts.ts` hides `body_text` even if present.

Frozen `GET /api/v1/clinical/notes/{note_id}` returns `body_text` to any staff with `clinical.note.read` in the org. Chart **must not** start using it.

**Read-after-write:** the create/update/finalize JSON already contains `body_text`. MVP keeps that body in **form React state** with `note_id` / `version` for same-session Save Draft → edit → finalize. **Do not** issue an extra GET. **Do not** put `body_text` in query keys or persistent cache. Chart notes section stays metadata-only.

---

## 7. First write capability (unchanged)

**FIRST WRITE CAPABILITY = Clinical Note only.**

**ENCOUNTER REQUIRED = YES.** Schema `encounter_id` is NOT NULL.

**SELECTED PATIENT REQUIRED = YES** (Healthcare Web). No selected patient → no form, zero write requests.

---

## 7a. P1: selected patient is not server-observable today

Frozen `CreateClinicalNoteRequest` has no selected-patient field. The server therefore **cannot** prove that encounter E belongs to the clinician’s current patient P for a same-org UUID. Frontend picker/generation guards are UX, not this invariant.

That is **not** acceptable. The following contract is mandatory before implementation.

---

## 7b. Patient-context precondition (decision A)

**Chosen transport: A — required `expected_patient_identity_id` on the mutation JSON body.**

Rejected:

- **B (header):** org/facility/purpose already use headers; a fourth identity header is easier to omit and is not an existing project pattern for patient writes.
- **C (nested route):** would be a new path (`/patients/{id}/notes`). Forbidden by “no new routes.”
- **D:** no existing clinical-note mechanism carries selected-patient context.

Applies to **CREATE, UPDATE DRAFT, and FINALIZE** (finalize is higher impact than draft update).

`expected_patient_identity_id` is a **PRECONDITION only**:

- It is **not** written to `clinical_notes.patient_identity_id`.
- It is **not** used to rewrite `encounters.patient_identity_id`.
- The persisted note patient remains `encounter.patient_identity_id` (create) or the note’s existing immutable `patient_identity_id` (update/finalize).

Do not send `organization_id`, `facility_id`, `author_id`, or `signer_id` as client authority.

**Authorization ≠ patient-context precondition.** PDP still checks `clinical.note.*` + org + facility scope. Knowing `note_id` / `encounter_id` is not proof that the current selected patient is that resource’s person. Both checks are required.

---

## 7c. Same-person rule (cluster / canonical)

Use frozen MPI helpers already used by Clinical Read (`resolve_canonical_identity`, `list_cluster_identity_ids` with `ACTIVE` + `MERGED_IN` members). Do not invent a new merge semantic. Do not rewrite historical IDs.

**CREATE invariant (all must hold):**

1. `expected_patient_identity_id` is visible in `X-Organization-Id` (same visibility as `_require_visible_identity` / Clinical Read: provenance or identifier for that org). Else **404** `"Patient identity not found"` (conceal; never “belongs to another organization”).
2. Expected identity is not `RETIRED`. Canonical resolution succeeds (MERGED X → survivor Y is OK). Else **409** `identity_not_usable` or `canonical_resolution_failed` (same codes as Chart/clinical).
3. Encounter exists, `encounter.organization_id == X-Organization-Id`. Else **404** `"Encounter not found"`.
4. Let `P_canon = resolve_canonical(expected_patient_identity_id)`, `cluster = list_cluster_identity_ids(P_canon.id)`, `E_patient = encounter.patient_identity_id`.
5. **Match:** `E_patient ∈ cluster` **and** `resolve_canonical(E_patient) == P_canon` (canonical equality). Simple UUID equality is **insufficient** because E may store historical source X while the UI selected survivor Y.
6. Else **404** `"Encounter not found"` — same-org wrong-patient is concealed. **Zero note rows.** Do not return 409 `patient_mismatch` (oracle that E exists for someone else).

**UPDATE / FINALIZE invariant:**

Replace “encounter” with the locked note: `note.organization_id` must equal header org (existing 404). `note.patient_identity_id ∈ cluster(expected)` and canonicals equal. Else **404** `"Clinical note not found"`. **Zero mutation.**

Platform-scoped principals keep existing `_visible_*` exceptions; Healthcare Web is org-scoped staff.

---

## 7d. Mandatory cases

| Case | Result |
|---|---|
| Org A, selected P1, submit P1’s encounter E1 | Allow if other checks pass. Note.patient = E1.patient_identity_id (may be historical X). |
| Org A, selected P1 (`expected_patient_identity_id=P1`), submit P2’s E2 | **404** Encounter not found. **ZERO notes.** |
| Selected P from org B, current `X-Organization-Id` = A | **404** Patient identity not found. No oracle. |
| Encounter UUID org B | **404** Encounter not found. |
| Selected canonical Y, encounter stores merged-in X in Y’s cluster | **Allow.** Persist X. Do not rewrite E. |
| Selected Y, encounter of unrelated person | **404** conceal. |

---

## 8. Encounter picker source (frozen)

**ENCOUNTER PICKER SOURCE = Clinical Read section `encounters`.**

Exact route:

`GET /api/v1/clinical/patients/{patient_identity_id}/chart/sections/encounters`

with current `X-Organization-Id`, optional `X-Facility-Id` (work context only; **not** copied to `?facility_id=`), `X-Purpose: TREATMENT`. Path id = memory-only selected patient (Chart already canonicalizes).

This list is **cluster-aware** (`EncounterModel.patient_identity_id.in_(cluster_ids)`).

**Do not** use command `GET /api/v1/clinical/encounters?patient_identity_id=` as the picker. That list is **canonical-id only** and omits historical encounters whose `patient_identity_id` was not rewritten after merge.

Picker is **not** authority. Backend re-validates `encounter_id` at mutation time (org + cluster match + documentable status).

No “today’s encounter.” No scheduling.

---

## 9. Create / update / finalize request contracts

### CREATE — `POST /api/v1/clinical/notes`

Headers: `Authorization`, `X-Organization-Id`, optional `X-Facility-Id`, `X-Purpose: TREATMENT`, **required** `Idempotency-Key` (§21).

```json
{
  "expected_patient_identity_id": "<uuid>",
  "encounter_id": "<uuid>",
  "note_type": "PROGRESS",
  "body_text": "…"
}
```

Persisted patient = encounter’s stored `patient_identity_id`. Facility per §12 create matrix.

### UPDATE DRAFT — `POST /api/v1/clinical/notes/{note_id}`

Same headers **except** Idempotency-Key is **not** required (version token is the concurrency control). Optional Idempotency-Key is out of scope for MVP update.

```json
{
  "expected_patient_identity_id": "<uuid>",
  "expected_version": 1,
  "body_text": "…"
}
```

`expected_version` is the existing integer column `clinical_notes.version` (NOT NULL, ≥ 1, created as `1`). **No version column in 0019.**

Mutable: `body_text` (and derived `content_hash`, `version`, `updated_at`) only. Not patient, encounter, organization, facility, author, `note_type`, `record_status`.

### FINALIZE — `POST /api/v1/clinical/notes/{note_id}/finalize`

Same org/purpose/facility headers. **Required** `Idempotency-Key`. **Required** JSON body (today empty — additive):

```json
{
  "expected_patient_identity_id": "<uuid>"
}
```

**`expected_version` is NOT required on finalize.** `SELECT FOR UPDATE` + `assert_note_can_finalize` (`note_not_draft` 409) already serializes DRAFT→FINAL and blocks overwrite-after-FINAL. Do not add a redundant version token.

EIE route: unchanged; **no UI**.

---


## 10. Canonical patient / MPI / merge-during-write

Frozen rule: **historical `patient_identity_id` is not rewritten after merge.**

- Create copies `encounter.patient_identity_id` as stored (may be source X).
- `expected_patient_identity_id` may be X, Y, or any cluster member. After Chart retarget, it is typically canonical Y.
- Same-person rule (§7c) uses cluster + canonical equality. **Do not rewrite E or the note.**

**MERGED while form is open:** Chart retargets to survivor Y. Keep the same encounter if it remains in Y’s cluster. Send `expected_patient_identity_id` = current selected id (Y). If the encounter is no longer in cluster → 404; user must re-select. Do not retarget to a different encounter.

**RETIRED check (CREATE, UPDATE DRAFT, and FINALIZE — all three):**

After resolving expected identity and loading encounter/note:

- If expected identity is `RETIRED` → 409 `identity_not_usable` (no write).
- If canonical resolution fails → 409 `canonical_resolution_failed`.
- If encounter/note `patient_identity_id` resolves to `RETIRED` (or cannot resolve to an active canonical) → 409 `identity_not_usable`.

A draft that was valid when opened cannot be updated or finalized after the person is retired. Frontend: Chart 409 already closes the patient; still rely on backend.

MERGED is not RETIRED. MERGED + resolvable survivor is allowed under §7c.

---

## 11. Organization binding

Authority: `X-Organization-Id` + organization-scoped principal. DTOs have **no** `organization_id`. Note.organization_id is the header org at **create** and is immutable thereafter. Encounter/note org mismatch → 404 conceal.

---

## 12. Facility matrix (implementation-exact)

`X-Facility-Id` is optional work context. PDP: facility ∈ org (`facility_tenant_decision`, conceal 404) and actor allow-list (empty list = org-wide). Not Chart `?facility_id=`.

**CREATE — current frozen bug:** `facility_id or encounter.facility_id` silently prefers the header. **Forbidden going forward.**

### CREATE attribution

| | Encounter facility | Header `X-Facility-Id` | Result | Note.facility_id |
|---|---|---|---|---|
| A | A | A | **Allow** | A |
| B | A | B ≠ A | **Reject** 409 `encounter_facility_mismatch`. Zero note. | — |
| C | A | absent | **Allow** | A (inherit) |
| D | absent | A (PDP-valid) | **Allow** | A (work attribution) |
| E | absent | absent | **Allow** | `null` (org-only) |

Invalid header UUID → 422 `invalid_facility`. Header facility not in org / not in actor allow-list → existing 404/403. Do not write.

**WORK FACILITY REQUIRED = CONDITIONAL.**

**Facility after create = IMMUTABLE.** Draft body edits and finalize must not change `facility_id`, `organization_id`, `author_id`, `patient_identity_id`, `encounter_id`, or `note_type`. Existing 0005 trigger already locks patient/encounter and FINAL content. **0019 extends the trigger** so DRAFT cannot change org/facility/author/`note_type`.

### UPDATE DRAFT facility

Do **not** copy header onto the note.

| Note.facility_id | Header | Result |
|---|---|---|
| A | A | Allow (no column change) |
| A | B ≠ A | **Reject** 409 `note_facility_mismatch`. No body write. |
| A | absent | Allow (no column change) |
| `null` | A | Allow; **do not** set facility to A |
| `null` | absent | Allow |

### FINALIZE facility

Same matrix as UPDATE. Finalizing under work facility B must not re-attribute a note stored as A. 409 `note_facility_mismatch` if both set and unequal.

Frontend: if selected work facility disagrees with encounter facility, block submit and require switch **before** create.

---

## 13. Permissions and role expectations

| Action | Permission |
|---|---|
| Create draft | `clinical.note.create` |
| Read (command GET includes body) | `clinical.note.read` |
| Update draft body | `clinical.note.update_draft` |
| Finalize **and** EIE | `clinical.note.finalize` |

No `clinical.note.delete` / `clinical.note.sign`. CLINICIAN seed has write permissions; REGISTRAR does not (403). ORG_ADMIN/AUDITOR: read only. PDP uses permission codes, not role names.

---

## 14. Purpose

Healthcare Web sends **`X-Purpose: TREATMENT`** for create, update, and finalize. Catalog parse is frozen (422 if missing/invalid). Purpose ≠ grant. Do not modify Wave1PolicyPDP.

---

## 15. Lifecycle, draft, finalize, immutability

Statuses: `DRAFT`, `FINAL`, `ENTERED_IN_ERROR`. **DRAFT = SUPPORTED.** **SIGN/FINALIZE = IN MVP** via `/finalize`. **FINAL mutable = NO.** Amendment/addendum **DEFERRED**. EIE API exists; **EIE UI = DEFERRED** (no button).

Draft update: `body_text` only. Cross-author draft edit remains possible with `clinical.note.update_draft` (frozen). Cross-author finalize remains possible with `clinical.note.finalize` — **known P2 / product-policy; do not silently add author-only finalize.**

---

## 16. Delete and correction

No delete UI or API. Grants revoke DELETE. Do not overwrite FINAL.

---

## 17. Author and signer

**AUTHOR = authenticated principal** on create (`author_id`). Never request-body authority. Finalize does not write `signer_id`; audit actor is the caller; `author_id` unchanged. No sign-as-another-user field. Co-sign deferred.

---

## 18. Note type, body, XSS, length, Unicode

Enum `PROGRESS|ADMISSION|ED|DISCHARGE|OTHER`. Plain `body_text`. No HTML editor. Escape on display. Max 20000. Strip ends; reject empty (`note_body_required`). No destructive Unicode normalization. Request cap 1 MiB.

---

## 19. Autosave, PHI persistence, form library

**AUTOSAVE = NO.** Unsaved PHI: React state only. No localStorage / sessionStorage / IndexedDB / URL / SW / persistQueryClient. **No React Hook Form.**

---

## 20. Encounter status

Create still blocks only `CANCELLED` and `ENTERED_IN_ERROR` (`encounter_not_documentable` 409). `PLANNED`, `IN_PROGRESS`, `FINISHED` may receive notes (frozen). Frontend does not invent a stricter rule. Backend re-checks status at write time.

---

## 21. Idempotency (exact)

**Header:** `Idempotency-Key` **required** on CREATE and FINALIZE. Not required on draft update.

| Rule | Value |
|---|---|
| Required | CREATE yes; FINALIZE yes; UPDATE no |
| Format | opaque string, length 8–128, charset `[A-Za-z0-9._-]` (UUID v4 recommended). No semantic parsing. Invalid → 422 `invalid_idempotency_key` |
| Scope | `(organization_id, actor_id, operation, idempotency_key)` where `operation` ∈ `NOTE_CREATE` \| `NOTE_FINALIZE`. **Not** globally unique across tenants or actors |
| Storage | table `clinical_note_write_idempotency` (0019). **No note body. No raw PHI.** |
| Fingerprint CREATE | SHA-256 hex of UTF-8 canonical: `encounter_id \| note_type \| sha256(utf8(stripped body_text))`. **Not** `expected_patient_identity_id` (precondition; X vs Y same person). **Not** facility header |
| Fingerprint FINALIZE | SHA-256 hex of UTF-8 `note_id` |
| Same key + same fingerprint | Replay: **200** `ClinicalNoteResponse` of the existing note. **No** second note, audit, or provenance. No replay indicator header required |
| Same key + different fingerprint | **409** `idempotency_key_conflict`. No second note. No body echo |
| Concurrent same key | Unique constraint; one winner inserts the note; loser sees unique_violation, `SELECT` winner, compare fingerprint → replay or 409. **No Redis.** Exactly one note |
| Missing key on create/finalize | 422 `idempotency_key_required` |
| Retention | insert-only; keep rows (immutable trigger like other clinical facts) |

Frontend: new key per user-intent; reuse the **same** key on retry after abort/network if the user is retrying **that** Save/Sign. New key only after explicit new intent. Disable button while pending (`retry: false`).

---

## 22. Migration 0019 (exact, not created)

**Revision:** `20260814_0019`  
**down_revision:** `20260814_0018`  
**One head.**

**0019 does NOT add `clinical_notes.version`** (already NOT NULL integer ≥ 1 from 0004; create sets 1; update already increments).

### Table `clinical_note_write_idempotency`

| Column | Type |
|---|---|
| `id` | UUID PK |
| `organization_id` | UUID NOT NULL FK organizations RESTRICT |
| `actor_id` | UUID NOT NULL |
| `operation` | VARCHAR(32) NOT NULL CHECK (`NOTE_CREATE`, `NOTE_FINALIZE`) |
| `idempotency_key` | VARCHAR(128) NOT NULL |
| `request_fingerprint` | CHAR(64) NOT NULL |
| `note_id` | UUID NOT NULL FK clinical_notes RESTRICT |
| `created_at` | timestamptz NOT NULL default now() |

**Unique:** `uq_clinical_note_write_idempotency_scope` on `(organization_id, actor_id, operation, idempotency_key)`.

Index on `note_id` for ops. `app_dml`: INSERT/SELECT; **REVOKE DELETE, UPDATE, TRUNCATE** (replay reads existing row; no updates required if insert happens after note id is known in the same transaction — insert once with final `note_id`).

**Insert order (single DB transaction):** lock encounter (create) or note (finalize) → validate preconditions → insert note + provenance + success audit (create) or status+audit (finalize) → insert idempotency row with `note_id`. If unique_violation: rollback this attempt’s new note **or** use savepoint: prefer **insert idempotency first is wrong** without note_id. Pattern:

1. `SELECT … FOR UPDATE` resource.
2. Validate.
3. Attempt `INSERT` idempotency is deferred until `note_id` exists: create note, then INSERT idempotency. On unique_violation: `ROLLBACK TO SAVEPOINT` the new note **or** abort transaction and `SELECT` existing mapping by scope key, compare fingerprint, return replay or 409 **without** leaving an orphan note.

Concurrent: both pass validation; both try insert note; both try idempotency insert; unique wins one mapping. The loser **must not commit a second note**. Implementation: take an advisory-free approach — insert idempotency row with a **preallocated** `note_id` (`gen_random_uuid()`) **before** inserting the note, using that id on both rows, inside one transaction. Unique on scope key serializes creators: second INSERT idempotency fails; transaction rolls back entirely; retry path SELECT existing. First transaction commits note+provenance+audit+idempotency together.

**Replay path:** SELECT mapping by scope; if fingerprint matches, load note by `note_id`, return view; **no** additional audit/provenance.

**Downgrade:** drop trigger extension (restore 0005 function), drop table.

### Trigger extension (same 0019)

Extend `prevent_final_clinical_note_content_mutation` (or add `prevent_clinical_note_attribution_mutation`): on UPDATE, if `organization_id`, `facility_id`, `author_id`, or `note_type` differ from OLD → exception `clinical note attribution is immutable`. Patient/encounter already blocked. DRAFT may still change `body_text`, `content_hash`, `version`, `updated_at`, `record_status` (DRAFT→FINAL / EIE as today).

Idempotency table: INSERT-only trigger (block UPDATE/DELETE) like `clinical_provenances`.

---

## 23. Optimistic version token

**Token = existing integer `clinical_notes.version`.** Field name on the wire: `expected_version` (int ≥ 1).

| Rule | Value |
|---|---|
| Initial | 1 at create (frozen service) |
| Increment | `version = version + 1` on every **successful** draft update (current code). Even if stripped body equals previous |
| Finalize | **does not** increment (frozen). No `expected_version` on finalize |
| Stale update | `expected_version != note.version` after `FOR UPDATE` → **409** `note_version_conflict`. Generic message. No body echo. Frontend must reload from **in-session form state** or abandon; **no GET-by-id in MVP** |
| No silent LWW | Client without `expected_version` → 422 |

---

## 24. Sign race and double finalize

| Order | Outcome |
|---|---|
| B finalize, then A update | A: 409 `note_not_draft`. Trigger blocks FINAL body. Signed state kept |
| A update holds lock, then B finalize | A commits new version; B then finalizes that body (or 409 if A finalized — N/A). Deterministic under `FOR UPDATE` |
| Two finalize, different keys | First: 200 FINAL + one audit. Second: 409 `note_not_draft`. No second FINAL transition |
| Two finalize, **same** Idempotency-Key | First commits; second unique/replay → 200 same FINAL note, **no** second audit |

Do not invent two FINAL rows.

---

## 25. Unsaved-work guards (exact UI)

Replace silent `canReplaceTenantContext()` no-op with a **modal**:

Copy: unsaved clinical note will be discarded. It is not stored in the browser.

Actions:

- **Stay** — cancel the navigation/switch. Form unchanged.
- **Discard and continue** — clear textarea, note id, version, encounter selection PHI from React state; unregister guard; then perform the pending Change Patient / Close Patient / org switch / facility switch / route change / logout.

No third “save first” action in MVP (user already has Save Draft).

| Event | Guard |
|---|---|
| Change Patient / Close Patient | Modal. Discard clears form then proceeds. Never carry body to P2 |
| Organization switch | Modal. Discard then switch. Never carry text into another tenant |
| Work facility switch | Modal. Discard then switch. Never silently re-attribute unsaved text to facility B |
| In-app route away | Modal (including Clinical Chart section change if it would unmount the form) |
| Logout | Warn via same modal if possible; **security cleanup still wins** if the user confirms or session ends |
| `beforeunload` | Browser confirm; no persistence |
| **401 / session expiry** | **No modal required.** `clearSensitiveClientState` wipes token, patient, queries, component unmount. Unsaved body lost. Documented tradeoff |

---

## 26. Abort and response generation guard

Browser abort ≠ server rollback. If create/update/finalize was accepted, the server may complete. Retry with the **same** Idempotency-Key (create/finalize). Message: do not claim “cancelled note was not saved.”

Apply mutation result **only if all still match**:

- `X-Organization-Id` / current org
- selected patient id (canonical, as Chart uses)
- selected `encounter_id` (create) or `note_id` (update/finalize)
- form generation (increment on patient/org/facility switch, discard, unmount)

Late A must not render under B. `retry: false`.

---

## 27. Draft reopen and body readback

**DRAFT REOPEN = DEFERRED (option A).**

MVP supports create → update → finalize **in the same form session only**. After Save Draft, retain in React memory: `note_id`, `version`, `body_text`, `encounter_id`, `note_type`. Continue editing from that state. **Do not** call `GET /api/v1/clinical/notes/{id}`. **Do not** open body from Chart notes metadata list.

If the user discards, navigates away, reloads, or 401s: that draft is not reopenable in MVP (it still exists server-side as DRAFT; a later pass may add safe reopen). Chart list remains metadata-only.

After finalize: clear textarea; keep a non-PHI confirmation (note id may be shown as opaque success). Invalidate caches (§28).

---

## 28. Post-write invalidation

After create, update, and finalize (when generation still matches):

- `clinicalKeys.section(org, patient, "notes")`
- `clinicalKeys.timeline(org, patient)` if that query exists

Not summary, allergies, medications, labs, shell, other sections. No `body_text` in query keys.

---

## 29. Finalize UI

Explicit confirmation: “Signing finalizes this note. It cannot be edited afterwards.” Show PatientSafetyBanner, encounter strip (class, label, time, facility, status), organization, current staff display, draft status. No one-click finalize. No EIE button.

---

## 30. HTTP extras (designed)

| Outcome | Status / code |
|---|---|
| Success / idempotent replay | 200 |
| Missing `expected_patient_identity_id` | 422 |
| Wrong-patient / cross-org encounter or note | 404 conceal |
| Facility mismatch create | 409 `encounter_facility_mismatch` |
| Facility mismatch update/finalize | 409 `note_facility_mismatch` |
| Version stale | 409 `note_version_conflict` |
| Idempotency conflict | 409 `idempotency_key_conflict` |
| Retired / unusable | 409 `identity_not_usable` |
| Cancelled/EIE encounter | 409 `encounter_not_documentable` |
| Not draft | 409 `note_not_draft` |

422 handler still strips Pydantic `input`. No body in logs.

---

## 31. Backend API strategy

Existing paths only. Additive DTO fields + Idempotency-Key + 0019 + facility/retired/cluster checks in `ClinicalService`. Do not modify Clinical Read Core, MPI module internals beyond **calling** existing resolve/cluster helpers from clinical service, ProductAccessPDP, or Wave1PolicyPDP.

---

## 32. Threat model (updated)

| Threat | Mitigation |
|---|---|
| Same-org wrong-patient encounter | `expected_patient_identity_id` + cluster match; 404; zero note |
| Cross-org patient/encounter | 404 conceal |
| Historical merge mismatch | canonical + cluster; persist encounter identity |
| Stale/mismatched facility | create/update/finalize matrices; 409; 0019 trigger |
| Forged author | principal only |
| Duplicate / concurrent create | Idempotency-Key + unique scope + one transaction |
| Concurrent draft LWW | `expected_version` 409 |
| Overwrite after FINAL | `note_not_draft` + trigger |
| Double finalize | 409 or idempotent replay |
| Retired write | 409 on create/update/finalize |
| Stale UI response | generation guard |
| Chart body leak via reopen | reopen deferred; no GET-by-id |
| Unsaved carry across patient/org/facility | modal discard |
| Body logging / XSS | existing redaction; plain text |

---

## 33. Implementation boundary

Later implementation PR only:

1. Form: selected patient + Clinical Read encounters picker + textarea.
2. POST notes / notes/{id} / notes/{id}/finalize with designed DTOs.
3. 0019 as specified.
4. Service: cluster precondition, facility matrix, retired checks, version match, idempotency.
5. Unsaved modal. Invalidate notes + timeline.
6. TREATMENT; catalog permissions.

**DEFER:** EIE UI, reopen-by-id, amendments, co-sign, other clinical writes, Chart body GET, AI, attachments, templates, voice, rich text.

---

## 34. Blocking / readiness

Wrong-patient binding, cluster comparison, facility matrix, retired scope, idempotency uniqueness, stale version, FINAL immutability, and unsaved switch protection now have **exact** contracts. Frontend picker is not a substitute for `expected_patient_identity_id`.

**CLINICAL NOTE WRITE WORKFLOW DESIGN = APPROVED FOR IMPLEMENTATION**

Do not implement on this pass. Do not create 0019 on this pass.
