# Patient lookup and selection — implementation gate

**Date:** 2026-08-27  
**Kind:** IMPLEMENTATION GATE — not hardening, not freeze  
**Baseline:** `1c502950011a168dbb139980ef758f2660561255` (`healthcare-web-shell-frozen`)  
**Parent:** `ca675b5a41782732995a4021fb85af7b9b29d5b5` (`iam-shell-context-frozen`)  
**Alembic:** `20260814_0018` (one head). Migration **0019 not created**.  

This gate is not a HIPAA, ISO 27001, or SOC 2 certification. No commit, tag, or push in this pass.

Implementation: `docs/architecture/patient-lookup-selection-implementation.md`.  
Design: `docs/architecture/patient-lookup-selection-design.md`.

---

## Verdict

**PATIENT LOOKUP BACKEND = IMPLEMENTED**

**PATIENT SELECTION UI = IMPLEMENTED**

**PATIENT LOOKUP & SELECTION HARDENING = NOT STARTED**

**PATIENT LOOKUP & SELECTION = NOT FROZEN**

**MIGRATION 0019 = NOT CREATED**

**CLINICAL CHART UI = NOT IMPLEMENTED**

**NO COMMIT / NO TAG / NO PUSH**

---

## Contract

| Item | Value |
|---|---|
| Route | `POST /api/v1/mpi/patients/lookup` |
| Request | `PatientLookupRequest`: `lookup_type`, `lookup_value` (`extra=forbid`) |
| Response | `PatientLookupResponse`: `outcome`, `truncated`, `results[]` |
| Audience | `php-api` only |
| Permission | `mpi.identity.read` |
| Purpose | catalog `X-Purpose`; staff `PATIENT_ACCESS` 403 |
| Identifiers | MRN, NIK, BPJS, `PATIENT_IDENTITY_ID` |
| Match | exact after frozen normalization |
| Org | header only; no body org override |
| Facility | not an identity filter |
| MERGED | canonical survivor Y |
| RETIRED | identifier → empty 200; UUID → 409 |
| ANONYMOUS | allowed exact hit |
| Audit | `PATIENT_LOOKUP_ACCESSED` (no raw identifier) |
| Frontend route | `/app/patients/select` |
| Selection | memory-only, org-bound, confirmation required |

Frozen `POST /api/v1/mpi/identities/lookup` unchanged.

---

## Tests

Backend integration: `tests/integration/test_patient_lookup.py` (audience, auth, purpose, tenant isolation, exact MRN/NIK/BPJS/UUID, zero/ambiguous, MERGED, **canonical cross-org pointer**, RETIRED, ANONYMOUS, unverified NIK, masking, audit, no provenance, POST URL privacy).

Frontend: `apps/healthcare-web/src/patient/patient-lookup.test.tsx` (permission gate, identifier types, purposes, confirmation, races, logout/401, storage, 429, XSS, no clinical read, no focus refetch).

Full suites: backend **417 passed**; frontend **81 passed**. No frozen MPI / IAM / Clinical Read / shell regressions observed.

---

## P0 / P1 / P2 / P3

| Severity | Notes |
|---|---|
| P0 | None |
| P1 | Cross-org identifier, foreign canonical hop, late org-A PHI, body org override, full NIK/BPJS, patient/platform audience — **tested and blocked by this implementation** |
| P2 | Success lookup now audited; no auto-select; PHI memory-only; no raw identifier in audit metadata |
| P3 | F5 re-select; Docker `:9100` missing new route (image lag, not rebuilt); per-principal lookup throttle deferred; inherited DENIED-audit rollback unchanged; `check:api-types` needs backend venv Python (FastAPI) |

No unresolved implementation P0. Do not downgrade tenant/PHI issues; none found remaining.

---

## Quality

| Gate | Result |
|---|---|
| `ruff check` / `ruff format --check` | pass |
| `mypy app` | pass |
| `pytest` | 417 passed |
| `npm ci` | pass |
| oxlint `--deny-warnings` | 0 errors, 0 warnings |
| typecheck | pass |
| production build | pass |
| `npm audit --omit=dev` | 0 vulnerabilities |
| OpenAPI source drift | pass |
| Health live/ready | 200 / 200; postgres, redis, object_storage ok |
| Secret/PHI scan | synthetic fixtures only |

---

## Forbidden scope (observed)

No Clinical Chart UI, no Clinical Read frontend calls, no clinical forms, no name search, no recent/today patients, no 0019, no PDP edits, no freeze/hardening documents, no commit/tag/push.
