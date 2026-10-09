"""Data steward report endpoints (#10471).

``GET /data-steward/latest`` serves the last saved run report. ``POST
/data-steward/run`` runs the steward by hand; like the self-update route it is
only registered for local deployments (``backend/bootstrap/routers.py``): on AWS
the nightly ``DataStewardLambda`` runs it. The steward is read-only, so neither
endpoint changes any data except writing the report itself; applying a proposed
fix goes through the existing ``POST /data-quality/issues/{id}/fix``.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from backend.config import config
from backend.data_steward.service import run_and_save
from backend.data_steward.store import load_latest_report

router = APIRouter(prefix="/data-steward", tags=["data-steward"])
run_router = APIRouter(prefix="/data-steward", tags=["data-steward"])

# One run at a time: a run makes many LLM and tool calls, so a second click while
# one is in progress is refused rather than doubling the cost.
_run_lock = asyncio.Lock()


@router.get("/latest")
def latest_report() -> Dict[str, Any]:
    report = load_latest_report()
    if report is None:
        raise HTTPException(status_code=404, detail="No data steward report yet.")
    return report


@run_router.post("/run")
async def run_now() -> Dict[str, Any]:
    if _run_lock.locked():
        raise HTTPException(status_code=409, detail="A data steward run is already in progress.")
    async with _run_lock:
        return await run_and_save(config)
