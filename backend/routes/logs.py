import os
import time
from collections import deque
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.config import config

router = APIRouter(prefix="/logs", tags=["logs"])

_DEFAULT_LINES = 200

# How far back to search CloudWatch Logs and how many raw events to scan before
# giving up. filter_log_events has no "most recent N" mode — it returns events
# in chronological order within the queried window — so a bounded lookback and
# scan cap keep a single request from paginating through the log group's full
# retention (backend_lambda_stack.py sets ONE_WEEK retention).
_CLOUDWATCH_LOOKBACK_MS = 24 * 60 * 60 * 1000
_CLOUDWATCH_MAX_EVENTS = 5000


@router.get("", response_class=PlainTextResponse)
def read_logs(lines: int = _DEFAULT_LINES) -> str:
    """Return the latest backend log lines.

    On AWS (``config.app_env == "aws"``) the Lambda filesystem has no
    ``logs/backend.log`` to read — stdout/stderr go to CloudWatch Logs instead —
    so recent events are fetched from the Lambda's own log group. Locally, the
    same lines are read from ``logs/backend.log`` as written by the
    ``run-backend``/``run-frontend`` dev scripts.

    Parameters
    ----------
    lines:
        Maximum number of lines to return, defaults to ``_DEFAULT_LINES``.
    """
    if config.app_env == "aws":
        return _read_cloudwatch_logs(lines)
    return _read_local_log_file(lines)


def _read_local_log_file(lines: int) -> str:
    root = Path(config.repo_root or Path.cwd())
    log_file = root / "logs" / "backend.log"
    if not log_file.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    try:
        with log_file.open("r", encoding="utf-8") as fh:
            content = "".join(deque(fh, maxlen=lines))
        return content
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def _read_cloudwatch_logs(lines: int) -> str:
    log_group_name = os.getenv("BACKEND_LOG_GROUP_NAME")
    if not log_group_name:
        raise HTTPException(status_code=404, detail="CloudWatch log group not configured")

    client = boto3.client("logs")
    start_time = int(time.time() * 1000) - _CLOUDWATCH_LOOKBACK_MS
    events: list[dict] = []
    try:
        paginator = client.get_paginator("filter_log_events")
        for page in paginator.paginate(
            logGroupName=log_group_name,
            startTime=start_time,
            interleaved=True,
        ):
            events.extend(page.get("events", []))
            if len(events) >= _CLOUDWATCH_MAX_EVENTS:
                break
    except ClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not events:
        raise HTTPException(status_code=404, detail="No log events found")

    events.sort(key=lambda event: event.get("timestamp", 0))
    recent = events[-lines:]
    return "".join(f"{event.get('message', '')}\n" for event in recent)
