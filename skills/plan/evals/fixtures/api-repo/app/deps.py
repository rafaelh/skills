"""Request-scoped dependencies."""

from collections.abc import Iterator

import redis
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models import ApiKey, Tenant
from app.settings import settings

_engine_session = sessionmaker()
_redis_pool = redis.ConnectionPool.from_url(settings.redis_url, max_connections=50)


def get_db() -> Iterator[Session]:
    session = _engine_session()
    try:
        yield session
    finally:
        session.close()


def get_redis() -> redis.Redis:
    """Shared Redis client. Already used by the report cache and session store."""
    return redis.Redis(connection_pool=_redis_pool)


def get_tenant(
    x_api_key: str = Header(...),
    db: Session = Depends(get_db),
) -> Tenant:
    """Every external request carries X-API-Key; the key maps to exactly one tenant."""
    key = db.scalar(select(ApiKey).where(ApiKey.key_hash == ApiKey.hash(x_api_key)))
    if key is None:
        raise HTTPException(status_code=401, detail="unknown api key")
    return key.tenant
