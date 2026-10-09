"""Lambda entry point to fetch and record dividend transactions on a schedule.

See ``backend.common.dividends.refresh_dividends`` for the fetch/write logic.

Failure handling
----------------
Exceptions are caught so a scheduled invocation failure (e.g. a transient
provider outage) does not raise past the handler; the error is logged and an
error summary is returned instead. This mirrors ``price_refresh.py``'s
handling of ``refresh_prices()`` failures.

Bot run records
---------------
The handler runs through the bot runner (``backend.bots``, #10477), which
records every run -- a failure is recorded as ``failed`` before the error
summary is returned -- and skips a scheduled firing when the bot is disabled
on the Bots page.
"""

from __future__ import annotations

import logging

from backend.bots.runner import handle_lambda_event
from backend.logging_setup import sanitise_exception_traceback, sanitise_log_value

logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    """Lambda handler invoked by the daily EventBridge schedule."""
    try:
        return handle_lambda_event("dividend-refresh", event, reraise=True)
    except Exception as exc:
        logger.error(
            "Dividend refresh failed: %s; traceback: %s",
            sanitise_log_value(exc),
            sanitise_exception_traceback(exc),
        )
        return {"error": str(exc), "dividends_created": 0}
