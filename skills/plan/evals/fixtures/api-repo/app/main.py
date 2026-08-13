"""Application wiring."""

from fastapi import FastAPI

from app.middleware.ratelimit import RateLimitMiddleware
from app.routes import ingest, internal, reports

app = FastAPI(title="Atlas API")

# Order matters: the limiter runs before auth, so it sees no tenant context.
app.add_middleware(RateLimitMiddleware)

app.include_router(reports.router)
app.include_router(ingest.router)
app.include_router(internal.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
