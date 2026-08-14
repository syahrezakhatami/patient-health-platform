# Wave 2A — Production hardening gate

**Status:** PASS WITH P2  
**Date:** 2026-08-14  
**Wave 2B:** NOT STARTED

This gate is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Executive summary

Wave 2A (Encounter, clinical note, terminology stub, CLINICIAN RBAC) was audited against the live repository, Alembic head `20260814_0005`, and Docker runtime on host port 9100.

Four production defects were fixed in Wave 2A only: lost updates on note/encounter mutation, incomplete FINAL immutability at the database, hard-deletable encounters, and anonymous non-emergency encounters. Remaining items are P2 (denial-audit rollback is Wave 1 session behavior; merge does not rewrite historical encounter rows).

## 2. Baseline

| Item | Live value |
|---|---|
| Git | Repository initialized, **no first commit**, working tree untracked |
| Alembic head | `20260814_0005` (revises `0004`; `0001`–`0003` untouched) |
| Docker | `backend` rebuilt from this tree; postgres/redis/minio already running |
| Ports | API `9100:8000`, Postgres `5433:5432`, Redis `6380:6379`, MinIO `9101:9000` / console `9002:9001` |
| Backend → MinIO | `http://minio:9000` |
| `gsai-minio` | Untouched |
| Schema | `encounters`, `encounter_participants`, `clinical_notes`, `clinical_provenances` only for clinical facts |
| API | `/api/v1/clinical/` (7 paths). No `/api/v2/` |

## 3. Files inspected

Clinical module (`application/services.py`, `domain/lifecycle.py`, `domain/terminology.py`, `infrastructure/models.py`, `infrastructure/repositories.py`), `api/v1/clinical.py`, `authorization` catalog/PDP/`authorize.py`, Alembic `0004`/`0005`, grant script, logging, exception handlers, Wave 2A tests, Docker Compose, live PostgreSQL triggers/FKs.

## 4. Files changed

- `backend/app/modules/clinical/application/services.py`
- `backend/app/modules/clinical/infrastructure/repositories.py`
- `backend/app/modules/clinical/domain/terminology.py`
- `backend/app/core/logging.py`
- `backend/alembic/versions/20260814_0005_wave2a_clinical_hardening.py`
- `backend/scripts/grant_dev_privileges.sql`
- `backend/tests/unit/test_wave2a_clinical_domain.py`
- `backend/tests/integration/test_wave2a_hardening.py`
- `docs/development/migrations.md`
- `docs/clinical/wave2a-clinical-foundation.md`

## 5. Encounter lifecycle verification

Implemented states: `PLANNED`, `IN_PROGRESS`, `FINISHED`, `CANCELLED`, `ENTERED_IN_ERROR`. There is **no** `COMPLETED` state; the API rejects it with 422.

Allowed: `PLANNED → IN_PROGRESS|CANCELLED|ENTERED_IN_ERROR`; `IN_PROGRESS → FINISHED|CANCELLED|ENTERED_IN_ERROR`; `FINISHED|CANCELLED → ENTERED_IN_ERROR`. Terminal: `ENTERED_IN_ERROR`.

Concurrent `FINISHED` vs `CANCELLED` from `IN_PROGRESS`: one 200, one 409, single remaining status. Mutations take `SELECT FOR UPDATE`.

## 6. Patient identity binding verification

`patient_identity_id` is a FK to `patient_identities.id` (`ON DELETE RESTRICT`). No second patient table.

| Lifecycle | Result |
|---|---|
| ACTIVE | Encounter allowed |
| ANONYMOUS | `EMER` allowed; `AMB` 409 |
| MERGED | New encounter binds to surviving identity |
| RETIRED | 409 |
| Unknown | 404 |

Historical rows are not rewritten on merge.

## 7. Organization / facility authorization

PDP is `Wave1PolicyPDP`. Clinical actions are org-scoped. Resource visibility is organization-scoped (cross-org 404). Facility: empty membership binding is org-wide; a bound actor sending an out-of-scope `X-Facility-Id` is 403. Matches Wave 1.5.

## 8. Purpose-of-use verification

`X-Purpose` is required (422 if missing/invalid). `TREATMENT` is catalogued and does not grant `clinical.note.create`. Registrar + `TREATMENT` → 403.

## 9. Clinical note immutability

DRAFT may be edited (version increments). FINAL cannot be edited via API (409). Direct SQL cannot change FINAL body, author, or revert status to DRAFT. DELETE is blocked. `ENTERED_IN_ERROR` is explicit, auditable, and then immutable.

Enforced at API, service (`assert_note_is_draft` / finalize), and database trigger.

## 10. Note concurrency

Concurrent double-finalize: `{200, 409}`, one `FINAL` row, one `CLINICAL_NOTE_FINALIZED` audit. Row lock prevents last-writer-wins resurrection of `ENTERED_IN_ERROR` into `FINAL`.

## 11. Audit

