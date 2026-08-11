from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from backend.common.goals import load_all_goals
from backend.common.rebalance import suggest_trades
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)


async def run_once() -> None:
    """Fetch goals and log rebalance suggestions."""
    all_goals = load_all_goals()
    for user, goals in all_goals.items():
        for g in goals:
            current = 0.0
            actual = {"goal": current, "cash": max(g.target_amount - current, 0.0)}
            trades = suggest_trades(actual, {"goal": 1.0})
            if trades:
                logger.info(
                    "Suggested %s trade(s) for %s/%s",
                    sanitise_log_value(len(trades)),
                    sanitise_log_value(user),
                    sanitise_log_value(g.name),
                )


def lambda_handler(_event: Dict[str, Any], _context: Any) -> Dict[str, str]:
    """AWS Lambda entry point."""
    asyncio.run(run_once())
    return {"status": "ok"}


async def schedule(interval_seconds: int = 86400) -> None:
    while True:
        await run_once()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(schedule())
