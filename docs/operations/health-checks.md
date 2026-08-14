# Health checks

| Endpoint | Meaning | Dependencies |
|---|---|---|
| `GET /api/v1/health/live` | Process is alive | None |
| `GET /api/v1/health/ready` | Process can serve work | PostgreSQL, Redis; object storage except `APP_ENV=test` |

Liveness must not depend on the database. Orchestrators should restart on liveness failure and stop sending traffic on readiness failure.

Both endpoints are unauthenticated. They return no clinical data.

Local Docker host URLs (container still listens on `8000`):

- `http://localhost:9100/api/v1/health/live`
- `http://localhost:9100/api/v1/health/ready`

Readiness checks object storage through the Compose network at `http://minio:9000`. The host mapping for this project's MinIO API is `localhost:9101`.
