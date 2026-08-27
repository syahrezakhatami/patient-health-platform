# Clinical Note write workflow — hardening gate

**Date:** 2026-08-27  
**Kind:** HARDENING GATE — not freeze  
**Baseline:** `3157ad9947f3f46d084df84982ee3b370f1c1a29` (`clinical-chart-ui-frozen`; annotated tag object peels to this SHA)  
**Parent:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Alembic:** `current == heads == 20260814_0019` (exactly one head; parent `20260814_0018`; no `0020`)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, push, or freeze in this pass.

Authoritative design: `docs/architecture/clinical-note-write-workflow-design.md` and `docs/gates/clinical-note-write-workflow-design-approval.md`.  
Implementation: `docs/architecture/clinical-note-write-workflow-implementation.md`.

---

## Verdict

**CLINICAL NOTE WRITE BACKEND = IMPLEMENTED**

**CLINICAL NOTE FORM = IMPLEMENTED**

**CLINICAL NOTE WRITE HARDENING = COMPLETE**

**CLINICAL NOTE WRITE WORKFLOW = NOT FROZEN**

**MIGRATION 0019 = CREATED**

**MIGRATION 0019 = NOT FROZEN**

**OTHER CLINICAL WRITES = NOT IMPLEMENTED**

**NO COMMIT / NO TAG / NO PUSH**

---

## 1. Baseline

| Item | Result |
|---|---|
| Published HEAD | `3157ad9947f3f46d084df84982ee3b370f1c1a29` |
| Tag | `clinical-chart-ui-frozen` peels to the same SHA |
| Parent | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Branch | `main` == `origin/main` |
| Working tree | uncommitted Clinical Note write implementation + this hardening pass |
| Frozen Clinical Read Core / MPI / ProductAccessPDP / Wave1PolicyPDP | not modified except approved note-write deltas |
| Other clinical writes | not implemented |
| New routes | none |
| Migration 0020 | not created |

---

## 2. Migration 0019

File: `backend/alembic/versions/20260814_0019_clinical_note_write_idempotency.py`.

**Contents only:** `clinical_note_write_idempotency` table, unique scope, deferred note FK, insert-only trigger, attribution-immutability strengthening on `prevent_final_clinical_note_content_mutation`. No GRANT. No unrelated schema.

**Upgrade 0018 → 0019:** one head; table, unique constraint, and immutable trigger exist. Live `alembic current` == `20260814_0019`.

**Downgrade 0019 → 0018:** restores the 0005 note trigger, drops the idempotency trigger/function/table. Pre-existing `clinical_notes` remain. Roundtrip test upgrades back to 0019.

**Schema downgrade vs operational rollback:** downgrade **drops** `clinical_note_write_idempotency`. That is not an operationally safe production rollback once idempotency rows exist. Production rollback is a separate restore/backup strategy. Not claimed safe here.

---

## 3. Fingerprint deviation analysis

**Implementation before this pass:** CREATE hashed `encounter_id\|note_type\|sha256(body)` (delimiter concat, no expected patient). FINALIZE hashed `note_id` only. Replay ran **before** patient/facility/RETIRED checks.

**Corrected design** stored `expected_patient_identity_id` as a precondition and originally omitted it from the fingerprint so same-person X vs Y could replay.

**This hardening pass** treats wrong-patient replay as a P1 and section 13 as requiring expected-patient differences that still pass safety context to 409. Fingerprint therefore now binds expected patient as defense-in-depth.

That tightens same-person X vs Y **same key** from 200 replay to **409 `idempotency_key_conflict`**. The write remains allowed with a **new** key. Wrong-person remains **404 conceal** because validation runs first.

---

## 4. Final fingerprint semantics

Canonical JSON (`json.dumps(..., separators=(",", ":"), sort_keys=True, ensure_ascii=False)`), then SHA-256 hex. No raw body stored.

**CREATE** keys:

```json
{
  "body_sha256": "<sha256 of stored stripped UTF-8 body>",
  "encounter_id": "<uuid>",
  "expected_patient_identity_id": "<uuid>",
  "note_type": "<enum>"
}
```

**FINALIZE** keys:

```json
{
  "expected_patient_identity_id": "<uuid>",
  "note_id": "<uuid>"
}
```

Facility header is not in the fingerprint. Current facility/permission still run on every command, including replay.

---

## 5. Body hashing semantics

Service strips `body_text` then stores that string. Fingerprint hashes the **stored stripped** body, not a different whitespace view.