Success events: encounter create/status, note create/update/finalize/entered-in-error. Fields: actor, org, facility when present, purpose, timestamp, action, resource id, result. Metadata is purpose/status/type — not note body.

**P2:** `DENIED` rows are flushed then rolled back with `ForbiddenError` because audit shares the request session. This is Wave 1 session semantics and was not changed.

## 12. Provenance

Separate insert-only `clinical_provenances` (actor, org, facility, timestamp, `authorship_kind=NATIVE`, `information_source=CLINICIAN`, `verification_method=clinical_authorship`). Not collapsed into audit. No `source_system` field — native authorship stub, not a second MPI provenance model.

## 13. Terminology boundary

Stub only: `system` + `code` + optional `display`. No terminology server, SNOMED, ICD, LOINC, or FHIR ValueSet. Invalid/missing system+code → 422. Display max 255.

## 14. CLINICIAN RBAC

Role and `clinical.*` permissions are DB-backed. Unprovisioned 403. Registrar cannot create notes. Unknown action `clinical.diagnosis.create` deny-by-default. No `if role == doctor`.

## 15. IDOR / enumeration

Random encounter/note UUID → 404. Cross-org encounter/note → 404, no SQL/body leak. List requires `patient_identity_id`.

## 16. PII / logging

Validation errors do not echo note body. `body_text` is in the log redaction set. Audit metadata does not store note content.

## 17. Database integrity

FKs `ON DELETE RESTRICT` to `patient_identities`. CHECKs on class/status/note type. Indexes on patient, org, status, authored_at. `0005` adds encounter delete/identity immutability and tightens FINAL/ERROR note rules.

## 18. Delete semantics

No DELETE routes. Notes and encounters cannot be hard-deleted (trigger). Correction is `ENTERED_IN_ERROR`. `app_dml` DELETE revoked on those tables.

## 19. Migration safety

`0001`–`0003` not edited. `0004` additive foundation. `0005` additive hardening. Head `20260814_0005`. Upgrade applied. Downgrade of `0005` restores the weaker `0004` note trigger and drops the encounter history trigger; **do not run downgrade against the populated dev database**.

`0004` previously expanded `identity_match_probes` purpose CHECK to include `TREATMENT`. Hardening did not further modify MPI tables.

## 20. Docker verification

Image rebuilt from the working tree. Health live/ready: postgres, redis, object_storage ok. Unauthenticated clinical POST → 401. Ports unchanged.

## 21. Test results

| Check | Result |
|---|---|
| ruff check / format --check | PASS |
| mypy | PASS |
| pytest | **101 passed** |

## 22. Clinical boundary scan

| Hit | Classification |
|---|---|
| Diagnosis/Observation/Medication/FHIR in docs and tests | Prohibition / deny-by-default test |
| `OrganizationType.LABORATORY` | Org taxonomy, not a lab domain |
| `clinical_governance` | Wave 0 placeholder, no patient facts |
| `fhir` / openai / langchain in `backend/app` | None |

No diagnosis, observation, laboratory result, medication, allergy, consent, FHIR, RAG, or AI implementation.

## 23. Findings by severity

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| H1 | P1 | Encounter/note mutations had no `SELECT FOR UPDATE`; lost updates / double-finalize | **Fixed** |
| H2 | P1 | FINAL trigger allowed status revert and author change via SQL | **Fixed** in `0005` |
| H3 | P1 | Encounters could be hard-deleted | **Fixed** in `0005` + grants |
| H4 | P1 | ANONYMOUS identities could receive non-`EMER` encounters | **Fixed** in service |
| H5 | P2 | `DENIED` audit rows roll back with `ForbiddenError` | Remaining (Wave 1 session) |
| H6 | P2 | Pre-merge encounters on a merged source are not rewritten or listed on the survivor | Remaining (no historical rewrite) |
| H7 | P3 | Clinical provenance has no `source_system` | Remaining (native stub) |

No P0.

## 24. Remediation performed

Row locks on mutating encounter/note reads; anonymous → EMER only; draft version increment; `body_text` log redaction; migration `0005`; `app_dml` DELETE revoked on clinical history tables; hardening tests.

## 25. Remaining risks

Denial audits are not durable until Wave 1 session/audit plumbing is changed under a dedicated exception. Merge does not backfill `patient_identity_id` on old encounters. Neither is Wave 2B.

## 26. Final scorecard

| Area | Result |
|---|---|
| Identity binding | PASS |
| Encounter lifecycle + concurrency | PASS (after H1) |
| Org/facility PDP | PASS |
| Purpose ≠ authorization | PASS |
| Note immutability (API + DB) | PASS (after H2) |
| Delete semantics | PASS (after H3) |
| CLINICIAN RBAC / IDOR | PASS |
| Terminology stub bounded | PASS |
| Clinical boundary | PASS |
| Docker / ports | PASS |
| Quality gates | 101 passed |
| **Verdict** | **PASS WITH P2** |

WAVE 2A HARDENING COMPLETE — WAVE 2B NOT STARTED
