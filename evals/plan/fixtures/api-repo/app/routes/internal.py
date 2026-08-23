"""Service-to-service endpoints.

Called by the billing worker and the nightly rollup job, not by customers.
Authenticated with a shared secret header rather than an API key, so these
requests have no tenant attached at the edge.
"""

from fastapi import APIRouter, Header, HTTPException
from sqlalchemy import select

from app.models import Tenant
from app.settings import settings

router = APIRouter(prefix="/internal", tags=["internal"])


def _check_secret(x_internal_secret: str = Header(...)) -> None:
    if x_internal_secret != settings.internal_shared_secret:
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/tenants")
def list_tenants(x_internal_secret: str = Header(...)) -> list[dict[str, object]]:
    _check_secret(x_internal_secret)
    # The rollup job pages through this every night at 02:00, fast and hard.
    from app.deps import get_db

    db = next(get_db())
    tenants = db.scalars(select(Tenant)).all()
    return [{"id": t.id, "plan": t.plan} for t in tenants]
