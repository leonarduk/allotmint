"""Run bots: the single path for scheduled, manual and event-triggered runs.

Every call to :func:`execute` writes exactly one run record -- ``skipped``
when the bot is disabled, not due, or already running; ``failed`` when it
raises -- so no run is ever silent.

Schedules stay in CDK: each EventBridge rule fires at the most frequent
cadence the bot supports, and :func:`execute` checks the stored settings
(``enabled``, ``cadence``) on each firing, recording a skipped run when the
bot is not due. The app therefore never needs permission to edit
EventBridge rules.

Run now (:func:`start_run`) is idempotent per bot: while a non-stale
``running`` record exists a second start is refused with
:class:`BotBusyError`, so two runs can never send duplicate alerts or emails.
Locally the run then executes as a FastAPI background task; deployed, the
bot's own Lambda is invoked asynchronously with the run id
(:func:`dispatch_run`), and its handler finishes that same record via
:func:`handle_lambda_event`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import traceback
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional, Tuple

from backend.auth import system_job_context
from backend.bots.registry import Bot, BotRunContext, BotSettings, Cadence, RunResult, RunTrigger, Schedule, get_bot
from backend.bots.runs import RunRecord, get_run, latest_run, list_runs, new_run_id, save_run
from backend.bots.settings import load_settings
from backend.config import config
from backend.logging_setup import sanitise_exception_traceback, sanitise_log_value

logger = logging.getLogger(__name__)

#: JSON map of bot id -> Lambda function name/ARN, set on the backend Lambda
#: by CDK so Run now can invoke the bot's own Lambda when deployed.
BOT_LAMBDAS_ENV = "BOT_LAMBDA_FUNCTIONS"

_MAX_ERROR_CHARS = 8000
# Weekly bots run on the first firing at least this long after the last
# scheduled run, so a daily rule at a fixed hour still lands on day 7.
_WEEKLY_MIN_GAP = timedelta(days=6, hours=12)

# Serialises the busy-check + "running" write in start_run within a process.
_start_lock = threading.Lock()


class BotBusyError(RuntimeError):
    """Raised by :func:`start_run` while another run of the bot is in progress."""

    def __init__(self, running: RunRecord):
        super().__init__(f"Bot {running.bot_id} is already running (run {running.id})")
        self.running = running


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ───────────────────────────── due / next run ─────────────────────────────


def last_scheduled_run(records: Iterable[RunRecord]) -> Optional[RunRecord]:
    """Most recent scheduled run that actually ran (not skipped/running)."""

    return next(
        (r for r in records if r.trigger == "schedule" and r.status not in ("skipped", "running")),
        None,
    )


def is_due(cadence: Cadence, last: Optional[RunRecord], now: datetime) -> bool:
    """Whether a schedule firing at ``now`` should run, given the last run."""

    if cadence == "daily" or last is None:
        return True
    if cadence == "weekly":
        return now - last.started_at >= _WEEKLY_MIN_GAP
    return (now.year, now.month) != (last.started_at.year, last.started_at.month)


def next_due(
    schedule: Optional[Schedule],
    settings: BotSettings,
    records: Iterable[RunRecord],
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """The next firing of the bot's rule at which it will actually run."""

    if schedule is None or not settings.enabled:
        return None
    last = last_scheduled_run(records)
    for fire in schedule.fire_times_after(now or _now()):
        if is_due(settings.cadence, last, fire):
            return fire
    return None


def running_record(bot: Bot, now: Optional[datetime] = None) -> Optional[RunRecord]:
    """The bot's in-progress run, ignoring ones older than its timeout."""

    latest = latest_run(bot.id)
    if latest is None or latest.status != "running":
        return None
    if (now or _now()) - latest.started_at > timedelta(minutes=bot.timeout_minutes):
        logger.warning(
            "Ignoring stale running record %s for bot %s", sanitise_log_value(latest.id), sanitise_log_value(bot.id)
        )
        return None
    return latest


# ───────────────────────────────── execute ────────────────────────────────


def _format_error(exc: BaseException) -> str:
    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    return text[-_MAX_ERROR_CHARS:]


def _finish(record: RunRecord, result: RunResult, finished: datetime) -> RunRecord:
    return record.model_copy(
        update={
            "status": result.status,
            "summary": result.summary,
            "report": result.report,
            "error": result.error,
            "owner": result.owner or record.owner,
            "model": result.model,
            "tokens_in": result.tokens_in,
            "tokens_out": result.tokens_out,
            "cost_usd": result.cost_usd,
            "finished_at": finished,
            "duration_seconds": round((finished - record.started_at).total_seconds(), 3),
        }
    )


