# Clinical Note write workflow — design approval gate

**Date:** 2026-08-27  
**Kind:** DESIGN APPROVAL — not implementation  
**Verdict:** CLINICAL NOTE WRITE WORKFLOW DESIGN = APPROVED FOR IMPLEMENTATION  
**Correction:** pre-implementation safety contract (server-observable patient context)  
**Baseline HEAD:** `3157ad9947f3f46d084df84982ee3b370f1c1a29` (`clinical-chart-ui-frozen`)  
**Parent:** `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`)  
**Alembic:** heads `20260814_0018` (exactly one head)  
**Migration 0019:** REQUIRED (not created on this pass)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize implementing Clinical Note writes, clinical forms, other clinical mutations, AI, Clinical Read Core changes, Encounter production changes, MPI/PDP changes, commit, tag, or push.

Source: `docs/architecture/clinical-note-write-workflow-design.md`.

---

## 1. Baseline

| Item | Result |
|---|---|
| HEAD | `3157ad9947f3f46d084df84982ee3b370f1c1a29` |
| Tag | `clinical-chart-ui-frozen` peels to the same SHA |
| Parent | `007af5c5fffd095124013eba239913c00ceeff6b` |
| Branch | `main` == `origin/main` |
| Uncommitted (this design series) | `docs/architecture/clinical-note-write-workflow-design.md`, `docs/gates/clinical-note-write-workflow-design-approval.md` only |
| Frozen Chart UI / Clinical Read / Lookup / Shell / IAM / Encounter / Clinical Note / MPI / Product Access / PDPs | unchanged |
| Migration `0019` file | **absent** |

If this table were materially wrong, this pass would STOP.

---

## 2. Explicit decisions

FIRST WRITE CAPABILITY = CLINICAL NOTE

ENCOUNTER REQUIRED = YES

SELECTED PATIENT REQUIRED = YES

PATIENT CONTEXT PRECONDITION = required JSON field `expected_patient_identity_id` on CREATE, UPDATE DRAFT, and FINALIZE (decision A; same existing routes)

PATIENT CONTEXT IS AUTHORITY = NO

ENCOUNTER/PATIENT MATCH = `resolve_canonical(expected)` equals `resolve_canonical(encounter_or_note.patient_identity_id)` AND `encounter_or_note.patient_identity_id ∈ list_cluster_identity_ids(canonical)` (ACTIVE + MERGED_IN). Historical id is not rewritten. Fail → 404 conceal (`Encounter not found` / `Clinical note not found`). Cross-org expected patient → 404 `Patient identity not found`. Same-org P1+E2 → 404, **zero notes**.

ENCOUNTER PICKER SOURCE = `GET /api/v1/clinical/patients/{patient_identity_id}/chart/sections/encounters` (cluster-aware). Not command `GET /api/v1/clinical/encounters?patient_identity_id=`.

CREATE REQUEST = `{ expected_patient_identity_id, encounter_id, note_type, body_text }` + headers Authorization, X-Organization-Id, optional X-Facility-Id, X-Purpose TREATMENT, required Idempotency-Key

UPDATE REQUEST = `{ expected_patient_identity_id, expected_version, body_text }` + same org/purpose/facility headers. Idempotency-Key not required. No mutation of patient/encounter/org/facility/author/type/status.

FINALIZE REQUEST = `{ expected_patient_identity_id }` + required Idempotency-Key + same headers. No `expected_version`.

WORK FACILITY REQUIRED = CONDITIONAL

FACILITY MATRIX =

| Case | Encounter/note facility | X-Facility-Id | CREATE | UPDATE/FINALIZE |
|---|---|---|---|---|
| A | A | A | allow; note=A | allow; no change |
| B | A | B ≠ A | 409 `encounter_facility_mismatch` | 409 `note_facility_mismatch` |
| C | A | absent | allow; note=A | allow; no change |
| D | absent | A | allow; note=A | allow; **do not** set facility |
| E | absent | absent | allow; note=null | allow; no change |

Facility/org/author/`note_type` immutable after create (0019 trigger). No silent header preference.

RETIRED CHECK = CREATE **and** UPDATE DRAFT **and** FINALIZE reject 409 `identity_not_usable` if expected or bound identity is RETIRED / not resolvable to an active canonical. MERGED with survivor in cluster is allowed.

PURPOSE = TREATMENT (Healthcare Web). Purpose is not a grant.

CREATE PERMISSION = `clinical.note.create`

UPDATE PERMISSION = `clinical.note.update_draft`

SIGN PERMISSION = `clinical.note.finalize`

NOTE BODY FORMAT = plain text (`body_text`)

DRAFT = SUPPORTED

SIGN/FINALIZE = IN MVP

SIGNED NOTE MUTABLE = NO

POST-SIGN CORRECTION = DEFERRED (EIE UI not in first implementation)

AUTHOR = AUTHENTICATED PRINCIPAL

SIGNER = audit actor on finalize; no `signer_id`; cross-author finalize remains frozen P2 (not redesigned)

IDEMPOTENCY HEADER = `Idempotency-Key` required on CREATE and FINALIZE; opaque 8–128 `[A-Za-z0-9._-]`; 422 if missing/invalid

