"""Environment-backed configuration."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    # Global ceiling shared by every caller. Not per-tenant.
    rate_limit_rps: int
    internal_shared_secret: str


def load() -> Settings:
    return Settings(
        database_url=os.environ["DATABASE_URL"],
        redis_url=os.environ["REDIS_URL"],
        rate_limit_rps=int(os.environ.get("RATE_LIMIT_RPS", "200")),
        internal_shared_secret=os.environ["INTERNAL_SHARED_SECRET"],
    )


settings = load()
