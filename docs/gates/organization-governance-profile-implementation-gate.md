# Organization Governance Profile — implementation gate

**Date:** 2026-08-28  
**Kind:** IMPLEMENTATION GATE — regression closure completed separately  
**Baseline:** `c3590dd142f60a79aed3d4f042ff1c505cb2371c` (`provider-governance-foundation-frozen`)  
**Alembic:** `20260814_0020` (parent `20260814_0019`, one head)

Design: `docs/architecture/organization-governance-profile-design.md`  
Approval: `docs/gates/organization-governance-profile-design-approval.md`  
Regression closure: `docs/gates/organization-governance-profile-regression-closure.md`  
Security hardening: `docs/gates/organization-governance-profile-security-hardening.md`

---

## Verdict history

| Stage | Status |
|---|---|
| Initial implementation pass | OGP foundation coded; **453/31** full suite — verification incomplete |
| Regression closure pass | **488/0** full suite — **COMPLETE** |
| Security / adversarial hardening | **528/0** full suite; SEC-001 fixed — **COMPLETE** |

**ORGANIZATION GOVERNANCE PROFILE BACKEND FOUNDATION = IMPLEMENTED**

**ORGANIZATION GOVERNANCE PROFILE = READY FOR FINAL FREEZE VERIFICATION**

---

## Implementation summary

- Migration `20260814_0020`: 8 OGP tables, triggers, five permission codes, **empty** provider seed
- Org + platform governance APIs (8 MVP org commands + 2 platform)
- Resolver, idempotency, audit, concurrency protections
- **No** Clinical Note / Observation / AI integration

---

## Authorization (post-closure)

| Surface | Requirement |
|---|---|
| `GET effective-context` | `php-api` + org membership only |
| Management reads/writes | `governance.profile.read` / `.manage` / `.approval.record` / `.feature.activate` as applicable |
| Platform capabilities | `php-platform` + `governance.provider.manage` |

### Default role provisioning

| Role | Governance permissions |
|---|---|
| ORG_ADMIN | `profile.read`, `profile.manage` |
| CLINICIAN | none |
| AUDITOR | none |
| PLATFORM_ADMIN | `provider.manage` |
| approval.record / feature.activate | unassigned by default |

---

## Quality gates (final)

| Check | Result |
|---|---|
| Full backend pytest | **488 passed** |
| OGP targeted | **21 passed** (4 unit + 17 integration) |
| Clinical Note | **39 passed** |
| Migration roundtrip | pass |
| Provider registry | **0** |
| OpenAPI check | pass |
| ruff `app/` | pass |
| mypy `app/` | pass |

**NO COMMIT / NO TAG / NO PUSH**
