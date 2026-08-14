# Local development

## Requirements

- Python 3.12+
- Docker (PostgreSQL, Redis, optional MinIO)

## Setup

```bash
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
docker compose up -d postgres redis
# Host ports: Postgres 5433, Redis 6380 (see docker-compose.yml)
alembic upgrade head
# Required after migrate so the Docker/API role (app_dml) can read/write tables:
# psql "$ADMIN_URL" -f scripts/grant_dev_privileges.sql
uvicorn app.main:app --reload --port 9100
```

Compose host mappings:

| Service | Host | Container |
|---|---|---|
| API | `9100` | `8000` |
| PostgreSQL | `5433` | `5432` |
| Redis | `6380` | `6379` |
| EMR MinIO API | `9101` | `9000` |
| EMR MinIO console | `9002` | `9001` |

Inside Compose, the backend talks to MinIO at `http://minio:9000`, not `localhost:9101`. Host `9000` and `9001` are left for other stacks.

## Checks

```bash
ruff check app tests
ruff format app tests
mypy
pytest tests/unit tests/security
```

Integration tests need `TEST_DATABASE_URL` and `TEST_REDIS_URL`.

## Synthetic data only

No real patient identities, NIK, MRN, laboratory results, or clinical documents belong in this repository. If a later wave adds fixtures, mark them `synthetic = true` and use names such as `TEST-PATIENT-001`.
