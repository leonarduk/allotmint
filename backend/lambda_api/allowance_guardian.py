"""Lambda entry point for the monthly allowance guardian run (#10495).

Runs through the bot runner (``backend.bots``, #10477) like the decision-journal
Lambda: every run is recorded on the Bots page, a scheduled firing is skipped
when the bot is disabled or not due, and Run now invokes this Lambda with the
run id. The bot (``backend.allowance_guardian.bot``) checks every owner's
contribution schedule against their transactions and records each owner's
alerts; one owner's failure does not stop the rest.

It runs as a system job (no request user, #8805) so owner discovery sees every
owner. Nothing in the schedules, transactions or account data is written.
"""

from __future__ import annotations

from backend.allowance_guardian.bot import BOT_ID
from backend.auth import system_job_context
from backend.bots.runner import handle_lambda_event


def lambda_handler(event, context):
    """Lambda handler invoked by the monthly schedule or by Run now."""

    with system_job_context():
        result = handle_lambda_event(BOT_ID, event, reraise=True)
    if isinstance(result, dict) and result.get("skipped"):
        return {"status": "skipped", "reason": result.get("reason")}
    return {"status": "ok"}
