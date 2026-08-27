# Clinical Note write workflow — final freeze

**Date:** 2026-08-27  
**Verdict:** PASS WITH P2  
**P0:** none  
**P1 unresolved:** none  
**CLINICAL NOTE WRITE BACKEND:** FROZEN  
**CLINICAL NOTE FORM:** FROZEN  
**CLINICAL NOTE WRITE WORKFLOW:** FROZEN  
**CLINICAL NOTE WRITE WORKFLOW:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not implement Condition, Medication, Allergy, Observation, laboratory, or Procedure writes; draft reopen; Chart note-body viewing; entered-in-error UI; amendments/addenda; attachments; templates; rich text; autosave; AI; scheduling; Patient Mobile; Platform Admin; FHIR; or `/api/v2`. Migration `0020` was not created. Frozen Clinical Read Core, MPI semantics, ProductAccessPDP, Wave1PolicyPDP, Patient Lookup & Selection, Healthcare Web Shell, and IAM context were not redesigned.

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` |
| Published parent SHA | `3157ad9947f3f46d084df84982ee3b370f1c1a29` |
| Published parent tag | annotated `clinical-chart-ui-frozen` → same SHA |
| Parent of that baseline | `007af5c5fffd095124013eba239913c00ceeff6b` (`patient-lookup-selection-frozen`) |
| Final freeze SHA | annotated tag `clinical-note-write-frozen` peel (this publication commit) |
| Final annotated tag | `clinical-note-write-frozen` → this publication commit |
| Alembic | `current == heads == 20260814_0019` (exactly one head; parent `20260814_0018`) |
| Migration `0020` | **Not created** |

Old tags were not moved or rewritten:

- `clinical-chart-ui-frozen`
- `patient-lookup-selection-frozen`
- `healthcare-web-shell-frozen`
- `iam-shell-context-frozen`
- `product-access-multi-org-context-isolation-frozen`
- `clinical-read-core-frozen`
- `product-access-tenancy-foundation-frozen`
- `wave-2b-clinical-foundation-complete`

Expected lineage:

```
clinical-chart-ui-frozen
3157ad9947f3f46d084df84982ee3b370f1c1a29
        |
        v
