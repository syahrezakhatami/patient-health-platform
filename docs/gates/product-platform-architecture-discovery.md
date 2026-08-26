# Product platform architecture discovery gate

**Date:** 2026-08-26  
**Kind:** Architecture discovery only  
**Verdict:** DISCOVERY COMPLETE — NOT IMPLEMENTATION APPROVAL  
**WAVE 2B CLINICAL FOUNDATION:** CLOSED (unchanged)  
**WAVE 2B.9:** NOT REQUIRED (unchanged)  
**NEXT MACRO PHASE:** NOT STARTED

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. It does not authorize production code, migration `0018`, frontend applications, AI integration, subscription implementation, commit, tag, or push.

Source architecture: `docs/architecture/product-platform-discovery.md`.  
Companion canvas (review-only, outside git): [product-platform-architecture-discovery.canvas.tsx](/Users/syahrezakhatami/.cursor/projects/Users-syahrezakhatami-Projects-patient-health-platform/canvases/product-platform-architecture-discovery.canvas.tsx)

## 1. Verified baseline

If this table were materially wrong, this pass would STOP.

| Item | Live value |
|---|---|
| Repository | `git@github.com:syahrezakhatami/patient-health-platform.git` |
| Branch | `main` == `origin/main` |
| HEAD | `b1606fe38dfaf4ee24d95775c07e77cb842c3736` |
| Tag | Annotated `wave-2b-clinical-foundation-complete` → same SHA |
| Parent | `9a56c0893f8638c1a66d854ca61f137a6177ebf4` (`wave-2b8-family-history-frozen`, still at that SHA) |
| Working tree at inspection | CLEAN (this pass adds discovery docs only; no commit) |
| Alembic | `current == heads == 20260814_0017` |
| Chain | `0001 → … → 0017` |
| Migration `0018` | Does not exist |
| Wave 2B.9 | Does not exist |
| `Wave1PolicyPDP` | Untouched |
| Frozen clinical inventory | Encounter through Family History (13 facts) |

Clinical foundation closeout remains intact.

## 2. Existing backend readiness

The FastAPI modular monolith is **ready to remain** the shared platform API. It is **not** ready to be three backends.

Present: `iam`, `authorization`, `organization`, `mpi`, `clinical` (frozen), `audit`, `clinical_governance` (shell).  
Absent: scheduling, notifications, pharmacy workflow, emergency ops, saas/billing, AI gateway, patient principal, frontends.

`/api/v1` prefix is approved. `/api/v2` and `/fhir/` remain forbidden.

## 3. Three-client architecture assessment

| Client | Assessment |
|---|---|
| Platform Admin Web | Distinct operator app. Must not be the hospital admin workspace. Blocked on least-privilege split (see §5). |
| Healthcare Web | **One** app for hospitals and clinics. Workspaces via tenant, facility, role, permission, resource, purpose. No Doctor/Nurse/Clinic/Hospital split unless a later contract proves need. |
| Patient Mobile | Free. No patient user exists. `PrincipalType.PATIENT` and purpose `PATIENT_ACCESS` are unused hooks. |

UI visibility must never substitute the PDP.

**Repo recommendation:** monorepo (`apps/platform-admin-web`, `apps/healthcare-web`, `apps/patient-mobile` plus generated `/api/v1` client and i18n package). Not created in this pass.

## 4. Multi-tenant assessment

Organization is the **MVP tenant grain**. Types already include `HOSPITAL` and `CLINIC`. Facility is a site under one org. Isolation via `X-Organization-Id` and clinical `organization_id` already prevents Hospital A from reading Hospital B **for staff** (except `PLATFORM_ADMIN` + `iam.platform` bypass).

Not a tenant yet: no subscription FK, no entitlement, no parent/group graph (`NETWORK` is a label only). Patient identity is platform-wide; clinical facts are org-attributed.

**New contracts required:** org-as-tenant, hospital group, patient cross-org self-access, operator without default PHI.

## 5. Platform Admin boundary

Today `PLATFORM_ADMIN` holds **all catalog permissions**, including clinical, and `Wave1PolicyPDP` allows any catalog action when `iam.platform` is present **without org isolation**.

**Future rule:** platform operators manage the SaaS (tenants, plans, health, AI routing). They do **not** freely browse patient clinical data. Break-glass would use the unused `emergency_access_id` slot. READY FOR DESIGN — not implemented here.

## 6. Healthcare Web boundary

Staff application on existing IAM + clinical APIs. `ORG_ADMIN` administers the tenant, not the platform. New workspace roles (pharmacist, dispatcher) need later permission bundles, not new web apps.

## 7. Patient Mobile boundary

Patient-facing, free. Requires a patient principal, account↔`patient_identities.id` binding, patient PDP, and a read-model API. Must not call staff write routes. Same-org self-read is the MVP; multi-org self-read needs a new PDP contract.

## 8. SaaS / subscription assessment

B2B organization subscription; patient access free. Conceptual: plan, subscription, entitlement, invoice/payment ports, statuses `trial`/`active`/`past_due`/`suspended`/`cancelled`. No prices. No payment provider. Suspended denies capabilities, not clinical rows.

## 9. Entitlement architecture

```
Organization → Subscription → Plan → Entitlements → Feature / Limit
```

Authorization: “May this user perform this action?”  
Entitlement: “Has this tenant purchased/enabled this capability?”  
Both required for entitled features. `if plan == "PRO"` is forbidden. Purpose and Consent remain non-grants.

