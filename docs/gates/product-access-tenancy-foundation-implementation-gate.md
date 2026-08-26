# Product access and tenancy foundation — implementation gate

**Status:** IMPLEMENTED  
**Hardening:** NOT STARTED  
**Frozen:** NO  
**Date:** 2026-08-26  
**Baseline:** `wave-2b-clinical-foundation-complete` / `b1606fe38dfaf4ee24d95775c07e77cb842c3736`  
**Alembic before:** `current == heads == 20260814_0017`  
**Alembic after:** `current == heads == 20260814_0018`  
**Wave1PolicyPDP:** FROZEN (untouched)

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. This foundation is **not frozen**. Hardening has **not** started. No commit, tag, or push.

Authoritative design: `docs/architecture/product-access-tenancy-foundation-design.md`.  
Implementation record: `docs/architecture/product-access-tenancy-foundation.md`.

---

## In scope

Organization-as-MVP-tenant enforcement, `PLATFORM_ADMIN` least-privilege transition (Option C), authorization dispatcher around frozen `Wave1PolicyPDP`, `PatientPrincipal`, `patient_accounts` 1:1 MPI UUID binding, Patient Self-Access PDP, token audience separation, catalog/migration `0018`, tests, implementation documentation.

## Out of scope

Healthcare Web, Patient Mobile UI, Platform Admin UI, patient medical-record read model, subscription/plan/entitlement/billing, AI Gateway, scheduling, notifications, pharmacy, emergency, hospital groups, patient multi-org PDP, break-glass, support impersonation, full identity-proofing, FHIR, `/api/v2`, Wave 2B.9, freeze, hardening gate.

---

## Baseline verification

| Item | Result |
|---|---|
| HEAD | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Tag | `wave-2b-clinical-foundation-complete` |
| Branch | `main` == `origin/main` |
| Migrations `0001`–`0017` | Untouched |
| `docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched |
| Wave 2B.9 | Does not exist |

---

## Migration `0018`

Forward-only after `0017`. One head.

Created: `patient_accounts` (UUID PK, unique `subject`, FK `patient_identity_id` → `patient_identities.id` `ON DELETE RESTRICT`, status ACTIVE/DISABLED, partial unique ACTIVE identity).

Catalog: insert `patient.account.read`, `patient.record.read`. Strip `PLATFORM_ADMIN` grants except retained platform/org bootstrap permissions.

Live inspect: no NIK/BPJS columns; leftover `clinical.*`/`mpi.*` on `PLATFORM_ADMIN` = 0; `app_dml` INSERT/SELECT/UPDATE only.

`0001`–`0017` not rewritten.

---

## PLATFORM_ADMIN test expectation changes

Intentional authorization change. Clinical lifecycle/immutability/concurrency/provenance/MPI assertions were **not** weakened. Only superseded PLATFORM_ADMIN success expectations were updated.

OLD: `PLATFORM_ADMIN` clinical access allowed (200/201).  
NEW: `PLATFORM_ADMIN` clinical/MPI access denied by default (403).

| File | Old | New |
|---|---|---|
| `test_wave2b8_family_history.py` | platform create 201, read 200; trigger used platform-created row | create/read **403**; clinician-created trigger row for status-transition SQL |
| `test_wave2b8_hardening.py` | platform create/amend/EIE 200 | all **403** on clinician `history_id` |
| `test_wave2b7_adverse_event.py` | platform create 201, read 200 | **403** |
| `test_wave2b7_hardening.py` | platform create/amend/EIE 200 | **403** |
| `test_wave2b6_medical_device.py` | platform read 200 | **403** |
| `test_wave2b6_hardening.py` | platform reported create/amend/EIE 201/200 | **403**; clinician create kept for anonymous/encounter cases |
| `test_wave2b5_procedure.py` | platform read 200 | **403** |
| `test_wave2b5_hardening.py` | platform reported create/amend/EIE 201/200 | **403**; clinician create kept for anonymous/encounter cases |
| `test_wave2b4_immunization.py` | platform read 200 | **403** |
| `test_wave2b4_hardening.py` | platform create 201 | **403** |
| `test_wave2b3b_allergy.py` | platform read 200 | **403** |
| `test_wave2b3c_consent.py` | platform read 200 | **403** |
| `test_wave1_organization.py` | platform org **and** facility/identifier 201 | org create still 201; facility/identifier **403**; `ORG_ADMIN` facility create still 201 |

Frozen `test_wave1_domain.py` direct `Wave1PolicyPDP` tests unchanged. CLINICIAN/ORG_ADMIN/REGISTRAR/IDENTITY_OFFICER clinical semantics unchanged except as above.

---

## New tests

Unit: `backend/tests/unit/test_product_access_tenancy.py` — dispatcher, Patient PDP, platform PHI deny, catalog, audience helpers, frozen PDP still allows `platform_scope` when called directly.

Integration: `backend/tests/integration/test_product_access_tenancy_foundation.py` — catalog/schema, bind ACTIVE, duplicate account/identity, ANONYMOUS/RETIRED/unknown, MERGED resolve + cluster, wrong org 404, Patient A↛B 404, UUID guess 404, PLATFORM_ADMIN clinical/MPI 403, token audiences, operator cannot assign CLINICIAN, staff cross-tenant 404, claim spoof ignored.

No dedicated hardening-gate file.

---

## Quality

| Check | Result |
|---|---|
| `ruff check app tests` | Pass |
| `ruff format --check app tests` | Pass |
| `mypy app` | Pass |
| `pytest` | **278 passed** |
| Alembic | `current == heads == 20260814_0018` (exactly one head) |
| Health live | 200 |
| Health ready | 200; postgres=ok, redis=ok, object_storage=ok |
| Secret scan | Clean |

---

## P0 / P1 / P2 / P3

- **P0:** none  
- **P1:** none  
- **P2 (inherited):** DENIED audit rollback; historical `patient_identity_id` non-rewrite (patient path uses cluster expansion); same-org UUID read for staff  
- **P3 (inherited):** grants outside Alembic; nullable clinical `provenance_id`; intentionally allowed duplicate facts; Docker image lag (`:9100` `/api/v1/patient/me` → 404; image not rebuilt)

---

## Docker

Ports unchanged. Compose untouched. Image **not** rebuilt. Classify missing patient routes on `:9100` as existing **P3 image lag**.

---

## Contract deviations

None that require redesign. Notes: identity-proofing deferred; PHI wrapper denies whenever `iam.platform` is present; no `/api/v1/platform` routes; record-access is not a chart.

---

## Publication

NO COMMIT  
NO TAG  
NO PUSH  
NO FREEZE  

HEALTHCARE WEB = NOT STARTED  
PATIENT MOBILE = NOT STARTED  
PLATFORM ADMIN WEB = NOT STARTED  
SUBSCRIPTION = NOT STARTED  
AI = NOT STARTED  