def _skip_reason(bot: Bot, settings: BotSettings, trigger: RunTrigger, run_id: Optional[str], now: datetime) -> str:
    if trigger == "schedule":
        if not settings.enabled:
            return "Disabled in settings"
        last = last_scheduled_run(list_runs(bot.id))
        if not is_due(settings.cadence, last, now):
            return f"Not due ({settings.cadence} cadence)"
    busy = running_record(bot, now)
    if busy is not None and busy.id != run_id:
        return f"Another run ({busy.id}) is in progress"
    return ""


def _safe_save(record: RunRecord) -> RunRecord:
    """Persist ``record``; a store failure is logged, never raised.

    Recording a run must not be able to stop the job itself (e.g. a missing
    S3 grant on a scheduled Lambda), so bookkeeping errors only log.
    """

    try:
        return save_run(record)
    except Exception as exc:
        logger.error(
            "Failed to save run record %s for bot %s: %s",
            sanitise_log_value(record.id),
            sanitise_log_value(record.bot_id),
            sanitise_exception_traceback(exc),
        )
        return record


def _existing_record(bot_id: str, run_id: Optional[str]) -> Optional[RunRecord]:
    if not run_id:
        return None
    try:
        return get_run(bot_id, run_id)
    except Exception as exc:
        logger.error(
            "Failed to read run %s for bot %s: %s",
            sanitise_log_value(run_id),
            sanitise_log_value(bot_id),
            sanitise_exception_traceback(exc),
        )
        return None


def execute(
    bot_id: str,
    trigger: RunTrigger,
    *,
    actor: Optional[str] = None,
    run_id: Optional[str] = None,
    owner: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
    reraise: bool = False,
) -> Tuple[RunRecord, Any]:
    """Run ``bot_id`` once and record it. Returns ``(record, raw_result)``.

    ``run_id`` continues a record created by :func:`start_run`. With
    ``reraise`` an exception from the bot is re-raised after it has been
    recorded, so a Lambda that used to fail loudly still does.
    """

    bot = get_bot(bot_id)
    started = _now()
    existing = _existing_record(bot_id, run_id)
    record = existing or RunRecord(
        id=run_id or new_run_id(),
        bot_id=bot_id,
        trigger=trigger,
        status="running",
        started_at=started,
        actor=actor,
        owner=owner,
    )

    try:
        settings = load_settings(bot)
    except Exception as exc:
        logger.error(
            "Failed to load settings for bot %s: %s", sanitise_log_value(bot_id), sanitise_exception_traceback(exc)
        )
        result = RunResult(status="failed", summary="Could not load settings", error=_format_error(exc))
        return _safe_save(_finish(record, result, _now())), None

    try:
        reason = _skip_reason(bot, settings, trigger, record.id if existing else None, started)
    except Exception as exc:
        # Could not read the run history: run anyway rather than silently
        # skipping a scheduled job.
        logger.error(
            "Failed to check whether bot %s is due: %s", sanitise_log_value(bot_id), sanitise_exception_traceback(exc)
        )
        reason = ""
    if reason:
        logger.info("Bot %s run skipped: %s", sanitise_log_value(bot_id), sanitise_log_value(reason))
        return _safe_save(_finish(record, RunResult(status="skipped", summary=reason), _now())), None

    record = _safe_save(record.model_copy(update={"status": "running"}))
    context = BotRunContext(
        run_id=record.id,
        bot_id=bot_id,
        trigger=trigger,
        started_at=record.started_at,
        actor=actor,
        owner=owner,
        payload=payload or {},
    )
    try:
        # Bots are jobs with no request user: owner discovery must see every
        # owner even with auth enabled (#8805). Set here, on the thread that
        # runs the bot, because the ContextVar does not cross threads.
        with system_job_context():
            result = bot.run(context, settings)
    except Exception as exc:
        logger.error(
            "Bot %s run %s failed: %s",
            sanitise_log_value(bot_id),
            sanitise_log_value(record.id),
            sanitise_exception_traceback(exc),
        )
        failed = _safe_save(
            _finish(record, RunResult(status="failed", summary=f"Failed: {exc}", error=_format_error(exc)), _now())
        )
        if reraise:
            raise
        return failed, None

    finished = _safe_save(_finish(record, result, _now()))
    logger.info(
        "Bot %s run %s finished: %s %s",
        sanitise_log_value(bot_id),
        sanitise_log_value(record.id),
        sanitise_log_value(result.status),
        sanitise_log_value(result.summary),
    )
    return finished, result.raw


