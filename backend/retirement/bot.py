"""The retirement readiness monitor as a bot on the Bots page (#10510, #10477).

Registered from :mod:`backend.bots.adapters`. Each run calls
:func:`backend.retirement.readiness.run` for every owner with a saved
investment plan (or the one owner a run names) with no overrides, so each
owner's run repeats their own last settings, and stores each owner's report.
The full reports stay on ``GET /retirement-readiness/{owner}/latest``; the
stored run report holds counts only, since the reports carry incomes and pots
and the Bots page shows run reports to every signed-in user.

There is no quarterly schedule yet: the registry has no quarterly cadence and
the monitor has no Lambda or EventBridge rule, so it runs from the Bots page's
Run now (and ``POST /retirement-readiness/{owner}/run``).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.bots.registry import BotKind, BotRunContext, BotScope, BotSettings, RunResult, RunStatus, Schedule
from backend.logging_setup import sanitise_log_value
from backend.retirement import readiness

logger = logging.getLogger(__name__)

BOT_ID = "retirement-readiness"


def _owners(context: BotRunContext) -> List[str]:
    if context.owner:
        return [context.owner]
    from backend.common.investment_plan import plan_owners

    # The same data root readiness.run reads each plan from.
    return sorted(plan_owners(readiness._accounts_root(None).parent))


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"


def _result(ran: int, not_stored: int, failed: List[str]) -> RunResult:
    report: Dict[str, Any] = {
        "owners": ran + len(failed),
        "reports": ran,
        "not_stored": not_stored,
        "failed": len(failed),
    }
    if not ran and not failed:
        return RunResult(status="skipped", summary="No owners with an investment plan", report=report)
    summary = f"{_plural(ran, 'report')} written"
    if not_stored:
        summary += f", {not_stored} not stored"
    if failed:
        summary += f"; {len(failed)} failed"
    status: RunStatus = "ok"
    if failed:
        status = "partial" if ran else "failed"
    elif not_stored:
        status = "partial"
    return RunResult(status=status, summary=summary, report=report, error="\n".join(failed) or None)


class RetirementReadinessBot:
    id = BOT_ID
    name = "Retirement readiness"
    description = (
        "Replays each owner's projected pension pot through historical return sequences and reports the "
        "sustainable income and what changed since the last run. Read-only; facts, not advice."
    )
    kind: BotKind = "ai"
    scope: BotScope = "owner"
    # Per-owner settings carry over from each owner's previous run (ReadinessSettings), so the
    # Bots page only holds enabled/cadence.
    settings_model: type[BotSettings] = BotSettings
    # No EventBridge rule or Lambda yet (quarterly is not a registry cadence); see the module docstring.
    default_schedule: Optional[Schedule] = None
    timeout_minutes = 15

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": "monthly"}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        ran = 0
        not_stored = 0
        failed: List[str] = []
        for owner in _owners(context):
            try:
                report = readiness.run(owner, today=context.started_at.date())
            except Exception as exc:  # noqa: BLE001 - one owner's failure is recorded; the others still run
                logger.exception("Retirement readiness failed for %s", sanitise_log_value(owner))
                failed.append(f"{owner}: {type(exc).__name__}: {exc}")
                continue
            ran += 1
            if not report.get("storage", {}).get("stored"):
                not_stored += 1
        return _result(ran, not_stored, failed)
