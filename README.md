# Patient-Centric Longitudinal Health Record Platform

Wave 0 foundation plus Wave 1 IAM, Organization, and Master Patient Index (MPI).

This repository does **not** contain FHIR clinical endpoints, consent, AI, or patient applications. Those belong to later waves. MPI is identity only: it does not store medical history.

Wave 1.5 is the frozen identity baseline. Wave 2A adds Encounter and clinical notes only. See [docs/clinical/wave2a-clinical-foundation.md](docs/clinical/wave2a-clinical-foundation.md).

## Stack

- Python 3.12, FastAPI, SQLAlchemy 2 (asyncio), Alembic
- PostgreSQL, Redis, S3-compatible object storage
- Modular monolith

## Quick start

See [docs/development/local-development.md](docs/development/local-development.md).

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres redis
alembic upgrade head
uvicorn app.main:app --reload --port 9100
```

Liveness: `http://localhost:9100/api/v1/health/live`

## Architecture

Approved baseline: Architecture v2.1. Implementation must not introduce microservices, Kubernetes, Kafka, blockchain, PACS, or a vector database.

## Data rule

No real patient data, NIK, MRN, prescriptions, or clinical documents in this repository. Fixtures must be synthetic.
