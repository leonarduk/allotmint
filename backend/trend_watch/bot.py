"""Trend watch as a bot on the Bots page (#10476, #10477).

Registered from :mod:`backend.bots.adapters`. The bot runs
:func:`backend.trend_watch.service.run_for_owner` for each owner (or the one
owner a run names), so the scheduled Lambda, Run now and the per-owner route
all produce the same stored reports. Its settings are the public detector and
investigation thresholds, layered over ``config.trend_watch`` by
:func:`backend.trend_watch.settings.load_trend_watch_config`.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Any, Coroutine, Dict, List, Optional, TypeVar

from pydantic import Field

from backend.bots.registry import (
    BotKind,
    BotRunContext,
    BotScope,
    BotSettings,
    Cadence,
    RunResult,
    RunStatus,
    Schedule,
)
from backend.logging_setup import sanitise_log_value
from backend.trend_watch.settings import BOT_ID, load_base_trend_watch_config

logger = logging.getLogger(__name__)

T = TypeVar("T")


class TrendWatchBotSettings(BotSettings):
    """Public, non-secret trend-watch thresholds (the fields of ``TrendWatchConfig``)."""

    cadence: Cadence = "weekly"
    min_signals: int = Field(default=2, ge=2, le=6, description="Signals that must agree (never fewer than 2)")
    min_new_signals: int = Field(default=1, ge=1, le=4, description="Trigger signals that must be new")
    new_lookback_days: int = Field(default=5, ge=1, le=60, description="Trading days per run (a week)")
    memory_runs: int = Field(default=4, ge=1, le=26, description="Earlier runs a new signal must have been off in")
    sma_slope_days: int = Field(default=20, ge=1, le=120, description="Trading days for a falling 200-day average")
    rs_low_days: int = Field(default=126, ge=20, le=504, description="Trading days for a new relative-strength low")
    swing_days: int = Field(default=20, ge=5, le=120, description="Trading days per swing window")
    market_move_tolerance: float = Field(
        default=0.05, ge=0, le=0.5, description="Max gap to the benchmark's move for a market-wide verdict"
    )
    max_investigated: int = Field(default=5, ge=0, le=50, description="Holdings investigated per owner per run")
    max_tool_calls: int = Field(default=8, ge=0, le=40, description="Tool calls per investigated holding")


def _run_coroutine(coro: Coroutine[Any, Any, T]) -> T:
    """Run ``coro`` to completion from sync code, even when called inside an event loop.

    The context is copied so the runner's system-job flag reaches the worker thread.
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    context = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(context.run, asyncio.run, coro).result()


def _owners(context: BotRunContext) -> List[str]:
    if context.owner:
        return [context.owner]
    from backend.common.data_loader import list_plots

    return [plot.owner for plot in list_plots() if plot.owner]


def _summarise(rows: List[Dict[str, Any]], failed: List[Dict[str, str]]) -> RunResult:
    to_review = sum(row["to_review"] for row in rows)
    holdings = sum(row["holdings_checked"] for row in rows)
    summary = f"{to_review} to review of {holdings} holdings across {len(rows)} owner{'s' if len(rows) != 1 else ''}"
    report = {"owners": rows, "failed": failed}
    if failed:
        status: RunStatus = "partial" if rows else "failed"
        error = "\n".join(f"{f['owner']}: {f['error']}" for f in failed)
        return RunResult(status=status, summary=f"{summary}; {len(failed)} failed", report=report, error=error)
    if not rows:
        return RunResult(status="partial", summary="No owners found", report=report)
    return RunResult(status="ok", summary=summary, report=report)


class TrendWatchBot:
    id = BOT_ID
    name = "Trend watch"
    description = (
        "Weekly review list of held positions whose trend has newly turned down, with the data checked first "
        "and the cause investigated. A review list, not trade instructions."
    )
    kind: BotKind = "ai"
    scope: BotScope = "owner"
    settings_model: type[BotSettings] = TrendWatchBotSettings
    default_schedule: Optional[Schedule] = Schedule(hour=6, weekday=5)  # cdk WeeklyTrendWatchRun
    timeout_minutes = 15

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": "weekly", **asdict(load_base_trend_watch_config())}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        from backend.trend_watch.service import run_for_owner

        rows: List[Dict[str, Any]] = []
        failed: List[Dict[str, str]] = []
        for owner in _owners(context):
            try:
                report = _run_coroutine(run_for_owner(owner, notify=True))
            except Exception as exc:  # noqa: BLE001 - one owner's failure is recorded; the others still run
                logger.exception("Trend watch failed for %s", sanitise_log_value(owner))
                failed.append({"owner": owner, "error": f"{type(exc).__name__}: {exc}"})
                continue
            rows.append(
                {
                    "owner": owner,
                    "holdings_checked": report.get("holdings_checked", 0),
                    "to_review": len(report.get("items") or []),
                    "report": f"trend_watch/{owner}/latest.json",
                }
            )
        return _summarise(rows, failed)
