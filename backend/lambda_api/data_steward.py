"""Lambda entry point for the data steward bot (#10471).

Scheduled by ``DataStewardLambda``'s EventBridge rule in
``cdk/stacks/backend_lambda_stack.py`` (after the nightly price refresh) and
invoked by Run now on the Bots page. ``backend.bots.runner`` records the run and
skips it when the bot is disabled or not due (#10477). The run is read-only apart
from its report and run record. A failure is recorded, not re-raised, so
EventBridge does not retry it and spend LLM tokens again.
"""

from __future__ import annotations

from backend.auth import system_job_context
from backend.bots.runner import handle_lambda_event
from backend.data_steward.bot import BOT_ID


def lambda_handler(event, context):
    # No request user: run as a trusted system job, like the price refresh.
    with system_job_context():
        return handle_lambda_event(BOT_ID, event)