# ─────────────────────────────── run now ──────────────────────────────────


def start_run(bot_id: str, *, actor: Optional[str] = None) -> RunRecord:
    """Create the ``running`` record for a manual run, or raise BotBusyError."""

    bot = get_bot(bot_id)
    with _start_lock:
        busy = running_record(bot)
        if busy is not None:
            raise BotBusyError(busy)
        record = RunRecord(
            id=new_run_id(),
            bot_id=bot_id,
            trigger="manual",
            status="running",
            started_at=_now(),
            actor=actor,
        )
        return save_run(record)


def _lambda_for(bot_id: str) -> Optional[str]:
    raw = os.getenv(BOT_LAMBDAS_ENV)
    if not raw:
        return None
    try:
        mapping = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.error("%s is not valid JSON: %s", sanitise_log_value(BOT_LAMBDAS_ENV), sanitise_log_value(exc))
        return None
    name = mapping.get(bot_id) if isinstance(mapping, dict) else None
    return str(name) if name else None


def dispatch_run(record: RunRecord, background_tasks: Any) -> RunRecord:
    """Start the work for a record from :func:`start_run`.

    Deployed (``app_env == "aws"``) the bot's Lambda is invoked async; any
    other environment runs it as a FastAPI background task.
    """

    if config.app_env != "aws":
        background_tasks.add_task(execute, record.bot_id, "manual", actor=record.actor, run_id=record.id)
        return record

    function_name = _lambda_for(record.bot_id)
    if not function_name:
        return _fail_dispatch(record, "No Lambda is configured for this bot")
    try:
        import boto3  # type: ignore

        boto3.client("lambda").invoke(
            FunctionName=function_name,
            InvocationType="Event",
            Payload=json.dumps({"bot_run_id": record.id, "bot_trigger": "manual", "actor": record.actor}).encode(),
        )
    except Exception as exc:
        logger.error(
            "Failed to invoke Lambda for bot %s: %s",
            sanitise_log_value(record.bot_id),
            sanitise_exception_traceback(exc),
        )
        return _fail_dispatch(record, f"Could not start the bot's Lambda: {exc}")
    return record


def _fail_dispatch(record: RunRecord, message: str) -> RunRecord:
    logger.error(
        "Bot %s run %s not started: %s",
        sanitise_log_value(record.bot_id),
        sanitise_log_value(record.id),
        sanitise_log_value(message),
    )
    return _safe_save(_finish(record, RunResult(status="failed", summary=message, error=message), _now()))


# ──────────────────────────────── Lambda ──────────────────────────────────


def trigger_for_event(event: Any) -> Tuple[RunTrigger, Optional[str], Optional[str]]:
    """Classify a Lambda event as ``(trigger, run_id, actor)``.

    EventBridge schedules send ``source == "aws.events"``; Run now sends a
    ``bot_run_id``; anything else (the post-deploy Trigger, a CI warm-up
    invoke) is a direct ``invoke`` that runs regardless of settings.
    """

    if isinstance(event, dict):
        if event.get("bot_run_id"):
            return "manual", str(event["bot_run_id"]), event.get("actor")
        if event.get("source") == "aws.events":
            return "schedule", None, None
    return "invoke", None, None


def handle_lambda_event(bot_id: str, event: Any, *, reraise: bool = False) -> Any:
    """Run ``bot_id`` for a Lambda invocation and return the job's own result.

    Returns ``{"skipped": True, ...}`` when the run was skipped; otherwise the
    job's raw result, so a wrapped handler returns exactly what it did before.
    """

    trigger, run_id, actor = trigger_for_event(event)
    record, raw = execute(bot_id, trigger, actor=actor, run_id=run_id, reraise=reraise)
    if record.status == "skipped":
        return {"skipped": True, "reason": record.summary, "run_id": record.id}
    return raw


__all__ = [
    "BOT_LAMBDAS_ENV",
    "BotBusyError",
    "dispatch_run",
    "execute",
    "handle_lambda_event",
    "is_due",
    "last_scheduled_run",
    "next_due",
    "running_record",
    "start_run",
    "trigger_for_event",
]
