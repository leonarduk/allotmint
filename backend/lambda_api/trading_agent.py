"""Lambda entry point to execute the trading agent on a schedule."""

from __future__ import annotations

from backend.agent.trading_agent import run


def lambda_handler(event, context):
    """Lambda handler invoked by a scheduler."""
    run()
    return {"status": "ok"}
