# Encounter-linked Clinical Note write workflow — implementation

**Date:** 2026-08-27  
**Kind:** IMPLEMENTATION — not hardening, not freeze  
**Status:** IMPLEMENTED (backend + Healthcare Web form)  
**Baseline HEAD:** `3157ad9947f3f46d084df84982ee3b370f1c1a29` (`clinical-chart-ui-frozen`)  
**Parent:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Alembic after implementation:** `current == heads == 20260814_0019` (exactly one head; parent `20260814_0018`; no `0020`)

This document is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement Condition, Medication, Allergy, Observation, laboratory, or Procedure writes; note amendment/addendum; entered-in-error UI; draft reopen; attachments; rich text; templates; autosave; or AI. No commit, tag, or push.

Authoritative design: `docs/architecture/clinical-note-write-workflow-design.md` and `docs/gates/clinical-note-write-workflow-design-approval.md`. When this file and the implementation prompt disagree, the corrected design wins.

---

## 1. Baseline

| Item | Result |
|---|---|
| Published HEAD | `3157ad9947f3f46d084df84982ee3b370f1c1a29` |
| Tag | `clinical-chart-ui-frozen` peels to the same SHA |
| Parent | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Branch | `main` == `origin/main` |
| Alembic before | `current == heads == 20260814_0018` |
| Alembic after | `current == heads == 20260814_0019` |
| Frozen Clinical Read Core / MPI / ProductAccessPDP / Wave1PolicyPDP | not modified |
| Other clinical writes | not implemented |

---

## 2. Existing routes only

No new Clinical Note routes. Additive request fields and `Idempotency-Key` on:

| Method | Path | Use |
|---|---|---|
| POST | `/api/v1/clinical/notes` | create DRAFT |
| POST | `/api/v1/clinical/notes/{note_id}` | draft body update |
| POST | `/api/v1/clinical/notes/{note_id}/finalize` | DRAFT → FINAL |

`GET /api/v1/clinical/notes/{note_id}` remains on the backend and is **not** called by the MVP form. Entered-in-error remains an existing command with **no UI**.

Audience: existing staff `php-api` (`require_staff_audience`). `php-patient`, `php-platform`, and `PatientPrincipal` do not gain note-write access.

Purpose: Healthcare Web sends `X-Purpose: TREATMENT`. Purpose is contextual justification only and does not grant `clinical.note.create` / `update_draft` / `finalize`.

Permissions (unchanged): `clinical.note.create`, `clinical.note.update_draft`, `clinical.note.finalize`. Backend remains authority. No role-name checks.

---

## 3. Request DTOs

**Create** (`CreateClinicalNoteRequest`, `extra=forbid`):

```json
{
  "expected_patient_identity_id": "<uuid>",
  "encounter_id": "<uuid>",
  "note_type": "PROGRESS|ADMISSION|ED|DISCHARGE|OTHER",
  "body_text": "<plain text, 1–20000 after strip>"
}
```

Required header: `Idempotency-Key` (8–128 `[A-Za-z0-9._-]`). Missing → 422 `idempotency_key_required`. Malformed → 422 `invalid_idempotency_key`.

Rejected as client authority: `organization_id`, `facility_id`, persisted `patient_identity_id`, `author_id`, `signer_id`, `status`, `version`.

**Draft update** (`UpdateClinicalNoteRequest`):

```json
{
  "expected_patient_identity_id": "<uuid>",
  "expected_version": 1,
  "body_text": "<plain text>"
}
```

No `Idempotency-Key`. Cannot mutate patient, encounter, organization, facility, author, note type, or status.

**Finalize** (`FinalizeClinicalNoteRequest`):

```json
{
  "expected_patient_identity_id": "<uuid>"
}
```

Required `Idempotency-Key`. No `expected_version`. Row lock + DRAFT precondition.

HTTP success (including replay): **200**.

---

## 4. Patient-context precondition (not write authority)

`expected_patient_identity_id` is a **precondition only**. It is never persisted as `note.patient_identity_id`.

Create copies `Encounter.patient_identity_id`. Update/finalize leave the historical binding unchanged.

**Ordering:** current-org visibility (`_require_visible_identity`) **before** canonical comparison. Do not canonicalize a foreign identifier and then treat the survivor as a current-org oracle.

**Same-person:** `resolve_canonical(expected) == resolve_canonical(bound)` **and** the stored bound id is a member of `list_cluster_identity_ids` (ACTIVE + MERGED_IN). Historical ids are not rewritten.

| Case | Result |
|---|---|
| Same-org wrong patient (P1 selected, E2 for P2) | 404 conceal; zero note |
| Cross-org encounter | 404 conceal; no foreign details |
| Historical encounter stores X, later MERGED into Y, selected Y | allow; new note copies Encounter’s stored identity |
| RETIRED expected or bound | 409 `identity_not_usable` |
| MERGED historical bound with visible survivor | allow via cluster rule |

---

## 5. Encounter picker and status

Frontend picker: frozen Clinical Read `GET /api/v1/clinical/patients/{id}/chart/sections/encounters` only. Not `GET /clinical/encounters?patient_identity_id=`.

