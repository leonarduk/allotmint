"""The retirement readiness monitor as a bot on the Bots page (#10510, #10477).

Registered from :mod:`backend.bots.adapters`. Each run calls
:func:`backend.retirement.readiness.run` for every owner with a saved
investment plan (or the one owner a run names) with no overrides, so each
owner's run repeats their own last settings, and stores each owner's report.
The full reports stay on ``GET /retirement-readiness/{owner}/latest``; the
stored run report holds counts only, since the reports carry incomes and pots
and the Bots page shows run reports to every signed-in user.

Digest: each owner's run adds owner-scoped ``digest_items`` (#11312), built
with :func:`backend.bots.run_records.digest_item`, for the assumptions that
changed since that owner's last run, a CPI-versus-assumed-inflation flag, a
report that could not be stored, and an owner whose run failed. Their text
names what changed but carries no amounts, incomes, pots or percentages.

There is no quarterly schedule yet: the registry has no quarterly cadence and
the monitor has no Lambda or EventBridge rule, so it runs from the Bots page's
Run now (and ``POST /retirement-readiness/{owner}/run``).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from backend.bots.digest_models import Severity
from backend.bots.registry import BotKind, BotRunContext, BotScope, BotSettings, RunResult, RunStatus, Schedule
from backend.bots.run_records import DIGEST_ITEMS_KEY, digest_item
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


def _item(owner: str, key: str, created: datetime, severity: Severity, title: str, summary: str) -> Dict[str, Any]:
    """One owner-scoped digest item; its ``dedupe_key`` is ``retirement-readiness:<owner>:<key>``."""

    return digest_item(
        BOT_ID,
        key,
        created,
        owner=owner,
        severity=severity,
        title=title,
        summary=summary,
        action_required=severity is not Severity.LOW,
    )


def _report_items(owner: str, report: Mapping[str, Any], created: datetime) -> List[Dict[str, Any]]:
    """Digest items for one owner's readiness report: labels and counts only, never figures."""

    items: List[Dict[str, Any]] = []
    labels = [str(change["label"]) for change in report.get("assumption_changes") or [] if change.get("label")]
    if labels:
        items.append(
            _item(
                owner,
                "assumption_changes",
                created,
                Severity.LOW,
                f"Retirement readiness: {_plural(len(labels), 'assumption')} changed since the last run",
                f"Changed: {', '.join(labels)}.",
            )
        )
    if (report.get("market") or {}).get("flags"):
        items.append(
            _item(
                owner,
                "inflation_assumption",
                created,
                Severity.LOW,
                "Latest UK CPI differs from the assumed inflation",
                "The latest UK CPI figure differs from the inflation assumed when converting the forecast "
                "to today's money.",
            )
        )
    if not (report.get("storage") or {}).get("stored"):
        items.append(
            _item(
                owner,
                "not_stored",
                created,
                Severity.MEDIUM,
                "Retirement readiness report could not be stored",
                "This run's report was not saved, so the next run compares against an older one.",
            )
        )
    return items


def _failure_item(owner: str, exc: Exception, created: datetime) -> Dict[str, Any]:
    return _item(
        owner,
        "failed",
        created,
        Severity.MEDIUM,
        "Retirement readiness could not run",
        f"The run failed with {type(exc).__name__}; no report was written.",
    )


def _result(ran: int, not_stored: int, failed: List[str], items: List[Dict[str, Any]]) -> RunResult:
    report: Dict[str, Any] = {
        "owners": ran + len(failed),
        "reports": ran,
        "not_stored": not_stored,
        "failed": len(failed),
        DIGEST_ITEMS_KEY: items,
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
        items: List[Dict[str, Any]] = []
        for owner in _owners(context):
            try:
                report = readiness.run(owner, today=context.started_at.date())
            except Exception as exc:  # noqa: BLE001 - one owner's failure is recorded; the others still run
                logger.exception("Retirement readiness failed for %s", sanitise_log_value(owner))
                failed.append(f"{owner}: {type(exc).__name__}: {exc}")
                items.append(_failure_item(owner, exc, context.started_at))
                continue
            ran += 1
            if not report.get("storage", {}).get("stored"):
                not_stored += 1
            items.extend(_report_items(owner, report, context.started_at))
        return _result(ran, not_stored, failed, items)