IDEMPOTENCY SCOPE = unique `(organization_id, actor_id, operation, idempotency_key)` with `operation` `NOTE_CREATE` \| `NOTE_FINALIZE`

IDEMPOTENCY REPLAY = same scope key + same fingerprint → 200 existing `ClinicalNoteResponse`; no second note/audit/provenance

IDEMPOTENCY CONFLICT = same key + different fingerprint → 409 `idempotency_key_conflict`; no body echo

IDEMPOTENCY STORAGE = table `clinical_note_write_idempotency` (id, organization_id, actor_id, operation, idempotency_key, request_fingerprint CHAR(64), note_id, created_at). Fingerprint is SHA-256 hex. CREATE fingerprint = `encounter_id \| note_type \| sha256(stripped body)`. FINALIZE fingerprint = `note_id`. No raw body stored.

OPTIMISTIC VERSION = existing integer `clinical_notes.version` as JSON `expected_version`

VERSION INCREMENT = +1 on every successful draft update; not on finalize; create starts at 1. Stale → 409 `note_version_conflict`

FINALIZE CONCURRENCY = `SELECT FOR UPDATE` + `note_not_draft`; no `expected_version` on finalize. Same Idempotency-Key → replay 200; different key after FINAL → 409

DRAFT REOPEN = DEFERRED (same form session only; no GET `/notes/{id}`)

UNSAVED WORK GUARD = modal Stay vs Discard and continue for Change/Close Patient, org switch, facility switch, in-app navigation; `beforeunload` for reload; 401/logout security wipe wins (unsaved body lost)

AUTOSAVE = NO

UNSAVED PHI PERSISTENCE = NONE

POST-WRITE INVALIDATION = `clinicalKeys.section(org, patient, "notes")` and `clinicalKeys.timeline(org, patient)` after create, update, and finalize

NEW BACKEND ROUTES = NONE

MIGRATION 0019 = REQUIRED

MIGRATION 0019 CONTENT = revision `20260814_0019` parent `20260814_0018`; table `clinical_note_write_idempotency` + unique scope constraint + insert-only trigger; extend clinical note UPDATE trigger to freeze org/facility/author/`note_type`; **no** new `version` column

---

## 3. Additional frozen-aligned decisions

| Topic | Decision |
|---|---|
| Chart note body GET | Deferred. Not used to reopen drafts |
| Encounter statuses for notes | Not CANCELLED/EIE; FINISHED allowed (frozen backend) |
| Empty body | 422 `note_body_required` |
| Max length | 20000 |
| Update method | POST (existing) |
| Form library | Controlled React; no React Hook Form |
| Mutation retry | `retry: false` |
| AbortSignal | ≠ server rollback; retry create/finalize with same Idempotency-Key |
| Response guard | org + selected patient + encounter or note id + form generation |
| CSRF | Not applicable (bearer OIDC) |
| Cross-author finalize | Known P2; not changed |
| DENIED audit rollback | Inherited P2 |
| Historical MPI identity | Not rewritten |

---

## 4. Implementation-only scope (later PR)

Allowed: encounter-linked note form; existing three write routes with designed DTOs; 0019; cluster/facility/retired/version/idempotency in ClinicalService; unsaved modal; notes+timeline invalidation.

Forbidden: other clinical writes; EIE UI; draft reopen-by-id; Chart body viewer; AI/attachments/templates/voice; modifying Clinical Read Core, MPI internals (call existing helpers only), PDPs, Encounter module redesign; `/api/v2`; FHIR; commit/tag/push on the design pass.

---

## 5. P0 / P1 / P2 / P3

**P0:** none remaining in the **design**. Shipping create without `expected_patient_identity_id` or without 0019 would be P0.

**P1 (closed in this correction; must be implemented as specified):** server-observable patient-context precondition; cluster comparison; facility matrices; retired on create/update/finalize; idempotency uniqueness; `expected_version`; unsaved org/facility/patient switch modal.

**P2:** DENIED-audit rollback; historical identity non-rewrite; cross-author finalize; provenance not on update/finalize; coarse IP rate limit.

**P3:** no notes status index; Content-Length body limiter; local `alembic current` not live-rechecked this pass.

---

## 6. P1 readiness checklist

| Contract | Exact |
|---|---|
| Wrong-patient encounter rejection | 404 conceal, zero notes |
| Wrong-org encounter rejection | 404 conceal |
| Merged/historical comparison | canonical + cluster; persist encounter id |
| Facility mismatch | §2 matrix; 409 |
| Retired write | create/update/finalize 409 |
| Create idempotency | required header + 0019 unique scope |
| Concurrent duplicate prevention | unique constraint + single transaction |
| Stale draft version | 409 `note_version_conflict` |
| Signed immutability | `note_not_draft` + DB trigger |
| Unsaved patient/org/facility switch | Stay / Discard and continue modal |

---

## 7. Verdict

CLINICAL NOTE WRITE WORKFLOW DESIGN = APPROVED FOR IMPLEMENTATION

The previous gap (selected patient not server-observable) is closed by `expected_patient_identity_id` as a **precondition**, not write authority.

CLINICAL NOTE WRITE IMPLEMENTATION = NOT STARTED

MIGRATION 0019 = NOT CREATED
