"""Bulk ingest. Long-running, called by customer ETL jobs on a schedule."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_db, get_tenant
from app.models import Report, ReportRow, Tenant

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("")
def ingest(
    payload: dict[str, object],
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
) -> dict[str, int]:
    report = Report(
        tenant_id=tenant.id,
        title=str(payload.get("title", "untitled")),
        created_at=datetime.now(UTC),
    )
    db.add(report)
    db.flush()

    raw_rows = payload.get("rows", [])
    assert isinstance(raw_rows, list)
    for raw in raw_rows:
        db.add(ReportRow(report_id=report.id, label=raw["label"], value=raw["value"]))

    db.commit()
    return {"report_id": report.id, "rows": len(raw_rows)}