`"  Stored assessment.  "` and `"Stored assessment."` with the same key replay 200 to one stored body `"Stored assessment."`. Whitespace-only bodies remain 422 `note_body_required` before fingerprinting. No silent truncation at 19999 / 20000; 20001 → 422.

---

## 6. Replay validation ordering

A replay is a **current clinical command**.

**CREATE:** strip body → `authorize` (permission, purpose, org, header facility) → current-org expected identity visibility (**before** canonical hop) → lock encounter → same-person / RETIRED bound identity → encounter status → current actor vs encounter facility → fingerprint compare → 200 existing note or 409 conflict or insert.

**FINALIZE:** `authorize` → expected identity → lock note → same-person / RETIRED → current actor vs **stored note** facility → fingerprint compare → 200 even if already FINAL (same key) → else claim, assert DRAFT, one FINAL transition.

DRAFT is **not** asserted before same-key replay lookup (otherwise double finalize same key would 409 `note_not_draft`).

---

## 7. Wrong-patient / facility / permission replay

| Case | Result |
|---|---|
| Create Patient A + key K, replay K with expected Patient B | **404 conceal**. No note-A body/id under B. Zero extra note. |
| Finalize Note A + Patient A + key F, replay F with expected Patient B | **404 conceal**. Note stays FINAL from the original command only. |
| Same-person historical vs canonical expected id, same key | **409 `idempotency_key_conflict`** after safety context. No body echo. |
| Original create while Facility A authorized; membership moved to B; replay | **403**. Not a 200 replay. |
| Permission revoked (role → registrar); replay | **403**. |
| Missing / invalid purpose; replay | **422**. |
| `ADMINISTRATION` purpose with current `clinical.note.create` | **200 replay**. Purpose remains Wave1 **audit context**, not a grant. `authorize()` still ran. Not a TREATMENT-only product change (would be BLOCKED if invented). |

Idempotency is duplicate suppression, not perpetual authorization.

---

## 8. Idempotency concurrency and atomicity

Same scoped key + same fingerprint: 200 existing resource; no second note, `CLINICAL_NOTE_CREATED` / `CLINICAL_NOTE_FINALIZED` audit, provenance, or idempotency row.

Same scoped key + different material input (patient after safety, encounter, type, body, finalize note id): 409 `idempotency_key_conflict`; no fingerprint/body echo.

**Concurrent same-key create (real DB):** notes = 1, `CLINICAL_NOTE_CREATED` = 1, create provenances = 1, idempotency rows = 1.

**Concurrent same-key different body:** at most one note; other 409; never two notes.

**Concurrent same-key finalize:** both 200; one FINAL; one `CLINICAL_NOTE_FINALIZED`; version unchanged.

Pattern: nested savepoint inserts the idempotency row with a preallocated `note_id` (deferred FK) **before** note/provenance/audit. Unique violation rolls back only that savepoint; the loser SELECTs the winner. Note + audit + provenance + mapping commit in **one** outer transaction. No committed orphan note.

Replay loads only `existing.note_id` in the same org via `_visible_note`. `note_id` is NOT NULL. Cross-scope mappings cannot be selected.

---

## 9. Idempotency table privacy and logging

Columns: `id`, `organization_id`, `actor_id`, `operation`, `idempotency_key`, `request_fingerprint`, `note_id`, `created_at`. No `body_text`, name, MRN, NIK, BPJS, title.

`Idempotency-Key` is caller-generated operational metadata. `_REDACT_KEYS` now includes `idempotency_key` / `idempotency-key` / `request_fingerprint` / `body_text`, and redaction walks nested maps. Keys are not combined with body PHI in application logs.

---

## 10. DB trigger, `app_dml`, attribution, FINAL

Direct UPDATE/DELETE on idempotency rows → denied (`immutable`). TRUNCATE → permission denied.

`app_dml`: SELECT + INSERT allowed; UPDATE/DELETE/TRUNCATE denied. Grants live in `scripts/grant_dev_privileges.sql` only.

Attribution trigger: `patient_identity_id`, `encounter_id`, `organization_id`, `facility_id`, `author_id`, `note_type` cannot change. Draft body/version still update through the service. FINAL body cannot be changed on the application path (`note_not_draft` + trigger).

---

## 11. Same-person, canonicalization, RETIRED

Historical X merged to canonical Y; expected Y + encounter X → allowed; stored binding remains X.

Same-org P1 + encounter P2 → 404 conceal; zero write.

Cross-org → 404 conceal.

Foreign expected identity is rejected on **current-org visibility** before canonical resolution. No MPI hop oracle (foreign expected cannot discover a local survivor and write).