clinical-note-write-frozen
(this publication commit)
```

---

## B. Scope

Encounter-linked Clinical Note **create / draft update / finalize** on existing routes, migration `20260814_0019`, idempotency, attribution immutability, grant-script SELECT/INSERT, Healthcare Web Notes form, unsaved-work integration, captured notes+timeline invalidation, tests, design/implementation/hardening docs, source OpenAPI/types.

Existing tests that create notes were updated to the new DTOs/`Idempotency-Key` only. Product access / Clinical Read Core production code was not modified.

---

## C. Routes and DTOs

Existing routes only. Router remains `require_staff_audience` (`php-api`).

| Method | Path | MVP |
|---|---|---|
| POST | `/api/v1/clinical/notes` | create DRAFT |
| POST | `/api/v1/clinical/notes/{note_id}` | draft update |
| POST | `/api/v1/clinical/notes/{note_id}/finalize` | DRAFT → FINAL |
| GET | `/api/v1/clinical/notes/{note_id}` | **existing backend capability; form does not call it** |
| POST | `/api/v1/clinical/notes/{note_id}/entered-in-error` | untouched; **no UI** |

**Create:** `{ expected_patient_identity_id, encounter_id, note_type, body_text }` + required `Idempotency-Key`. `extra: forbid`. No client authority for patient binding, org, facility, author, signer, status.

**Update:** `{ expected_patient_identity_id, expected_version, body_text }`. No idempotency header. No attribution fields.

**Finalize:** `{ expected_patient_identity_id }` + required `Idempotency-Key`. No `expected_version`.

---

## D. Permission and purpose

| Command | Permission |
|---|---|
| CREATE | `clinical.note.create` |
| UPDATE | `clinical.note.update_draft` |
| FINALIZE | `clinical.note.finalize` |

No role-name checks. Patient/platform/wrong audience remain frozen-auth rejects.

**HEALTHCARE WEB NOTE PURPOSE = TREATMENT** (`X-Purpose: TREATMENT` on all form wrappers).

Backend: `X-Purpose` is catalogued/audited context, **not** an authorization grant. Wave1PolicyPDP was not changed. A caller with the mutation permission and a valid catalog purpose such as `ADMINISTRATION` may succeed; that is frozen purpose architecture, **not P2**.

---

## E. Patient context

`expected_patient_identity_id` is a **precondition only**. Never persisted as `note.patient_identity_id`.

CREATE binding derives from the encounter. UPDATE/FINALIZE keep the stored binding immutable.

Current-org visibility is established **before** canonical/same-person resolution. Foreign expected identity cannot canonicalize into a local survivor.

**Same-person:** canonical expected identity == canonical bound identity, and the historical bound id is in the approved visible cluster. Historical X is not rewritten when selected Y is the survivor.

Wrong-patient (same org, P1 + E2/P2): **404 conceal**, zero note, zero success audit, zero provenance.

Cross-org: **404 conceal**, no foreign metadata, zero mutation.

Merged historical encounter X + selected Y: write allowed; persisted `patient_identity_id` remains X.

---

## F. Encounter picker and status

Picker uses only `GET /api/v1/clinical/patients/{id}/chart/sections/encounters`. No canonical command-list fallback. Late Patient A lists do not populate Patient B. Authorized empty vs 403/error are distinct.

**Encounter status (design §461 + source):** notes allowed on `PLANNED`, `IN_PROGRESS`, `FINISHED`. Rejected: `CANCELLED`, `ENTERED_IN_ERROR` (`409 encounter_not_documentable`). Explicitly approved; not invented at freeze.

---

## G. Facility

| Create | Result |
|---|---|
| Enc A / header A | allow; note A |
| Enc A / header B | 409 `encounter_facility_mismatch` |
| Enc A / no header, actor authorized for A | allow; note A |
| Enc A / no header, **explicit Facility B only** | **403** (header absence does not widen scope) |
| Enc null / header A | allow if A accessible; note A |
| Enc null / no header | note null if otherwise authorized |

Update/finalize: note A / header A allow; header B 409 `note_facility_mismatch`; header absent only with current A authority; null-facility note / header A allow **without reattribution**. Facility is immutable after create.

---

## H. RETIRED

CREATE / UPDATE / FINALIZE with expected or bound identity RETIRED/unusable: **409 `identity_not_usable`**. No body/version change. Draft stays DRAFT. No FINAL audit.

---

## I. Idempotency

**Scope:** `(organization_id, actor_id, operation, idempotency_key)` where operation is `NOTE_CREATE` or `NOTE_FINALIZE`.

**CREATE fingerprint:** SHA-256 of canonical JSON  
`{"body_sha256","encounter_id","expected_patient_identity_id","note_type"}`  
(`sort_keys`, compact separators). `body_sha256` is SHA-256 of the **stored stripped UTF-8** body. Padding that storage strips is the same mutation. Meaningful content differs. No raw body in the table. No delimiter concatenation.

**FINALIZE fingerprint:** SHA-256 of canonical JSON  
`{"expected_patient_identity_id","note_id"}`.  
Same key + different expected patient does not replay.

**Replay order (create and finalize):** authenticate → org/membership → mutation permission → valid purpose → expected identity visible in current org → lock encounter/note → same-person → RETIRED/usability → resource status → current facility authority → fingerprint compare → replay / conflict / new mutation.

Wrong-patient replay: 404, not 200. Facility-revoked replay: 403. Permission-revoked replay: 403. Missing/invalid purpose: 422. Same key + same fingerprint after safety: 200 existing resource; no second note/audit/provenance/idempotency row. Same key + different request: 409 `idempotency_key_conflict`.

**Concurrent identical create (real PostgreSQL):** 1 note, 1 `CLINICAL_NOTE_CREATED`, 1 create provenance, 1 idempotency row (one create, one replay).

**Concurrent same key, different body:** at most 1 note; other 409; never 2 notes.

**Atomicity:** nested savepoint inserts the idempotency row with a preallocated `note_id` (deferred FK) **before** note/provenance/audit. Unique violation rolls back only that savepoint. Outer transaction commits mapping + note + audit + provenance together, or none.

Table columns: ids, operation, key, fingerprint, timestamps. No body, name, MRN, NIK, BPJS, prose.

UPDATE/DELETE/TRUNCATE of idempotency rows denied (trigger + `app_dml` revoke). `app_dml`: SELECT+INSERT. Grants live in `scripts/grant_dev_privileges.sql`, not Alembic (**inherited operational P3**). After Alembic recreates the table, default privileges can temporarily include UPDATE until the grant script is re-applied.

---

## J. Migration 0019

Revision `20260814_0019`, parent `20260814_0018`. Exactly one head. No `0020`.

Contents only: `clinical_note_write_idempotency` (unique scope, deferred note FK, insert-only trigger) and attribution immutability strengthening (`organization_id`, `facility_id`, `author_id`, `note_type` plus existing patient/encounter). No new version column. No GRANT. No unrelated schema.

Roundtrip `0018 → 0019 → 0018 → 0019` verified. **Downgrade drops `clinical_note_write_idempotency`.** That is a schema-downgrade test behavior. It is **not** an operational production rollback plan once idempotency rows exist. Production rollback may need a forward-fix / data-preservation strategy.

Attribution trigger continues to block patient, encounter, org, facility, author, note_type changes. Draft body/version remain service-updatable. FINAL body remains immutable on the application path.

---

## K. Version, races, finalize

Create `version == 1`. Successful draft update `+1` exactly once. Finalize does not increment.

Stale `expected_version`: 409 `note_version_conflict`; no body/version/success audit.

Update vs finalize `FOR UPDATE`: update-first → finalize signs resulting DRAFT; finalize-first → later update 409 `note_not_draft`. No lost update.

Same-key double finalize: 200 replay, one FINAL transition, one FINAL audit. Different key after FINAL: 409 `note_not_draft`.

**Cross-author finalize:** an actor with `clinical.note.finalize` may finalize another author's draft. Author id unchanged. **KNOWN P2 PRODUCT-POLICY DEBT.** Not a newly introduced privilege escalation. Not redesigned at freeze.

---

## L. GET note endpoint

Existing `GET /api/v1/clinical/notes/{note_id}` remains `clinical.note.read` + org isolation + purpose handling. Returning body is the command’s job.

**EXISTING BACKEND CAPABILITY. FRONTEND BODY VIEW = DEFERRED.** Not P2 merely because the MVP form does not call it. Form: **zero** GET-by-id. Reload does not restore draft body from browser storage.

---

## M. Body, XSS, privacy

Plain text. Max 20000. Empty/whitespace rejected. Unicode preserved. No rich text. No HTML interpretation.

Hostile markup stored as text; React escaping; no `dangerouslySetInnerHTML` / `innerHTML` / HTML preview.

422 responses omit Pydantic `input` / raw `body_text`. Logs redact `body_text` and `Idempotency-Key` (nested maps included).

Success audits: `CLINICAL_NOTE_CREATED`, `CLINICAL_NOTE_UPDATED`, `CLINICAL_NOTE_FINALIZED`. No body. Replay: zero extra success audit.

Create provenance exactly once. Replay: zero duplicate. Update/finalize follow frozen existing provenance behavior. No body in provenance metadata.

**DENIED audit rollback:** inherited **P2**. Not fixed at freeze.

---

## N. Frontend form

Existing Clinical Chart Notes section. Reuses `PatientSelectionContext`, PatientSafetyBanner, org/facility context. No second patient-context system.

No draft reopen. No entered-in-error UI or new client wrapper. No autosave / debounce save. Explicit Save Draft only.

Unsaved PHI: React memory only. No localStorage, sessionStorage, IndexedDB, Cache API, Service Worker, URL, cookies, or persistent query cache.

Create: one stable Idempotency-Key per logical create; explicit retry reuses it; confirmed success retires it; later edits use update. Finalize: same. Mutations `retry: false`, `gcTime: 0`.

Network: lost success response + explicit retry same key → 200 replay. UI must not treat a failed wait as proven server rollback.

Abort: browser abort does **not** mean the transaction rolled back. Server: transaction + idempotency + locks. UI: generation/context guard (`note.abortNotRollback`).

Late Patient A create/update/finalize after approved discard/switch to B: does not update B form, show A success under B, or set A note/version under B. Success invalidates **captured A** notes + timeline only, never current B keys.

MutationCache wiped on success, error, discard, patient/org/facility switch, 401, logout.

Dirty patient / close / org / facility / in-app navigation: Stay or Discard and continue; wipe before the new context is active.

Browser Back: `beforeunload` plus same-URL history sentinel + `popstate` (Stay re-pushes; Discard then `history.back()`). Extra history entry while dirty is **P3**, not a safety bypass.

Voluntary logout: Stay or Discard and Logout; wipe then logout. 401: **no confirmation**; immediate security wipe; unsaved body lost.

Facility/permission revocation: backend 403; no saved illusion; no auto retry.

Finalize confirmation: explicit; patient display name, encounter, org, facility, DRAFT; no NIK/BPJS. After FINAL: read-only; no Save Draft; no second finalize action.

Cache invalidation: **notes section + timeline only**. No summary/conditions/allergies/medications/labs/all-chart fan-out.

Read-only Clinical Chart initial open remains 1 shell + 1 summary. No accidental note write or note-body GET.

---

## O. Quality gates

| Check | Result |
|---|---|
| Frontend tests | **184 passed** |
| lint (`oxlint --deny-warnings`) | 0 errors / 0 warnings |
| typecheck | pass |
| production build | pass |
| `npm audit --omit=dev` | 0 vulnerabilities |
| OpenAPI source `--check` | pass (venv Python, not Docker) |
| ruff check / format | pass |
| mypy `app` | pass |
| pytest | **467 passed** |
| Alembic | `current == heads == 20260814_0019`; one head; no 0020 |
| `/api/v1/health/live` | 200 |
| `/api/v1/health/ready` | 200; postgres / redis / object_storage ok |
| Health runtime | **stale Docker** `backend-backend-1` created 2026-08-14. Does **not** prove 0019 or this source are in the image |
| Secret / PHI | synthetic fixtures only; no credentials |

`npm ci` was not re-run this pass (`package-lock.json` unchanged; existing Node 20.20.2 install used for lint/test/build).

---

## P. Findings

**P0:** none.

**P1 unresolved:** none.

**P2:**

- Inherited DENIED-audit rollback.
- Cross-author finalize product-policy debt (`clinical.note.finalize` is not author-scoped).

Purpose: valid catalog purposes with independently held mutation permission are frozen architecture, not P2.

GET note-by-id: existing protected backend capability; not P2.

**P3:**

- Docker image/source lag; 0019 absent from the running image.
- Content-Length-only 1 MiB request limiter.
- No note status index.
- Source OpenAPI tooling needs backend venv Python.
- Dirty-form extra history sentinel entry.
- `app_dml` grants deployed outside Alembic (inherited operational convention).

**Operational note (not classified as P3 by itself):** Alembic downgrade of 0019 drops `clinical_note_write_idempotency` and is not a production rollback plan.

---

## Q. Docker

Do not rebuild in this pass. Running backend image created 2026-08-14. Clinical Note write source and migration 0019 are **ahead** of that image. **P3 deployment lag.**

---

## R. Exact files included

Design / gates:

- `docs/architecture/clinical-note-write-workflow-design.md`
- `docs/architecture/clinical-note-write-workflow-implementation.md`
- `docs/gates/clinical-note-write-workflow-design-approval.md`
- `docs/gates/clinical-note-write-workflow-implementation-gate.md`
- `docs/gates/clinical-note-write-workflow-hardening-gate.md`
- `docs/gates/clinical-note-write-workflow-final-freeze.md`
- `docs/development/migrations.md`

Backend production:

- `backend/alembic/env.py`
- `backend/alembic/versions/20260814_0019_clinical_note_write_idempotency.py`
- `backend/app/api/v1/clinical.py`
- `backend/app/api/v1/deps.py`
- `backend/app/api/v1/schemas.py`
- `backend/app/core/logging.py`
- `backend/app/modules/clinical/application/services.py`
- `backend/app/modules/clinical/domain/enums.py`
- `backend/app/modules/clinical/domain/idempotency.py`
- `backend/app/modules/clinical/infrastructure/models.py`
- `backend/app/modules/clinical/infrastructure/repositories.py`
- `backend/scripts/grant_dev_privileges.sql`

Backend tests:

- `backend/tests/integration/clinical_notes.py`
- `backend/tests/integration/test_clinical_note_write.py`
- `backend/tests/integration/test_clinical_note_write_hardening.py`
- `backend/tests/unit/test_clinical_note_write_idempotency.py`
- `backend/tests/integration/test_clinical_read_core.py` (DTO/`Idempotency-Key` helpers only)
- `backend/tests/integration/test_clinical_read_core_hardening.py` (same)
- `backend/tests/integration/test_product_access_tenancy_foundation_hardening.py` (same)
- `backend/tests/integration/test_wave2a_clinical.py` (same)
- `backend/tests/integration/test_wave2a_hardening.py` (same)

Frontend:

- `apps/healthcare-web/src/chart/notes/ClinicalNoteForm.tsx`
- `apps/healthcare-web/src/chart/notes/clinical-note-write.test.tsx`
- `apps/healthcare-web/src/components/UnsavedWorkDialog.tsx`
- `apps/healthcare-web/openapi/iam-shell.json`
- `apps/healthcare-web/scripts/export_iam_openapi.py`
- `apps/healthcare-web/src/api/generated/iam-shell.ts`
- `apps/healthcare-web/src/App.tsx`
- `apps/healthcare-web/src/api/client.ts`
- `apps/healthcare-web/src/api/clinical.ts`
- `apps/healthcare-web/src/api/errors.ts`
- `apps/healthcare-web/src/api/queryClient.ts`
- `apps/healthcare-web/src/auth/sessionLifecycle.ts`
- `apps/healthcare-web/src/chart/ClinicalChartPage.tsx`
- `apps/healthcare-web/src/chart/ClinicalSectionView.tsx`
- `apps/healthcare-web/src/chart/clinical-chart.test.tsx`
- `apps/healthcare-web/src/chart/wipe.ts`
- `apps/healthcare-web/src/components/FacilitySwitcher.tsx`
- `apps/healthcare-web/src/components/UserMenu.tsx`
- `apps/healthcare-web/src/i18n/locales/en.json`
- `apps/healthcare-web/src/i18n/locales/id.json`
- `apps/healthcare-web/src/patient/PatientLookupPanel.tsx`
- `apps/healthcare-web/src/patient/PatientSelectionProvider.tsx`
- `apps/healthcare-web/src/security/security.test.ts`
- `apps/healthcare-web/src/styles/shell.css`
- `apps/healthcare-web/src/tenant/TenantContext.ts`
- `apps/healthcare-web/src/tenant/TenantProvider.tsx`
- `apps/healthcare-web/src/tenant/unsavedWork.ts`
- `apps/healthcare-web/src/test/TestAppHarness.tsx`
- `apps/healthcare-web/src/test/setup.ts`

No Condition/Medication/Allergy/Observation/lab/Procedure write production code. No `0020`. No ProductAccessPDP / Wave1PolicyPDP / MPI production edits.

---

## S. Post-push verification (fill after push)

| Item | Expected |
|---|---|
| `HEAD == origin/main` | yes |
| Working tree | clean |
| `clinical-note-write-frozen` | points to HEAD |
| Old tags | unchanged |
| Alembic | `20260814_0019` only |

---

## T. Out of scope (unchanged)

Condition/Medication/Allergy/Observation/lab/Procedure writes, draft reopen, Chart note-body view, entered-in-error UI, amendment/addendum, Patient Mobile, Platform Admin, scheduling, notifications, subscription, AI.
