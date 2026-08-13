"""Report reads. The endpoint enterprise customers complain about."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.deps import get_db, get_tenant
from app.models import Report, ReportRow, Tenant

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{report_id}")
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
) -> dict[str, object]:
    report = db.get(Report, report_id)
    if report is None or report.tenant_id != tenant.id:
        return {"error": "not found"}

    row_ids = db.scalars(select(ReportRow.id).where(ReportRow.report_id == report_id)).all()

    # One query per row. Fine at 50 rows, not fine at the 40k rows our
    # largest accounts have.
    rows = []
    for row_id in row_ids:
        row = db.get(ReportRow, row_id)
        if row is not None:
            rows.append({"label": row.label, "value": row.value})

    return {"id": report.id, "title": report.title, "rows": rows}


@router.get("")
def list_reports(
    db: Session = Depends(get_db),
    tenant: Tenant = Depends(get_tenant),
) -> list[dict[str, object]]:
    reports = db.scalars(select(Report).where(Report.tenant_id == tenant.id)).all()
    return [{"id": r.id, "title": r.title} for r in reports]