RETIRED expected or bound identity: create 409 `identity_not_usable`, zero note. Draft then RETIRED: update 409, no body/version change; finalize 409, remains DRAFT, zero FINAL audit.

---

## 12. Facility matrix

| Create | Result |
|---|---|
| enc A / header A | allow, note facility A |
| enc A / header B | 409 `encounter_facility_mismatch` |
| enc A / no header, ALL_IN_ORGANIZATION | allow, inherit A |
| enc A / no header, explicit Facility B only | **403** (header absence does not widen scope) |
| enc null / header A | allow, note facility A |
| enc null / no header, ALL_IN_ORGANIZATION | allow, facility null |

Update/finalize: note A / header A allow; header B 409 `note_facility_mismatch`; header absent authorized allow; header absent unauthorized 403; null-facility note / header A or absent allow for ALL_IN_ORGANIZATION. No attribution rewrite.

---

## 13. Encounter status

Matches corrected design §461 and frozen backend source: notes allowed except `CANCELLED` / `ENTERED_IN_ERROR`.

**PLANNED** (AMB default) and **FINISHED** are explicitly tested and retained. Not invented in this pass. Frontend UX filter matches (`PLANNED` / `IN_PROGRESS` / `FINISHED`). Backend re-checks.

---

## 14. Version and finalize concurrency

Create version == 1. Replay does not increment.

Valid update: version +1 once; one `CLINICAL_NOTE_UPDATED`.

Stale `expected_version`: 409 `note_version_conflict`; no body change; no success audit.

Update vs finalize `FOR UPDATE`: if update commits first, finalize signs the latest DRAFT; if finalize commits first, update 409 `note_not_draft`. No lost FINAL overwrite.

Double finalize different keys: 409 `note_not_draft`; one FINALIZED audit.

Finalize does not increment version.

---

## 15. Cross-author finalize and GET note

**Cross-author finalize:** another clinician with `clinical.note.finalize` in the same org can finalize. Author id is unchanged. Inherited product-policy debt (**P2**). Not a new authorization-model violation.

**GET `/api/v1/clinical/notes/{id}`:** existing frozen command. `clinical.note.read` + TREATMENT/purpose header + org isolation + 404 conceal cross-org. Chart notes section remains metadata-only. **Not a P2** merely because the form does not call it. Classified as an existing backend capability / frontend-deferred surface.

MVP form performs **zero** GET-by-id. No draft reopen. No Chart note-body viewer. Security scan still forbids GET note-by-id.

---

## 16. Frontend mutation keys, network, abort, late responses

One logical create → one stable `Idempotency-Key`. Ambiguous retry reuses it. Confirmed success retires it; later edits use the update route.

Same for finalize. Confirmed FINAL retires the finalize key; no second Finalize control.

All note mutations: `retry: false`, `gcTime: 0`. No automatic POST retry.

Network ambiguity: UI does not assume “not saved” as rollback. Explicit retry uses the same create key; server 200 replays.

Abort after dispatch: copy `note.abortNotRollback` — waiting stopped is not a server rollback. DB may contain the note.

Late Patient A create/update/finalize must not populate Patient B form, note id/version, success toast, or B-specific UI. Mutation success **always** invalidates notes + timeline for the mutation’s **captured** org/patient, never the currently selected B keys.

Successful create/update/finalize invalidate **notes + timeline only**. No summary/conditions/allergies/medications/labs fan-out. Draft update invalidates those two domains exactly as designed.

MutationCache: cleared on success, error, discard, tenant/patient/facility wipe, 401, logout. Raw `body_text` must not remain. Unsaved body is React state only (no localStorage / sessionStorage / IndexedDB / URL / Cache API / cookies / BroadcastChannel).

---

## 17. Unsaved guards and browser Back

Dirty Change Patient / Close Patient / org / facility / in-app `<a href>` capture: Stay (no context change) or Discard (wipe text first, then transition).

Voluntary logout: Stay or Discard and Logout; body wiped with logout.

401: **no modal**; immediate wipe of auth, patient, chart PHI, form body, mutation state.

Facility/permission revocation: backend 403 remains authority; form shows `note.forbidden`; no retry; not marked saved. Buttons follow last fetched permissions after context refresh.

**Browser Back:** `beforeunload` covers reload/tab close. Dirty form also pushes a same-URL history sentinel and handles `popstate` (Stay re-pushes; Discard then `history.back()`). In-app links remain click-captured. Frozen `BrowserRouter` still cannot use `useBlocker`. Extra sentinel history entries while dirty are **P3 UX**, not a Back bypass. Hardening is **not** blocked on this item.

