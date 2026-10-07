"""Lambda entry point to execute the trading agent on a schedule."""

from __future__ import annotations

from backend.agent.trading_agent import run
from backend.auth import system_job_context


def lambda_handler(event, context):
    """Lambda handler invoked by a scheduler.

    The scheduled run has no request user; run it as a trusted system job so
    owner discovery returns every owner even with auth enabled (#8805, #8914).
    """
    with system_job_context():
        run()
    return {"status": "ok"}
