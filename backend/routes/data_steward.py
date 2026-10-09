"""Data steward report endpoint (#10471).

``GET /data-steward/latest`` serves the last saved run report. Runs are started
from the Bots page (``POST /bots/data-steward/run``, #10477) or by the nightly
``DataStewardLambda``. The steward is read-only; applying a proposed fix goes
through the existing ``POST /data-quality/issues/{id}/fix``.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.data_steward.store import load_latest_report

router = APIRouter(prefix="/data-steward", tags=["data-steward"])


@router.get("/latest")
def latest_report() -> Dict[str, Any]:
    report = load_latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No data steward report yet.")
    return report