---

## 18. Body validation, Unicode, XSS, 422/audit privacy

19999 / 20000 accepted; 20001 422; no echo of the long payload.

`""` / spaces / tabs / newlines-only → 422.

Indonesian, Simplified Chinese, combining `e\u0301`, warning emoji: stored and fingerprint-replayed without corruption.

HTML/script-like text stored as plain text; confirmation/form render escaped; no `dangerouslySetInnerHTML`.

Malformed 422: no `body_text` in `detail.input` / custom payload.

409s (wrong patient, facility, version, idempotency, `note_not_draft`, `identity_not_usable`) do not echo body, name, MRN, or foreign encounter metadata.

Audits `CLINICAL_NOTE_CREATED` / `UPDATED` / `FINALIZED`: no body_text; metadata `{note_type?, purpose}`. Replay: zero extra audit. Provenance on create only; replay does not add a second row; no body in provenance metadata.

---

## 19. Encounter picker, finalize confirmation, no EIE / reopen

Picker uses `/chart/sections/encounters` only (no canonical encounter list). Merged historical encounters remain selectable when authorized. Late Patient A list does not populate Patient B. Empty list vs 403/error are distinct copy (`note.noEncounters` vs `note.encountersUnavailable`). No create without an encounter.

Finalize confirmation: current patient display name, encounter label, org, facility, draft state, author. No NIK/BPJS. Explicit confirm required.

After FINAL: non-editable; no Save Draft; no second Finalize command.

No entered-in-error button or route call. Refresh does not restore draft body from browser storage.

---

## 20. Rate limit, Content-Length, OpenAPI

Existing global limiter (`rate_limit_per_minute` default 120) covers mutations. No unapproved threshold added. Coarse IP limiter remains inherited debt, not a new note-write defect.

`MAX_REQUEST_BYTES` 1 MiB is **Content-Length-based**. Transfer encodings without Content-Length are **P3**; not a proxy redesign in this pass.

OpenAPI generated from source (venv Python, not Docker). Create/update/finalize DTOs match. Frontend wrappers use generated types.

---

## 21. Quality gates

| Check | Result |
|---|---|
| Frontend tests | **184 passed** (implementation 178; frozen 167) |
| lint (`oxlint --deny-warnings`) | 0 errors / 0 warnings |
| typecheck | pass |
| production build | pass |
| `npm audit --omit=dev` | 0 vulnerabilities |
| OpenAPI source `--check` | pass |
| ruff check / format | pass |
| mypy `app` | pass |
| pytest | **467 passed** (implementation 454; frozen 442) |
| Alembic | `current == heads == 20260814_0019`; one head; no 0020 |
| `/api/v1/health/live` | 200 |
| `/api/v1/health/ready` | 200 postgres / redis / object_storage ok |
| Health runtime | **stale Docker** `backend-backend-1` created 2026-08-14; **does not exercise 0019 source** |
| Secret / PHI scan | synthetic fixtures only |

---

## 22. Findings

**P0:** none.

**P1:** none remaining. Replay-before-validation, delimiter fingerprint, wrong-patient replay, concurrent duplicate create, FINAL overwrite, RETIRED write, late A-under-B, unsaved tenant carry, and header-absent facility widening are fixed or proven.

**P2:**

- Cross-author finalize remains inherited product-policy debt (authorization model allows it).
- Inherited DENIED-audit rollback unchanged.
- Purpose is Wave1 contextual justification: `ADMINISTRATION` with current note-create permission can replay. Not changed (PDP out of scope).

**P3:**

- Docker backend image created 2026-08-14; source/0019 lag. Do not rebuild in this pass.
- Content-Length 1 MiB limiter does not cover all transfer encodings.
- No note status index (pre-existing).
- Tooling: OpenAPI scripts require backend venv Python.
- Dirty-form history sentinel can leave an extra same-URL history entry.
- Schema downgrade of 0019 drops the idempotency table (not an operational rollback).

`GET /clinical/notes/{id}` existence is **not** a P2.

---

## 23. Docker

**P3 deployment lag:** running image is stale relative to Clinical Note write source. Migration 0019 is **not** represented in that image. Health/ready reflects the image, not this working tree. Do not rebuild automatically.

---

## 24. Out of scope (unchanged)

Draft reopen, note-body Chart GET UI, entered-in-error UI, amendments/addenda, attachments, templates, rich text, AI, autosave, other clinical writes, new routes, migration 0020, Clinical Read Core, MPI semantics, ProductAccessPDP, Wave1PolicyPDP, freeze, commit, tag, push.
