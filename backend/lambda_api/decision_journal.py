"""Lambda entry point for the daily decision-journal run (#10481, #10525).

Runs through the bot runner (``backend.bots``, #10477) like the trend-watch
Lambda: every run is recorded on the Bots page, a scheduled firing is skipped
when the bot is disabled, and Run now invokes this Lambda with the run id. The
bot itself (``backend.decision_journal.bot``) lists unlogged trades and runs
the reviews that have fallen due; it writes only the journal sidecar store,
never the plan.
"""

from __future__ import annotations

from backend.auth import system_job_context
from backend.bots.runner import handle_lambda_event
from backend.decision_journal.bot import BOT_ID


def lambda_handler(event, context):
    """Lambda handler invoked by the daily schedule or by Run now."""

    with system_job_context():
        result = handle_lambda_event(BOT_ID, event, reraise=True)
    if isinstance(result, dict) and result.get("skipped"):
        return {"status": "skipped", "reason": result.get("reason")}
    return {"status": "ok"}