Picker is UX. Backend reloads and validates `encounter_id` at mutation time.

**Status (frozen backend, not invented):** notes allowed except `CANCELLED` and `ENTERED_IN_ERROR`. `PLANNED`, `IN_PROGRESS`, and `FINISHED` may receive notes. Frontend filter is UX only (`PLANNED` / `IN_PROGRESS` / `FINISHED`). Backend re-checks → 409 `encounter_not_documentable`.

No latest-encounter auto-selection.

---

## 6. Organization and facility

Organization: `X-Organization-Id` + `Principal.for_organization`. No body override.

Facility header omission does **not** bypass explicit facility scope. Extra `authorize` when header is absent and the encounter/note has a facility.

**Create matrix**

| | Encounter facility | Header | Result |
|---|---|---|---|
| A | A | A | allow; note facility A |
| B | A | B | 409 `encounter_facility_mismatch` |
| C | A | absent | allow only if actor authorized for A; note inherits A |
| D | null | A | allow if header facility accessible; note facility A |
| E | null | absent | allow; note facility null |

Header-absent + actor scoped only to facility B while encounter is A: **403**.

**Update / finalize:** A+A allow; A+B 409 `note_facility_mismatch`; A+absent extra authorize for A, no re-attribution; null+A allow, **do not set** facility; null+absent allow.

---

## 7. Attribution immutability

