"""Lambda entry point to execute the trading agent on a schedule.

Runs through the bot runner (``backend.bots``, #10477) so every run is
recorded on the Bots page and a scheduled firing is skipped when the bot is
disabled there. Failures are recorded and then re-raised, as before.
"""

from __future__ import annotations

from backend.auth import system_job_context
from backend.bots.runner import handle_lambda_event


def lambda_handler(event, context):
    """Lambda handler invoked by a scheduler.

    The scheduled run has no request user; run it as a trusted system job so
    owner discovery returns every owner even with auth enabled (#8805, #8914).
    """
    with system_job_context():
        result = handle_lambda_event("trading-agent", event, reraise=True)
    if isinstance(result, dict) and result.get("skipped"):
        return {"status": "skipped", "reason": result.get("reason")}
    return {"status": "ok"}
