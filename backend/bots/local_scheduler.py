"""Run bots on their schedules on a local server (#10925).

Deployed, each bot's EventBridge rule is its scheduler (see
:mod:`backend.bots.runner`). A local server has no EventBridge, so without
this module every "Next run" on the Bots page would be a time that never
comes. When ``app_env == "local"`` the app starts :func:`local_bot_scheduler_loop`,
which fires the bots listed in ``local_bot_schedule`` at their
:attr:`~backend.bots.registry.Bot.default_schedule` times through
:func:`backend.bots.runner.execute` with ``trigger="schedule"`` -- the same
path an EventBridge firing takes, so the enabled/cadence ("not due") checks,
the in-progress guard and the run record all apply unchanged.

By default only price refresh and dividend refresh are scheduled locally:
bots that send external messages (trading agent Telegram alerts, the pension
report email, trend watch, the data steward) run on a schedule only when
listed explicitly. Every other environment schedules nothing here, so a
deployment never runs a bot twice.

On startup a bot whose latest firing was missed while the server was down
(no completed run since it) is run once straight away, so prices are not left
stale until the next day's slot.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterable, List, Optional, Tuple

from backend.bots import runner
from backend.bots.registry import Bot, Schedule, list_bots
from backend.bots.runs import RunRecord, list_runs
from backend.bots.settings import load_settings
from backend.config import Config
from backend.logging_setup import sanitise_exception_traceback, sanitise_log_value

logger = logging.getLogger(__name__)

#: Bots scheduled locally when ``local_bot_schedule`` is not set: jobs that
#: only refresh data and send nothing outside the app.
DEFAULT_LOCAL_BOTS: Tuple[str, ...] = ("price-refresh", "dividend-refresh")

# Wake at least this often while waiting, so a laptop that slept through a
# slot (the monotonic clock may pause) notices on waking, not hours later.
_MAX_SLEEP_SECONDS = 300.0
# Far enough back to find the latest firing of a monthly schedule, including
# one on day 29-31 that skips short months (Aug 31 -> Oct 31 is 61 days).
_CATCH_UP_LOOKBACK = timedelta(days=62)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def local_bot_ids(cfg: Config) -> frozenset[str]:
    """Bot ids this server schedules itself: none unless ``app_env == "local"``."""

    if cfg.app_env != "local":
        return frozenset()
    ids = cfg.local_bot_schedule
    return frozenset(DEFAULT_LOCAL_BOTS if ids is None else ids)


def is_scheduled_here(bot: Bot, cfg: Config) -> bool:
    """Whether ``bot``'s schedule actually fires for this server.

    Locally only the bots in ``local_bot_schedule``; anywhere else the bot's
    EventBridge rule, i.e. any bot with a schedule.
    """

    if bot.default_schedule is None:
        return False
    if cfg.app_env == "local":
        return bot.id in local_bot_ids(cfg)
    return True


def scheduled_bots(cfg: Config) -> List[Bot]:
    """The registered bots this server fires itself, in registry order."""

    ids = local_bot_ids(cfg)
    bots = [bot for bot in list_bots() if bot.id in ids and bot.default_schedule is not None]
    unknown = ids - {bot.id for bot in list_bots()}
    if unknown:
        logger.warning("local_bot_schedule lists unknown bots: %s", sanitise_log_value(sorted(unknown)))
    return bots


def next_firing(bots: Iterable[Bot], after: datetime) -> Tuple[Optional[datetime], List[Bot]]:
    """The earliest firing strictly after ``after`` and every bot firing then."""

    when: Optional[datetime] = None
    due: List[Bot] = []
    for bot in bots:
        fire = next(bot.default_schedule.fire_times_after(after), None)  # type: ignore[union-attr]
        if fire is None:
            continue
        if when is None or fire < when:
            when, due = fire, [bot]
        elif fire == when:
            due.append(bot)
    return when, due


def previous_firing(schedule: Schedule, now: datetime) -> Optional[datetime]:
    """The latest firing of ``schedule`` at or before ``now``."""

    latest: Optional[datetime] = None
    for fire in schedule.fire_times_after(now - _CATCH_UP_LOOKBACK):
        if fire > now:
            break
        latest = fire
    return latest


def _last_completed(records: Iterable[RunRecord]) -> Optional[RunRecord]:
    return next((r for r in records if r.status not in ("skipped", "running")), None)


def missed_firing(bot: Bot, now: datetime) -> bool:
    """Whether ``bot`` should catch up now: its latest firing has no run since.

    Any completed run counts (a Run now after the slot is as good as the
    scheduled one). Disabled bots and ones their cadence says are not due are
    left alone, so a restart never records a pile of skipped runs.
    """

    schedule = bot.default_schedule
    if schedule is None:
        return False
    fire = previous_firing(schedule, now)
    if fire is None:
        return False
    records = list_runs(bot.id)
    last = _last_completed(records)
    if last is not None and last.started_at >= fire:
        return False
    settings = load_settings(bot)
    return settings.enabled and runner.is_due(settings.cadence, runner.last_scheduled_run(records), now)


def _run(bot_id: str, execute: Callable[..., Any]) -> None:
    """Fire one bot; the runner records failures, anything else is logged here."""

    try:
        record, _raw = execute(bot_id, "schedule")
    except Exception as exc:
        logger.error(
            "Local schedule could not run bot %s: %s", sanitise_log_value(bot_id), sanitise_exception_traceback(exc)
        )
        return
    logger.info(
        "Local schedule ran bot %s: %s %s",
        sanitise_log_value(bot_id),
        sanitise_log_value(record.status),
        sanitise_log_value(record.summary),
    )


async def _catch_up(cfg: Config, bots: List[Bot], execute: Callable[..., Any], now: datetime) -> None:
    for bot in bots:
        try:
            missed = await asyncio.to_thread(missed_firing, bot, now)
        except Exception as exc:
            logger.error(
                "Could not check bot %s for a missed run: %s",
                sanitise_log_value(bot.id),
                sanitise_exception_traceback(exc),
            )
            continue
        if missed and not cfg.offline_mode:
            logger.info("Bot %s missed its last scheduled run; running it now", sanitise_log_value(bot.id))
            await asyncio.to_thread(_run, bot.id, execute)


async def _sleep_until(when: datetime, now: Callable[[], datetime], sleep: Callable[[float], Any]) -> None:
    while (remaining := (when - now()).total_seconds()) > 0:
        await sleep(min(remaining, _MAX_SLEEP_SECONDS))


async def local_bot_scheduler_loop(
    cfg: Config,
    *,
    execute: Callable[..., Any] = runner.execute,
    now: Callable[[], datetime] = _now,
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> None:
    """Catch up missed runs, then fire each scheduled bot at its slot until cancelled.

    Bots due at the same moment run one after another. A slot reached while
    ``offline_mode`` is on is skipped.
    """

    bots = scheduled_bots(cfg)
    if not bots:
        return
    await _catch_up(cfg, bots, execute, now())
    after = now()
    while True:
        when, due = next_firing(bots, after)
        if when is None:
            logger.error("Local bot scheduler stopped: no further firing times")
            return
        await _sleep_until(when, now, sleep)
        # Never re-fire this slot, even if the clock reads a moment early.
        after = max(when, now())
        if cfg.offline_mode:
            logger.info("Scheduled bot runs skipped: offline_mode is on")
            continue
        for bot in due:
            await asyncio.to_thread(_run, bot.id, execute)


def start_local_bot_scheduler(cfg: Config) -> Optional[asyncio.Task]:
    """Start :func:`local_bot_scheduler_loop` on a local server; otherwise ``None``.

    Never starts in tests or inside a Lambda (where EventBridge schedules
    bots), whatever ``app_env`` says.
    """

    if os.getenv("TESTING") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        return None
    if cfg.offline_mode:
        logger.info("Local bot schedule not started: offline_mode is on")
        return None
    bots = scheduled_bots(cfg)
    if not bots:
        return None
    logger.info(
        "Local bot schedule: %s",
        sanitise_log_value(", ".join(f"{bot.id} ({bot.default_schedule.description})" for bot in bots)),  # type: ignore[union-attr]
    )
    return asyncio.create_task(local_bot_scheduler_loop(cfg))


__all__ = [
    "DEFAULT_LOCAL_BOTS",
    "is_scheduled_here",
    "local_bot_ids",
    "local_bot_scheduler_loop",
    "missed_firing",
    "next_firing",
    "previous_firing",
    "scheduled_bots",
    "start_local_bot_scheduler",
]
