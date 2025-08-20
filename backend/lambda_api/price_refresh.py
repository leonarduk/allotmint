"""Lambda entry point to refresh prices on a schedule.

After refreshing prices the optional trading agent can be triggered. The
behaviour is controlled via the ``ALLOTMINT_ENABLE_TRADING_AGENT`` environment
variable so deployments can enable or disable automated trading without code
changes.
"""

from __future__ import annotations

import os

from backend.common.prices import refresh_prices

try:  # trading agent is optional; skip if missing
    import trading_agent  # type: ignore
except Exception:  # pragma: no cover - only hit when package missing
    trading_agent = None


def lambda_handler(event, context):
    """Lambda handler invoked by the scheduler."""

    result = refresh_prices()

    # honour environment flag so trading agent can be toggled per deployment
    if os.getenv("ALLOTMINT_ENABLE_TRADING_AGENT", "").lower() in {"1", "true", "yes"} and trading_agent is not None:
        trading_agent.run()

    return result
