"""Lambda entry point for the quarterly retirement readiness run (#10510).

Runs through the bot runner (``backend.bots``, #10477) like the trend-watch
Lambda: every run is recorded on the Bots page, a scheduled firing is skipped
when the bot is disabled or not due, and Run now invokes this Lambda with the
run id. The bot (``backend.retirement.bot``) runs every owner with a saved
investment plan, stores each owner's report and records any owner that failed
without stopping the rest.

It runs as a system job (no request user, #8805) so owner discovery and the
portfolio loaders see every owner. Nothing in the plans, profiles or account
data is written.
"""

from __future__ import annotations

from backend.auth import system_job_context
from backend.bots.runner import handle_lambda_event
from backend.retirement.bot import BOT_ID


def lambda_handler(event, context):
    """Lambda handler invoked by the quarterly schedule or by Run now."""

    with system_job_context():
        result = handle_lambda_event(BOT_ID, event, reraise=True)
    if isinstance(result, dict) and result.get("skipped"):
        return {"status": "skipped", "reason": result.get("reason")}
    return {"status": "ok"}
