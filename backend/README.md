# Backend

FastAPI modular monolith. Application code lives in `app/`.

```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 9100
```

OpenAPI (non-production): `/api/v1/docs`
