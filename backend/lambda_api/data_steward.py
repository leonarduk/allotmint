"""Lambda entry point for the nightly data steward run (#10471).

Scheduled by ``DataStewardLambda``'s EventBridge rule in
``cdk/stacks/backend_lambda_stack.py``, after the nightly price refresh. The run
is read-only apart from saving its report under ``DATA_STEWARD_REPORTS_URI``.
``run_and_save`` already records any failure in the saved report; anything that
still escapes is logged and returned rather than raised, so a failed run does not
trigger EventBridge's retries (each retry would spend LLM tokens again).
"""

from __future__ import annotations

import asyncio
import logging

from backend.auth import system_job_context
from backend.config import config
from backend.data_steward.service import run_and_save
from backend.logging_setup import sanitise_exception_traceback, sanitise_log_value

logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    # No request user: run as a trusted system job, like the price refresh.
    with system_job_context():
        try:
            report = asyncio.run(run_and_save(config))
        except Exception as exc:
            logger.error(
                "Data steward run failed before saving a report: %s; traceback: %s",
                sanitise_log_value(exc),
                sanitise_exception_traceback(exc),
            )
            return {"status": "error", "error": str(exc)}
    return {
        "status": report["status"],
        "run_id": report["run_id"],
        "issues_investigated": report["issues_investigated"],
        "errors": len(report["errors"]),
    }