## 10. AI Gateway assessment

Future only. `application → AI Gateway → policy/router → provider adapters`. No hardcoded model in clinical logic. Provider-agnostic. Not started.

## 11. AI governance assessment

Clinician-in-the-loop is mandatory: recommendation → review → decision. Autonomous diagnosis/prescription is forbidden. Clinical AI audit (model version, prompt version, accept/modify/reject, redaction) must be separate from cost telemetry. No unnecessary PHI in billing analytics.

## 12. Patient journey assessment

Identity + encounter + condition + medication + notes **exist**. Appointment, queue, check-in, pharmacy, reminders, follow-up **do not**. Paperless means reuse known identity/facts, not skip safety checks.

## 13. Appointment / scheduling assessment

Own macro capability. Encounter `PLANNED` is not a booking system. Depends on tenant/facility, staff, patient principal, notifications.

## 14. Medication reminder assessment

Frozen Medication has dose/route/start/stop, **not** frequency/timing/SIG. Reminders belong to instruction + schedule + notifications. Do not extend frozen Medication without a new contract.

## 15. Notification assessment

Cross-cutting platform: event → orchestration → preferences → language → channel → delivery. Required by appointments, reminders, results, ambulance status. Do not embed push inside the first scheduling tables.

## 16. Pharmacy assessment

Workflow (prescribe / verify / dispense), referencing Medication. Not a duplicate drug fact. Not FHIR MedicationRequest.

## 17. Emergency / ambulance assessment

Ops domain. `EMER` encounters and anonymous MPI are documentation hooks only. Medical Device is not a fleet. Location/dispatch tables are not authorized here.

## 18. Patient medical-record read model

Projection of the 13 frozen facts. No `patient_histories` table. Chronology, filters, org attribution, pagination, disclosure. Staff vs patient PDPs differ.

## 19. i18n assessment

ID, EN, later ZH. Stable clinical codes; localized display. Separate UI, system messages, templates, education, terminology. No blind AI translation of codes.

## 20. Security assessment

Need: three principal token boundaries, tenant isolation, operator least privilege, patient self-only access, webhook authenticity later, AI egress/redaction, retain rate limit 120. Inherited denial-audit P2 weakens evidence but does not block same-org MVP.

## 21. API / module assessment

Keep `/api/v1`. Add prefixes only with approved modules (`/patient`, `/scheduling`, `/notifications`, `/platform`, `/saas`, `/ai`, `/emergency`, `/pharmacy`). Clinical ownership stays under `/clinical`.

## 22. Dependency graph

Tenancy/operator split → Healthcare Web and patient principal → scheduling + pharmacy + patient read model → notifications consumed by scheduling/reminders/emergency → SaaS entitlements → AI Gateway → clinical AI. Emergency last. See architecture document §23.

## 23. Macro capability candidates

A Tenancy · B Patient experience · C Scheduling · D Pharmacy · E Notifications · F Emergency · G Clinical AI · H SaaS · I Frontends.

## 24. Recommended implementation order

1. A Tenancy + operator least privilege + patient-principal **contract**  
2. I Healthcare Web (registrar + clinician)  
3. B Patient principal + read model + mobile shell  
4. C Scheduling  
5. E Notifications  
6. H SaaS entitlements (billing port later)  
7. D Pharmacy workflow  
8. Medication instruction + reminders  
9. G AI Gateway, then clinician-reviewed AI  
10. F Emergency / ambulance  

Platform Admin Web only after step 1. i18n ID+EN from step 2.

## 25. MVP boundary

**MUST:** shared backend, staff org isolation, operator PHI split before operator UI, Healthcare Web chart, Patient Mobile own-record read (same-org), ID+EN.  
**SHOULD:** appointments, notifications, reminders, manual entitlements, thin Platform Admin.  
**LATER:** payments, AI, ambulance, inpatient ops, pharmacy dispense, ZH, hospital groups, QR check-in.

## 26. Existing P0 / P1 / P2 / P3 impacts

| Sev | Impact on macros |
|---|---|
| P0 / P1 | None |
| P2 denial audit rollback | Does not block MVP; fix before relying on denial SIEM |
| P2 identity non-rewrite | Read model must use canonical identity |
| P2 same-org UUID read | Blocks staff cross-org; keep for MVP; patient multi-org needs new PDP |
| P3 grants / nullable provenance / duplicates / Docker lag | Do not block; do not fix here |

## 27. Topics requiring separate design approval

Before any implementation: tenancy semantics, PLATFORM_ADMIN least privilege, patient principal, scheduling, pharmacy workflow, SIG/reminders, hospital group, SaaS/billing ports, AI Gateway/governance, emergency dispatch, patient multi-org PDP, break-glass, paperless check-in.

This discovery pass did **not** approve those designs.

Access/tenancy follow-on (still not implemented): `docs/architecture/product-access-tenancy-foundation-design.md`.

## 28. Production status

NO PRODUCTION CODE  
NO MIGRATION 0018  
NO FRONTEND CREATED  
NO AI INTEGRATION  
NO SUBSCRIPTION IMPLEMENTATION  
NO COMMIT  
NO TAG  
NO PUSH  

NEXT MACRO PHASE = NOT STARTED

PRODUCT PLATFORM ARCHITECTURE DISCOVERY = COMPLETE
