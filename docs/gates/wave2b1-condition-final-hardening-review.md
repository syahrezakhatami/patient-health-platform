# Wave 2B.1 — Condition final hardening review (H4 / H5)

**Date:** 2026-08-14
**Recommendation:** **FREEZE CONDITION**
**Wave 2B.2:** NOT STARTED
**Git commit/tag this pass:** none (not created)

This review is not a HIPAA, ISO 27001, or SOC 2 certification.

## 1. Findings before remediation

Inspected live implementation, Alembic `20260814_0006`, Docker `:9100`, PostgreSQL on `5433`, and existing tests. No code was changed until this inspection completed.

| ID | Sev | Finding | Decision |
|---|---|---|---|
| H4 | P2 | `conditions.provenance_id` had no FK | **Fix.** It is a back-pointer to canonical `clinical_provenances`, not a polymorphic column. Service always inserts provenance first, then stores `provenance.id`. Live: 31/31 rows populated, 0 orphans. Encounter/note `provenance_id` stays Wave 2A (no FK). |
| H5 | P2 | `onset_at` / `recorded_at` / `facility_id` (and `abatement_at`) were SQL-mutable before EIE | **Policy A — immutable after create.** No mutation API exists. `clinical.condition.update` is status-only. Docs and architecture treat these as historical facts. Prefer immutable unless controlled mutation is required; it is not. Public API unchanged. |
| H2 | P2 | `DENIED` audit rows roll back with `ForbiddenError` | Unchanged (Wave 1 session; out of scope) |
| H3 | P2 | Historical `patient_identity_id` not rewritten after MPI merge | Unchanged (explicit design; tested) |

## 2. Files changed

- `backend/alembic/versions/20260814_0007_wave2b1_condition_integrity.py` (new)
- `backend/app/modules/clinical/infrastructure/models.py` — `ForeignKey` on `provenance_id`
- `backend/tests/integration/test_wave2b1_hardening.py` — H4/H5 tests
- `docs/clinical/wave2b1-condition.md` — explicit immutability policy
- `docs/development/migrations.md` — `0007`
- `docs/gates/wave2b1-condition-final-hardening-review.md` — this report

`0001`–`0006` were not rewritten. No `/api/v2`. No Observation/Laboratory/Medication/Allergy/Consent/FHIR/AI.

## 3. Migration status

| Item | Value |
|---|---|
| Previous head | `20260814_0006` |
| New head | `20260814_0007` (single head) |
| `current == heads` | Yes |
| Upgrade | Applied on live `php_dev` |
| Downgrade | Not run (populated DB) |
| Orphan check | Migration aborts if `provenance_id` does not exist in `clinical_provenances` |

## 4. Database constraints

Live `conditions`:

- Existing FKs unchanged: patient, encounter, organization, facility — all `ON DELETE RESTRICT`
- **New:** `fk_conditions_provenance_id` → `clinical_provenances(id)` `ON DELETE RESTRICT`
- CHECKs: category, clinical/verification status, encounter-diagnosis requires encounter, period, non-empty code/system
- Trigger `prevent_condition_history_mutation` now also freezes `facility_id`, `onset_at`, `abatement_at`, `recorded_at`, `provenance_id`
- Still allowed until EIE: `clinical_status`, `verification_status`, `updated_at`
- DELETE still raises `conditions cannot be deleted`
- Provenance DELETE is also blocked by the insert-only trigger on `clinical_provenances` (fires before FK)

`app_dml` on `conditions`: INSERT/SELECT/UPDATE (no DELETE). Invalid `provenance_id` INSERT fails FK for both `php_admin` and `app_dml`.

## 5. Condition lifecycle

Unchanged. Create `ACTIVE`+`CONFIRMED`. Status machine via `POST .../status`. Void via `POST .../entered-in-error`. After EIE the whole row is frozen. No DELETE route.

Onset/abatement, if known, are supplied at create. Later resolution is a **status** change, not a period rewrite. **Public API contract is unchanged** (`CreateConditionRequest` / `ChangeConditionStatusRequest` fields unchanged).

## 6. Identity behavior

Unchanged. Canonical `patient_identity_id`. MERGED → survivor on new writes. RETIRED 409. Unknown/cross-org 404. Anonymous problem list 409; anonymous EMER encounter diagnosis allowed. Historical rows not rewritten.

## 7. Authorization

Unchanged. Auth + org + facility + purpose + `clinical.condition.*`. Registrar + `TREATMENT`/`EMERGENCY` 403. `clinical.diagnosis.create` deny-by-default.

## 8. Audit / provenance

Success audits unchanged (no PII/code display). Provenance remains a separate insert-only table. Condition now **references** that table with RESTRICT. Provenance `subject_type` already includes `CONDITION`.

## 9. Concurrency

Mutating Condition reads still use `SELECT FOR UPDATE`. Redis is not an authoritative lock. Existing tests: concurrent identical status `{200,409}` one audit; concurrent double EIE `{200,409}` one void audit; status vs EIE deterministic. No new mutable fields, so no extra mutation-race API tests. SQL bypass of historical fields is trigger-blocked (including `app_dml`).

## 10. Security tests

Covered in Wave 2B.1 suites: unauthenticated 401, invalid purpose 422, registrar 403, facility allow-list, cross-org 404, random UUID 404, HTTP DELETE 405, `app_dml` cannot DELETE, orphan `provenance_id` rejected, historical SQL UPDATE rejected, status update still 200 after H5 freeze.

Live Docker smoke: unauthenticated POST/GET Condition **401**; DELETE **405**; no SQL in body.

## 11. Docker runtime

Backend rebuilt `--no-deps`. Health live/ready: postgres, redis, object_storage ok. `OBJECT_STORAGE_ENDPOINT=http://minio:9000`. Ports unchanged. `gsai-minio` untouched (up 2 weeks).

## 12. Full test results

| Check | Result |
|---|---|
| ruff check / format --check | PASS |
| mypy | PASS |
| pytest | **118 passed** (Wave 1.5 + Wave 2A + Wave 2B.1) |
| Alembic current / heads | `20260814_0007` |
| Docker health | PASS |
| Clinical boundary scan | Condition only |

## 13. Remaining findings

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| H4 | P2 | Missing Condition provenance FK | **Closed** in `0007` |
| H5 | P2 | Onset/recorded/facility SQL-mutable before EIE | **Closed** in `0007` trigger (Policy A) |
| H2 | P2 | Denial-audit rollback | Remaining (Wave 1; do not redesign) |
| H3 | P2 | No historical identity rewrite after merge | Remaining (by design) |
| H6 | P3 | Dev grants in `grant_dev_privileges.sql` | Remaining (Wave 1/2A pattern) |
| — | P3 | Encounter/note `provenance_id` still has no FK | Remaining (Wave 2A freeze; out of scope) |

P0 = 0. Open P1 = 0. No remaining **Condition-specific** P2.

## 14. Recommendation

**FREEZE CONDITION**

H4 and H5 are closed with an additive `0007` and no public API change. Residual P2 items are the same inherited Wave 1 / MPI non-rewrite class that Wave 2A already froze with. Do not start Wave 2B.2 in this pass. Commit and tag are **not** created here.

WAVE 2B.1 FINAL HARDENING COMPLETE — WAVE 2B.2 NOT STARTED — NO COMMIT — NO TAG
