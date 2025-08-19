from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from backend.reports import (
    ReportData,
    compile_report,
    report_to_csv,
    report_to_pdf,
    _parse_date,
)

router = APIRouter(tags=["reports"])


@router.get("/reports/{owner}")
async def owner_report(
    owner: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    format: str = "json",
):
    """Return summary report for ``owner``.

    Optional query parameters ``start`` and ``end`` limit the date range and
    accept ISO formatted dates (``YYYY-MM-DD``).
    Set ``format`` to ``csv`` or ``pdf`` to download the report.
    """

    start_d = _parse_date(start)
    end_d = _parse_date(end)

    try:
        data: ReportData = compile_report(owner, start=start_d, end=end_d)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Owner not found")

    if format.lower() == "csv":
        content = report_to_csv(data)
        return Response(
            content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={owner}_report.csv"},
        )
    if format.lower() == "pdf":
        content = report_to_pdf(data)
        return Response(
            content,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={owner}_report.pdf"},
        )
    return data.to_dict()

