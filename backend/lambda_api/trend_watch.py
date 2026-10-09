"""Lambda entry point for the weekly trend-watch run (#10476)."""

from __future__ import annotations

import asyncio
import logging

from backend.auth import system_job_context
from backend.common.data_loader import list_plots
from backend.logging_setup import sanitise_log_value
from backend.trend_watch.service import run_for_owner

logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """Run trend watch for every owner and send the alerts.

    Runs as a trusted system job so owner discovery returns every owner with
    auth enabled, as the trading-agent Lambda does (#8805, #8914). One owner's
    failure is logged and counted; it does not stop the others.
    """

    failed = []
    with system_job_context():
        owners = [plot.owner for plot in list_plots() if plot.owner]
        for owner in owners:
            try:
                asyncio.run(run_for_owner(owner, notify=True))
            except Exception as exc:  # noqa: BLE001 - reported in the result and the log
                logger.exception("Trend watch failed for %s", sanitise_log_value(owner))
                failed.append({"owner": owner, "error": f"{type(exc).__name__}: {exc}"})
    return {"status": "partial" if failed else "ok", "owners": len(owners), "failed": failed}
