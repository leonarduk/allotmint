from __future__ import annotations

import asyncio
import logging
from typing import Dict, Any

from backend.common.goals import load_all_goals
from backend.common.rebalance import suggest_trades

log = logging.getLogger("tasks.auto_rebalance")


async def run_once() -> None:
    """Fetch goals and log rebalance suggestions."""
    all_goals = load_all_goals()
    for user, goals in all_goals.items():
        for g in goals:
            current = 0.0
            actual = {"goal": current, "cash": max(g.target_amount - current, 0.0)}
            trades = suggest_trades(actual, {"goal": 1.0})
            if trades:
                log.info("Suggested trades for %s/%s: %s", user, g.name, trades)


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
