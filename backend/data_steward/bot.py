"""The data steward as a bot on the Bots page (#10471, #10477).

Scheduled, manual (Run now) and Lambda runs all go through ``backend.bots.runner``,
which records each run and skips it when the bot is disabled or not due. The full
report stays in the steward's own store (``GET /data-steward/latest``); the run
record only carries counts and a pointer, never holdings values.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from typing import Any, Dict, Optional

from pydantic import Field

from backend.bots.registry import (
    BotKind,
    BotRunContext,
    BotScope,
    BotSettings,
    RunResult,
    RunStatus,
    Schedule,
    register_bot,
)
from backend.config import config
from backend.data_steward.runner import StewardLimits
from backend.data_steward.service import run_and_save

BOT_ID = "data-steward"
_STATUS: Dict[str, RunStatus] = {"ok": "ok", "partial": "partial", "error": "failed"}


class DataStewardSettings(BotSettings):
    """Per-run cost caps (public values only)."""

    max_issues: int = Field(
        default=StewardLimits.max_issues, ge=1, le=50, description="Most issues investigated per run"
    )
    max_tool_calls: int = Field(
        default=StewardLimits.max_tool_calls_per_issue, ge=1, le=20, description="Most tool calls per issue"
    )


def to_run_result(report: Dict[str, Any]) -> RunResult:
    """A steward report as a bot run: counts and a pointer, no portfolio values."""

    verdicts = Counter(str(item.get("verdict")) for item in report.get("items") or [])
    errors = [f"{e.get('stage')}: {e.get('error')}" for e in report.get("errors") or []]
    totals = report.get("totals") or {}
    investigated = int(report.get("issues_investigated") or 0)
    summary = f"investigated {investigated} issue{'s' if investigated != 1 else ''}"
    if verdicts.get("fix_available"):
        summary += f", {verdicts['fix_available']} with a fix available"
    return RunResult(
        status=_STATUS.get(str(report.get("status")), "failed"),
        summary=summary,
        report={
            "report": "GET /data-steward/latest",
            "run_id": report.get("run_id"),
            "issues_found": report.get("issues_found"),
            "issues_investigated": investigated,
            "verdicts": dict(verdicts),
            "errors": len(errors),
        },
        error="\n".join(errors) or None,
        model=f"{report.get('provider')}/{report.get('model')}",
        tokens_in=totals.get("input_tokens"),
        tokens_out=totals.get("output_tokens"),
        cost_usd=totals.get("cost_usd"),
        raw={"status": report.get("status"), "run_id": report.get("run_id"), "issues_investigated": investigated},
    )


class DataStewardBot:
    id = BOT_ID
    name = "Data steward"
    description = (
        "AI agent that investigates data-quality issues on held instruments with read-only tools and reports "
        "a verdict, likely cause and evidence for each. It never changes data."
    )
    kind: BotKind = "ai"
    scope: BotScope = "system"
    settings_model: type[BotSettings] = DataStewardSettings
    default_schedule: Optional[Schedule] = Schedule(hour=2)  # cdk DailyDataStewardRun
    timeout_minutes = 15

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": "daily"}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        caps = DataStewardSettings.model_validate(settings.model_dump())
        limits = StewardLimits(max_issues=caps.max_issues, max_tool_calls_per_issue=caps.max_tool_calls)
        return to_run_result(asyncio.run(run_and_save(config, limits=limits)))


register_bot(DataStewardBot(), replace=True)
