"""Lambda entry point to fetch and record dividend transactions on a schedule.

See ``backend.common.dividends.refresh_dividends`` for the fetch/write logic.

Failure handling
----------------
Exceptions are caught so a scheduled invocation failure (e.g. a transient
provider outage) does not raise past the handler; the error is logged and an
error summary is returned instead. This mirrors ``price_refresh.py``'s
handling of ``refresh_prices()`` failures.
"""

from __future__ import annotations

import logging

from backend.common.dividends import refresh_dividends

logger = logging.getLogger("dividends")


def lambda_handler(event, context):
    """Lambda handler invoked by the daily EventBridge schedule."""
    try:
        return refresh_dividends()
    except Exception as exc:
        logger.error("Dividend refresh failed: %s", exc, exc_info=True)
        return {"error": str(exc), "dividends_created": 0}