After create, UPDATE cannot change `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `author_id`, `note_type`. Migration `0019` extends `prevent_final_clinical_note_content_mutation()`. FINAL body immutability from `0005` remains. Frontend has no controls for those fields.

Author is the authenticated principal. Cross-author finalize is **unchanged**: a principal with `clinical.note.finalize` may finalize another author’s draft (P2 product-policy debt). Audit actor is the finalizing principal.

---

## 8. Idempotency (`20260814_0019`)

Table `clinical_note_write_idempotency`:

- `id`, `organization_id` (FK organizations), `actor_id`, `operation`, `idempotency_key`, `request_fingerprint` CHAR(64), `note_id` (deferred FK clinical_notes), `created_at`
- Unique `(organization_id, actor_id, operation, idempotency_key)` named `uq_clinical_note_write_idempotency_scope`
- `operation` CHECK `NOTE_CREATE` \| `NOTE_FINALIZE`
- Insert-only trigger `trg_clinical_note_write_idempotency_immutable`
- No note body, name, MRN, NIK, BPJS

`app_dml`: SELECT + INSERT only (grants in `scripts/grant_dev_privileges.sql`, not Alembic). No UPDATE / DELETE / TRUNCATE.

**Fingerprint (hardening; stored-body semantics):**

- CREATE: SHA-256 hex of canonical JSON `{"body_sha256","encounter_id","expected_patient_identity_id","note_type"}` (`sort_keys`, compact separators). `body_sha256` is SHA-256 of the **stripped stored** body UTF-8. No raw body stored. Not facility header.
- FINALIZE: SHA-256 hex of canonical JSON `{"expected_patient_identity_id","note_id"}`.
- Same-person historical vs canonical expected ids with the same key → 409 `idempotency_key_conflict` (stricter than the original design convenience replay).

Replay is a **current command**. Order: authorize (permission/purpose/org/header facility) → expected identity visibility (current org before canonical) → lock encounter/note → same-person / RETIRED / encounter status → current facility vs stored resource → then fingerprint compare. Matching key/fingerprint never returns 200 before those checks.

Create claims the unique row (preallocated `note_id`, deferred FK) in a nested savepoint, then inserts note + provenance + audit. Unique violation → SELECT winner, compare fingerprint → 200 replay or 409 `idempotency_key_conflict`. Concurrent same-key create: exactly one note, one `CLINICAL_NOTE_CREATED`, one provenance, one idempotency row.

Same key + same request: 200 existing note; no second audit/provenance/idempotency row.  
Same key + different request: 409; no body echo.

Create and finalize are separate operations.

---

## 9. Versioning and locking

Reuse `clinical_notes.version`. Initial **1**. Each successful draft update: `version = version + 1`. Finalize does **not** increment.

Draft update: `SELECT … FOR UPDATE`, then DRAFT, `expected_version`, patient, facility, retired/usability.

Stale version: 409 `note_version_conflict`; no body update; no success audit.  
Update after FINAL: 409 `note_not_draft`; never overwrite FINAL body.

Races: if update commits first, finalize operates on the latest committed draft; if finalize wins, later update sees FINAL → `note_not_draft`. Double finalize with different keys: 409 `note_not_draft`; one FINAL; one `CLINICAL_NOTE_FINALIZED`.

---

## 10. Body, audit, provenance, privacy

Plain `body_text`, max 20000, strip then reject empty/whitespace (`note_body_required`). No HTML. Unicode preserved (Indonesian, English, Simplified Chinese, medical punctuation). Frontend does not silently truncate.

Audit (no body): `CLINICAL_NOTE_CREATED` `{note_type, purpose}`; `CLINICAL_NOTE_UPDATED` `{purpose}`; `CLINICAL_NOTE_FINALIZED` `{purpose}`. No duplicate audit on replay.

Provenance: create records existing clinical provenance. Update/finalize follow frozen existing behavior. No frontend-controlled provenance.

`_REDACT_KEYS` includes `body_text`. Global 422 handler discards Pydantic `input` (`del exc`). Dedicated test sends a malformed DTO with a unique secret and asserts it is absent from the response.

`MAX_REQUEST_BYTES` remains 1 MiB (P3; not redesigned).

---

## 11. Frontend form

Route: existing `/app/clinical/chart` Notes section. Components: `ClinicalNoteForm`, encounter `<select>`, `UnsavedWorkDialog`, finalize confirmation, status text. No React Hook Form. No autosave. No GET note body. No draft reopen from Chart. No entered-in-error control. No `dangerouslySetInnerHTML`.

Requires frozen `PatientSelectionContext`. No selected patient / org mismatch: no form, no mutation. PatientSafetyBanner remains visible. Encounter context: class, label, time, facility, status. No NIK/BPJS.

Mutations: `retry: false`. One opaque create key per logical create; reuse on explicit retry; retire after confirmed success. Same for finalize. Successful create keeps `note_id` / `version` / DRAFT / body in memory. Subsequent save sends `expected_version`. Version conflict: safe message; no text merge (reopen deferred).

Invalidate **notes section + timeline only** for the mutation's **captured** organization/patient, even if the UI has moved on. Do not apply the payload or toast under a different patient/org. Late Patient A success/error is not applied under Patient B.

Unsaved body: React state only. Dirty = meaningful trimmed text that differs from last saved. Stay / Discard for Change Patient, Close Patient, org switch, facility switch, in-app link navigation, chart-view leave, voluntary logout (Discard and log out). 401 / session expiry: **no modal**; `clearSensitiveClientState` wipes immediately (documented MVP tradeoff). `beforeunload` for reload/tab close. Dirty form also pushes a same-URL history sentinel and handles `popstate` (Stay re-pushes; Discard allows the Back). Frozen `BrowserRouter` still cannot use `useBlocker`. `UnsavedWorkDialog` captures internal `<a href>` clicks while dirty. Chart tab changes use `confirmDiscardUnsavedWork("chart-view")`.

AbortSignal stops frontend waiting; it is **not** a transactional cancel. UI copy: the browser stopped waiting; that does not mean the server cancelled the save.

---

## 12. Tests and quality gates

Backend: `tests/unit/test_clinical_note_write_idempotency.py`, `tests/integration/test_clinical_note_write.py`, plus additive headers on existing note-create callers.

Frontend: `src/chart/notes/clinical-note-write.test.tsx`; notes section now also loads encounters; security scan allows POST note paths and still forbids GET note-by-id.

| Gate | Result |
|---|---|
| Frontend tests | **178 passed** (frozen baseline 167) |
| lint / typecheck / production build | 0 errors, 0 warnings |
| `npm audit --omit=dev` | 0 vulnerabilities |
| OpenAPI source `--check` | pass (backend venv Python; not Docker `:9100`) |
| Backend pytest | **454 passed** (frozen baseline 442) |
| ruff check / ruff format --check / mypy app | pass |
| Alembic | `20260814_0019` one head |
| `/api/v1/health/live` and `/ready` | 200 (postgres, redis, object_storage ok) against **stale** Docker image |

---

## 13. Findings

**P0:** none.

**P1:** none remaining in this implementation (wrong-patient, cross-org, header-absent facility scope, concurrent create, FINAL overwrite, RETIRED, late A-under-B, unsaved tenant carry are covered by tests/guards).

**P2:**

- Cross-author finalize remains inherited product-policy debt.
- Inherited DENIED-audit rollback unchanged.
- `GET /clinical/notes/{id}` is an authorized frozen backend command (`clinical.note.read`, org isolation, purpose). MVP form does not call it. Not classified as a defect.

**P3:**

- Docker backend image created 2026-08-14; source/0019 lag. Do not rebuild in this pass. Health/ready reflects the running image, not this source.
- `max_request_bytes` 1 MiB Content-Length limiter unchanged.
- `npm run check:api-types` uses system `python3`; drift check must use the backend virtualenv.

---

## 14. Contract deviations (design wins)

- CREATE fingerprint is canonical JSON SHA-256 including `expected_patient_identity_id` (hardening defense-in-depth; same-person X vs Y with the same key is 409 `idempotency_key_conflict`).
- FINALIZE fingerprint is canonical JSON SHA-256 of `note_id` + `expected_patient_identity_id`.
- Navigation guard is click-capture + history sentinel/`popstate` + existing confirm helpers, not React Router `useBlocker`.

---

## 15. Out of scope (unchanged)

Draft reopen, note-body Chart GET, entered-in-error UI, amendment, Condition/Medication/Allergy/Observation/lab/Procedure writes, attachments, templates, rich text, AI, Clinical Read Core, MPI semantics, ProductAccessPDP, Wave1PolicyPDP, hardening gate, freeze, commit, tag, push.
