# Modular monolith

The backend is a single FastAPI process with explicit bounded-context packages under `backend/app/modules/`.

## Rules

- Domain logic must not import FastAPI or Starlette.
- HTTP adapters live in `app/api/` or a module `api/` package.
- FHIR adapters must not become the internal domain model.
- Do not extract microservices, introduce Kafka, Kubernetes, a vector database, PACS, or blockchain without a later architecture gate.

## Wave 0 modules

| Module | Why it exists now |
|---|---|
| `iam` | OIDC/JWT token validation interface |
| `authorization` | PDP interface and deny-by-default skeleton |
| `audit` | Audit event schema and insert-only persistence |
| `clinical_governance` | Shell only — owns rules, not patient facts |

## Wave 1 modules

| Module | Why it exists now |
|---|---|
| `iam` | Users, roles, organization memberships (in addition to JWT validation) |
| `authorization` | Wave 1 permission PDP; unknown actions still deny by default |
| `organization` | Organization, facility, organization identifiers |
| `mpi` | Patient identity, identifiers, matching, merge/unmerge |

## Wave 2A modules

| Module | Why it exists now |
|---|---|
| `clinical` | Encounter and clinical note foundation. Not a FHIR store. |

## Wave 2B.1 modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds Condition (problem list and encounter diagnosis). Still not a FHIR store. |

## Wave 2B.2a modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Observation (measurements/findings). Not a laboratory domain and not a FHIR Observation store. |

## Wave 2B.2b modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Laboratory (order, specimen, result). Not a FHIR DiagnosticReport / ServiceRequest / Specimen store. |

## Wave 2B.3a modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Medication (prescribed or reported medication fact). Not a FHIR MedicationRequest / MedicationAdministration store. |

## Wave 2B.3b modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Allergy (documented allergy/intolerance fact). Not a FHIR AllergyIntolerance store. |

## Wave 2B.3c modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Consent (documented permit/refuse decision). Not a FHIR Consent store and not a PDP. |

## Wave 2B.4 modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Immunization (documented vaccination fact). Not a FHIR Immunization store. |

## Wave 2B.5 modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Procedure (documented performed or reported procedure fact). Not a FHIR Procedure store. |

## Wave 2B.6 modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Medical Device (documented patient-device association). Not a FHIR Device store and not inventory. |

## Wave 2B.7 modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Adverse Event (documented coded adverse event). Not a FHIR AdverseEvent store, not pharmacovigilance, and not incident management. |

## Wave 2B.8 modules

| Module | Why it exists now |
|---|---|
| `clinical` | Adds native Family History (documented family-history fact). Not a FHIR FamilyMemberHistory store and not Patient History. |

Timeline, FHIR clinical APIs, and AI remain out of scope.

## Async strategy

SQLAlchemy 2.0 asyncio + asyncpg is the selected database access model. FastAPI handlers are async. Redis uses `redis.asyncio`. This is deliberate: one concurrency model for request I/O.
