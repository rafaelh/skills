# Atlas API

Multi-tenant reporting API for our analytics product.

- Python 3.12, FastAPI, uvicorn (4 workers per task)
- Postgres 15 via SQLAlchemy 2.x
- Redis 7 — already used for session storage and the report cache
- Deployed as one ECS Fargate service behind an ALB, 3 tasks

## Layout

| Path | What |
|---|---|
| `app/main.py` | app wiring, middleware registration |
| `app/settings.py` | env-backed config |
| `app/deps.py` | request-scoped dependencies (db session, redis, tenant) |
| `app/models.py` | SQLAlchemy models |
| `app/middleware/ratelimit.py` | the limiter we have today |
| `app/routes/` | endpoints |

## Running

```
uvicorn app.main:app --reload
pytest
```
