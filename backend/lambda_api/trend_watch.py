"""Lambda entry point for the weekly trend-watch run (#10476).

Runs through the bot runner (``backend.bots``, #10477) like the trading-agent
Lambda: every run is recorded on the Bots page, a scheduled firing is skipped
when the bot is disabled or not yet due (weekly cadence), and Run now invokes
this Lambda with the run id. The bot itself (``backend.trend_watch.bot``) runs
each owner in turn and records any owner that failed without stopping the rest.
"""

from __future__ import annotations

from backend.auth import system_job_context
from backend.bots.runner import handle_lambda_event
from backend.trend_watch.settings import BOT_ID


def lambda_handler(event, context):
    """Lambda handler invoked by the weekly schedule or by Run now."""

    with system_job_context():
        result = handle_lambda_event(BOT_ID, event, reraise=True)
    if isinstance(result, dict) and result.get("skipped"):
        return {"status": "skipped", "reason": result.get("reason")}
    return {"status": "ok"}
