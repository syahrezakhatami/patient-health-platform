# Product access and tenancy foundation — design approval

**Date:** 2026-08-26  
**Kind:** Design approval only  
**Verdict:** PRODUCT ACCESS & TENANCY FOUNDATION = APPROVED FOR DESIGN ONLY  
**IMPLEMENTATION:** NOT STARTED

This gate is not implementation authorization for Healthcare Web, Patient Mobile, Platform Admin Web, subscription, or AI. It is not a HIPAA certification. `Wave1PolicyPDP` remains frozen.

Design: `docs/architecture/product-access-tenancy-foundation-design.md`.  
Discovery: `docs/architecture/product-platform-discovery.md`.  
Companion canvas: [product-access-tenancy-foundation.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/product-access-tenancy-foundation.canvas.tsx)

## 1. Baseline

| Item | Value |
|---|---|
| HEAD | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Tag | `wave-2b-clinical-foundation-complete` |
| Parent | `9a56c0893f8638c1a66d854ca61f137a6177ebf4` |
| Branch | `main` == `origin/main` |
| Alembic | `current == heads == 20260814_0017` |
| Migration `0018` | Does not exist |
| Wave 2B | CLOSED |
| Wave 2B.9 | Does not exist |
| `Wave1PolicyPDP` | Untouched |
| Unexpected production changes | **None.** Working tree at inspection: untracked discovery docs only. This pass adds design docs only. |

## 2. Tenant decision

**Organization == MVP tenant.** Canonical boundary: `organization_id` (`organizations.id`). No `tenants` table. `HOSPITAL` / `CLINIC` are types. Hierarchy / `NETWORK` graph: DEFERRED. No implicit inheritance. Hospital A ≠ Hospital B.

## 3. Platform operator decision

**Option C.** Keep `PLATFORM_ADMIN`. Strip `clinical.*` and `mpi.*` via forward `role_permissions` change. Authorize **wrapper** denies those prefixes for org-less `iam.platform` actors. Do not edit `wave1_pdp.py`. Do not add `PLATFORM_OPERATOR`. Operator may bootstrap `ORG_ADMIN` / `PLATFORM_ADMIN` only — not CLINICIAN.

Platform ownership ≠ clinical access.

Break-glass: DEFERRED.

## 4. Patient principal decision

New `PatientPrincipal`. `PrincipalType.PATIENT` is authoritative. **Not** an IAM user. Not CLINICIAN / ORG_ADMIN / PLATFORM_ADMIN / REGISTRAR.

## 5. MPI binding decision

`patient_accounts.subject` (IdP sub) ↔ one `patient_identities.id`. UUID FK. Never NIK/BPJS. 1:1. Staff cannot arbitrarily attach. ANONYMOUS not eligible.

## 6. Self-access decision

Canonical(binding) must equal requested identity. `X-Organization-Id` required; resource org must match. UUID guess → 404. Purpose `PATIENT_ACCESS` required as context, not a grant. Permissions: `patient.account.read`, `patient.record.read` — not `clinical.*`.

## 7. Patient multi-org decision

**Not approved.** SEPARATE FUTURE PDP DESIGN. Must not lift staff same-org UUID P2 to fake aggregation.

## 8. Staff isolation decision

Existing membership + PDP org check. No new bypass. Role groups permissions; permission is the check.

## 9. Facility decision

Exactly one organization per facility. Multi-membership allowed. Empty `actor_facility_ids` = all facilities in that org. Clinical `facility_id` optional as frozen.

## 10. Permission strategy

Staff: existing `clinical.*` / `mpi.*` / `iam.*` / `org.*`.  
Operator: platform subset only.  
Patient: `patient.*` only.  
Entitlement: later, separate from PDP.

## 11. Wave1PolicyPDP extension

Around it: `authorize()` dispatch by principal type + platform clinical deny wrapper + `PatientSelfAccessPDP`. Frozen evaluator unchanged.

## 12. DB preview

`patient_accounts` (new). Strip PLATFORM_ADMIN clinical/MPI grants. Insert `patient.*` permissions. No frozen clinical columns. No subscription tables.

## 13. Migration preview

Forward-only after `0017`. Do not rewrite `0001`–`0017`. Implementation-wave tests: PLATFORM_ADMIN clinical 201 → 403; CLINICIAN tests unchanged.

## 14. API preview

Existing `/api/v1/clinical|iam|organizations|mpi` = staff. Future `/api/v1/platform`, `/api/v1/patient`. No `/api/v2`. Distinct token audiences.

## 15. Security matrix

See design § isolation matrix. Operator × patient clinical = DENY. Patient A × Patient B = DENY. Cross-org clinical = DENY. Billing/AI cost = NOT YET DESIGNED then non-PHI only.

## 16. Threat model

Tenant header, UUID guessing, staff cross-org, operator PHI, wrong bind, merge lockout/collision, facility bypass, operator self-grant CLINICIAN, forged principal type, token reuse, impersonation. Mitigations in the design. Impersonation not implemented.

## 17. Backward compatibility

Production: no SaaS customers yet; local PLATFORM_ADMIN is a bootstrap actor.  
Tests: Wave 1 org-create stays. Clinical files that `assert platform_created.status_code in {200, 201}` (family history, allergy, consent, immunization, procedure, device, AE, several hardening files) **must change in the implementation pass**. Frozen Wave1PolicyPDP unit tests stay. Clinical `has_platform_scope` visibility remains in frozen services but is unreachable if clinical actions are unauthorized.

## 18. P0 / P1 / P2 / P3

| Sev | Impact |
|---|---|
| P0 / P1 | None |
| P2 denial audit | Still weakens deny evidence; not a design blocker |
| P2 identity non-rewrite | Patient reads use canonical + cluster expansion |
| P2 same-org UUID | Retained for staff; not a patient multi-org grant |
| P3 | Unchanged; new tables will follow grant-script convention |

None block approving this design.

## 19. Exact future implementation scope

When separately approved: patient account persistence, operator grant strip, authorize dispatcher, Patient PDP, audience separation, tests, docs.  
Not in that first implementation unless re-approved: frontends, full read-model API, subscription, AI, scheduling, proofing UX, break-glass, hospital groups.

## 20. Deferred / forbidden

Deferred: subscription, entitlement, AI, appointments, notifications, pharmacy, emergency, Healthcare Web, Platform Admin Web, Patient Mobile UI, cross-org patient record, break-glass, hospital groups, identity proofing product, staff+patient same person.  
Forbidden: Wave1PolicyPDP rewrite, Tenant table, duplicate clinical stores, `clinical.*` on patients, `/api/v2`, Wave 2B.9.

## Production status

IMPLEMENTATION = NOT STARTED  
MIGRATION 0018 = NOT CREATED  
HEALTHCARE WEB = NOT STARTED  
PATIENT MOBILE = NOT STARTED  
PLATFORM ADMIN WEB = NOT STARTED  
SUBSCRIPTION = NOT STARTED  
AI = NOT STARTED  

NO PRODUCTION CODE  
NO TEST CHANGES  
NO COMMIT  
NO TAG  
NO PUSH
