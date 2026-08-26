# Product access and tenancy foundation — final freeze

**Date:** 2026-08-26  
**Verdict:** PASS WITH P2  
**P0:** none  
**P1 unresolved:** none  
**PRODUCT ACCESS & TENANCY FOUNDATION:** FROZEN  
**PRODUCT ACCESS & TENANCY FOUNDATION:** PUBLISHED  

This freeze is not a HIPAA, ISO 27001, or SOC 2 certification. It does not start Healthcare Web, Patient Mobile, Platform Admin Web, Patient Medical Record read model, subscription, entitlement, billing, AI, scheduling, notifications, pharmacy, emergency, ambulance, break-glass, patient multi-org, or hospital hierarchy.

Authoritative contracts (not reinterpreted):

- `docs/architecture/product-platform-discovery.md`
- `docs/gates/product-platform-architecture-discovery.md`
- `docs/architecture/product-access-tenancy-foundation-design.md`
- `docs/gates/product-access-tenancy-foundation-design-approval.md`
- `docs/architecture/product-access-tenancy-foundation.md`
- `docs/gates/product-access-tenancy-foundation-implementation-gate.md`
- `docs/gates/product-access-tenancy-foundation-hardening-gate.md`

---

## A. Repository and lineage

| Item | Value |
|---|---|
| Branch | `main` == `origin/main` (at freeze) |
| Published parent SHA | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Parent tag | annotated `wave-2b-clinical-foundation-complete` → same SHA |
| Family History freeze (unchanged) | `wave-2b8-family-history-frozen` → `9a56c0893f8638c1a66d854ca61f137a6177ebf4` |
| Final freeze SHA | this publication commit (`git rev-parse product-access-tenancy-foundation-frozen^{}`) |
| Final annotated tag | `product-access-tenancy-foundation-frozen` → this publication commit |
| Parent of freeze | `wave-2b-clinical-foundation-complete` |
| Alembic | `current == heads == 20260814_0018` (exactly one head; no `0019`) |
| `docker-compose.yml` | Untouched |
| `wave1_pdp.py` | Untouched vs parent; SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd` |

Old tags were not moved or rewritten.

---

## B. Scope

Product Access & Tenancy Foundation only:

- migration `20260814_0018` (`patient_accounts`, patient permissions, `PLATFORM_ADMIN` PHI strip, rebinding trigger)
- PatientPrincipal / patient self-access PDP / patient account APIs
- ProductAccessPDP dispatcher around frozen Wave1
- token audience isolation (`php-api`, `php-platform`, `php-patient`)
- tenant = Organization; facility ∈ organization validation
- hardening P1 fixes (SQL rebind, mixed `aud`, merge-collision commit, foreign-facility attribution)
- implementation / hardening / isolation tests
- discovery, design, implementation, hardening, and this freeze documentation

No frontend, subscription, billing, entitlement, AI, scheduling, notification, pharmacy, emergency, or ambulance work is included.

---

## C. Tenant contract

Organization == MVP tenant. Canonical boundary is `organization_id`. No `tenants` table. `HOSPITAL` / `CLINIC` remain organization types. Hospital groups deferred. Hospital A ≠ Hospital B. Clinic A ≠ Clinic B. No implicit cross-tenant inheritance.

---

## D. Facility contract

Each facility belongs to exactly one organization. When `facility_id` is present, `facility.organization_id` must equal the effective request/resource `organization_id`.

Empty `actor_facility_ids` means all authorized facilities **inside the actor organization**, never globally.

Verified:

- same-org facility → allow when otherwise authorized
- foreign-org facility → deny/conceal (404)
- explicit listed facility → allow
- same-org unlisted facility → deny (403 Wave1 allow-list)
- null facility remains valid where frozen clinical facts permit it

---

## E. Central facility validation

`facility_tenant_decision` runs from `authorize()` **after** PDP allow when `facility_id` is present. Unknown/mismatched facilities are not persisted on the API path. Wave1PolicyPDP was not modified. Validation is not copy-pasted into each clinical method.

All 75 public ClinicalService operations, all MpiService `authorize()` sites, IAM, organization, and patient-access authorize sites pass `session=` into the shared helper.

Direct untrusted client SQL is not a product architecture path. No public API bypass of the invariant was found.

---

## F. Database facility limitation (P3)

Frozen clinical tables keep independent `organization_id` and `facility_id` FKs. The database alone does not universally enforce the pair. Production mutation uses centralized `authorize()` validation. No migration `0019`. Frozen clinical schemas were not rewritten.

---

## G. PLATFORM_ADMIN

`PLATFORM_ADMIN` remains. `PLATFORM_OPERATOR` was not introduced. Live `role_permissions`: `clinical.*` = 0, `mpi.*` = 0. Retained: `iam.platform`, `iam.user.read`, `iam.user.provision`, `iam.membership.manage`, `org.organization.create`, `org.organization.read`.

ProductAccessPDP denies `clinical.*` / `mpi.*` when `iam.platform` is in scopes even if stale grants are injected. Platform ownership does not imply clinical access. Facility headers cannot restore PHI.

Bootstrap membership assign: `CLINICIAN` / `IDENTITY_OFFICER` / `REGISTRAR` / `AUDITOR` denied. Approved bootstrap: `PLATFORM_ADMIN`, `ORG_ADMIN`. No break-glass. No impersonation.

Platform `ORG_FACILITY_CREATE` / identifier manage on a tenant org is 403 (least privilege vs earlier Wave1 tests). ORG_ADMIN still creates facilities.

---

## H. ProductAccessPDP

| Principal | Dispatcher |
|---|---|
| PATIENT | Patient Self-Access PDP |
| STAFF / PRACTITIONER / AUDITOR | frozen Wave1PolicyPDP, after platform-PHI gate |
| PLATFORM (`iam.platform` + `clinical.*`/`mpi.*`) | deny `platform_clinical_forbidden` |
| UNKNOWN / MALFORMED / SYSTEM | deny `principal_type_denied` |

No unknown-principal fallthrough. Production protected operations go through `authorize()` → `app.state.pdp` (`default_pdp()` = ProductAccessPDP). `/api/v1/auth/context` is introspection-only.

---

## I. Wave1PolicyPDP

Unchanged vs `b1606fe38dfaf4ee24d95775c07e77cb842c3736`. SHA-256 `f4c98eb9393d005abc87e786c6150c21d3120641f28371bebac026e9591895dd`. Instantiated only from ProductAccessPDP.

---

## J. PatientPrincipal and `patient_accounts`

PatientPrincipal is distinct from IAM staff Principal. `PrincipalType.PATIENT` is authoritative. Patient is not CLINICIAN / ORG_ADMIN / REGISTRAR / PLATFORM_ADMIN.

Resolution: validated token `sub` → `patient_accounts` → `patient_identity_id` → canonical MPI identity. Request/token `patient_identity_id` is not the binding.

Live schema after 0018:

- UUID PK
- unique `subject`
- `patient_identity_id` FK `ON DELETE RESTRICT`
- status CHECK `ACTIVE` / `DISABLED`
- unique active identity index `uq_patient_accounts_active_identity`
- indexes on PK, subject, identity
- no NIK, no BPJS, no demographics, no clinical payload

`app_dml`: INSERT, SELECT, UPDATE. DELETE denied. TRUNCATE denied.

---

## K. Binding immutability (H1 FIXED)

Trigger `trg_patient_accounts_binding_immutable` / function `prevent_patient_account_rebinding`:

- `subject` immutable
- generic `patient_identity_id` reassignment blocked
- identity may rebind only along approved MPI merge survivor hops
- `DISABLED → ACTIVE` forbidden
- DELETE raises

---

## L. Account controller invariant

One ACTIVE authenticated controller per canonical patient identity.

Two subjects → same active identity: reject. Same subject → two identities: reject. Collision (`Account A→X`, `Account B→Y`, merge `X→Y`): both DISABLED and committed before 403; no A→B takeover. Historical DISABLED rows cannot reactivate.

---

## M. Patient permissions and PATIENT_ACCESS

Catalog: `patient.account.read`, `patient.record.read` only. No `clinical.*`, `mpi.*`, `iam.platform`, or org-admin permissions. No wildcard/prefix grant.

`PATIENT_ACCESS` is required validated purpose/context, not a grant. Wrong patient / wrong tenant → 404 conceal. Wrong purpose → 403. Missing/unknown purpose → 422.

Patient A → A: allow when fully authorized. Patient A → B / random UUID / other org: 404. Patient multi-org medical-record access is not approved.

---

## N. Audiences (H2 FIXED)

`php-api`, `php-platform`, `php-patient`. Validator requires exactly one distinct non-empty audience. Mixed arrays such as `["php-api","php-patient"]` are rejected.

Patient token → staff/platform API: 401. Staff token → patient API: 401. Platform token → patient API: 401. Platform token → clinical API: 401 (audience) or 403 (PDP) per route class.

Fake `principal_type` / `patient_identity_id` claims do not override trusted resolution.

---

## O. MPI ACTIVE / ANONYMOUS / RETIRED / merge / collision

ACTIVE: eligible to bind when otherwise valid. ANONYMOUS: not eligible for patient account. RETIRED: not a standalone self-service identity. Frozen MPI lifecycle was not redesigned.

Merge `Account → X`, `X MERGED → Y`: survivor access retained; historical clinical `patient_identity_id` rows are **not rewritten** (inherited P2); cluster-aware `record-access` includes merged-in members; no duplicate facts; no cross-org expansion; no Patient A → Patient B leakage.

Collision H3 FIXED: disable is committed before the subsequent 403 so rollback cannot restore dual ACTIVE controllers.

Concurrency uses PostgreSQL `SELECT FOR UPDATE`, not Redis.

---

## P. Isolation recap

| Case | Result |
|---|---|
| Hospital A staff → Hospital B | deny/404 |
| Hospital A staff + facility B | 404 conceal |
| Clinic B → Hospital A | deny/404 |
| Patient org-header manipulation | no cross-org PHI |
| Platform + org/facility headers | not a clinician |

---

## Q. Provenance and audit

Authentication, account lookup, patient self-read, authorization decisions, and non-clinical platform actions do not create `clinical_provenances` rows.

Audit does not log tokens, Authorization headers, NIK, BPJS, or credentials.

Inherited **P2**: DENIED-audit rollback (platform/clinical 403 may still insert 0 `DENIED` `audit_events` rows when the request transaction rolls back). Not redesigned.

---

## R. Migration 0018

`0017 → 0018` is the additive Product Access revision (`down_revision = 20260814_0017`). Live freeze verification: `current == heads == 20260814_0018`, one head, trigger present, patient catalog present, `PLATFORM_ADMIN` PHI grants = 0. Reverse cycle `0018 → 0017 → 0018` was executed during the hardening pass; this freeze did not re-downgrade the populated local database. `scripts/grant_dev_privileges.sql` remains outside Alembic (inherited P3). No `0019`.

---

## S. Frozen clinical regression

Full suite through Family History passed. Intentional authorization difference only: `PLATFORM_ADMIN` clinical/MPI → **403**. Lifecycle, audit, provenance, immutability, concurrency, coded semantics, and MPI semantics otherwise intact.

---

## T. Quality gates (fresh)

| Check | Result |
|---|---|
| `ruff check app tests` | Pass (0 issues) |
| `ruff format --check app tests` | Pass (174 files) |
| `mypy app` | Pass (118 source files) |
| `pytest` | **326 passed** |
| Alembic | `current == heads == 20260814_0018` |
| `/api/v1/health/live` | 200 `{"status":"alive"}` |
| `/api/v1/health/ready` | 200; postgres=ok, redis=ok, object_storage=ok |
| Secret scan | Clean (no private keys, `AKIA…`, `.env`, or credential files in the freeze commit) |

---

## U. Docker

Compose untouched. Image **not** rebuilt. `:9100` `GET /api/v1/patient/me` → **404** (image predates Product Access). **P3 DOCKER IMAGE LAG.** Not P0/P1.

---

## V. P0 / P1 / P2 / P3

- **P0:** none
- **P1 unresolved:** none
- **P1 found during hardening and FIXED:** H1 SQL rebind; H2 mixed JWT audience; H3 merge-collision rollback; H5 foreign-facility attribution. Unknown-principal fallthrough also fixed.
- **P2 inherited (verified):** DENIED audit rollback; historical clinical `patient_identity_id` non-rewrite after MPI merge (patient path compensates via canonical/cluster)
- **P3 inherited (verified):** `app_dml` grants outside Alembic; nullable clinical `provenance_id` convention; Docker image lag; independent org/facility FKs on frozen clinical tables

---

## W. Files in this freeze

Implementation and docs from parent `b1606fe38dfaf4ee24d95775c07e77cb842c3736`:

- `backend/.env.example`
- `backend/alembic/env.py`
- `backend/alembic/versions/20260814_0018_product_access_tenancy.py`
- `backend/app/api/v1/clinical.py`
- `backend/app/api/v1/deps.py`
- `backend/app/api/v1/iam.py`
- `backend/app/api/v1/mpi.py`
- `backend/app/api/v1/organizations.py`
- `backend/app/api/v1/patient.py`
- `backend/app/api/v1/router.py`
- `backend/app/core/config.py`
- `backend/app/core/dependencies.py`
- `backend/app/modules/authorization/application/authorize.py`
- `backend/app/modules/authorization/application/facility_scope.py`
- `backend/app/modules/authorization/application/product_access_pdp.py`
- `backend/app/modules/authorization/domain/catalog.py`
- `backend/app/modules/authorization/domain/models.py`
- `backend/app/modules/clinical/application/services.py`
- `backend/app/modules/iam/application/services.py`
- `backend/app/modules/iam/infrastructure/jwt_oidc_validator.py`
- `backend/app/modules/mpi/application/services.py`
- `backend/app/modules/mpi/infrastructure/repositories.py`
- `backend/app/modules/organization/application/services.py`
- `backend/app/modules/patient_access/` (domain, application, infrastructure)
- `backend/scripts/grant_dev_privileges.sql`
- `backend/tests/integration/test_facility_organization_isolation.py`
- `backend/tests/integration/test_product_access_tenancy_foundation.py`
- `backend/tests/integration/test_product_access_tenancy_foundation_hardening.py`
- `backend/tests/integration/test_wave1_organization.py`
- `backend/tests/integration/test_wave2b3b_allergy.py`
- `backend/tests/integration/test_wave2b3c_consent.py`
- `backend/tests/integration/test_wave2b4_hardening.py`
- `backend/tests/integration/test_wave2b4_immunization.py`
- `backend/tests/integration/test_wave2b5_hardening.py`
- `backend/tests/integration/test_wave2b5_procedure.py`
- `backend/tests/integration/test_wave2b6_hardening.py`
- `backend/tests/integration/test_wave2b6_medical_device.py`
- `backend/tests/integration/test_wave2b7_adverse_event.py`
- `backend/tests/integration/test_wave2b7_hardening.py`
- `backend/tests/integration/test_wave2b8_family_history.py`
- `backend/tests/integration/test_wave2b8_hardening.py`
- `backend/tests/security/test_authentication.py`
- `backend/tests/unit/test_product_access_tenancy.py`
- `docs/architecture/product-access-tenancy-foundation-design.md`
- `docs/architecture/product-access-tenancy-foundation.md`
- `docs/architecture/product-platform-discovery.md`
- `docs/development/migrations.md`
- `docs/gates/product-access-tenancy-foundation-design-approval.md`
- `docs/gates/product-access-tenancy-foundation-final-freeze.md`
- `docs/gates/product-access-tenancy-foundation-hardening-gate.md`
- `docs/gates/product-access-tenancy-foundation-implementation-gate.md`
- `docs/gates/product-platform-architecture-discovery.md`

---

## X. Push verification

Normal push of `main` and annotated tag `product-access-tenancy-foundation-frozen`. No force-push. Parent tags unchanged.

Expected after publish:

```
wave-2b-clinical-foundation-complete
        |
        v
product-access-tenancy-foundation-frozen
```

HEAD == `origin/main`. Working tree clean.

---

## Y. Verdict

PASS WITH P2
