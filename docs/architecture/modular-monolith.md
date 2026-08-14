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

Medication, laboratory, allergy, timeline, FHIR clinical APIs, and AI remain out of scope.

## Async strategy

SQLAlchemy 2.0 asyncio + asyncpg is the selected database access model. FastAPI handlers are async. Redis uses `redis.asyncio`. This is deliberate: one concurrency model for request I/O.
