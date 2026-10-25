"""The allowance guardian as a bot on the Bots page (#10495, #10477).

Registered from :mod:`backend.bots.adapters`. Each run calls
:func:`backend.allowance_guardian.report.run` for every owner (or the one owner
a run names) and records alert counts per owner. The full report, with its
not-modelled list and adviser note, stays on ``GET /allowance-guardian/{owner}``;
the stored run report holds counts, codes and the breach month only, since
alert messages carry amounts.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional

from backend.allowance_guardian import report as guardian_report
from backend.bots.registry import BotKind, BotRunContext, BotScope, BotSettings, RunResult, RunStatus, Schedule
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

BOT_ID = "allowance-guardian"


def _owners(context: BotRunContext) -> List[str]:
    if context.owner:
        return [context.owner]
    from backend.common.data_loader import list_plots

    return [plot.owner for plot in list_plots() if plot.owner]


def _owner_row(owner: str, result: Dict[str, Any]) -> Dict[str, Any]:
    alerts = result.get("alerts") or []
    pension = result.get("pension_allowance") or {}
    breach = pension.get("projected_breach") if pension.get("available") else None
    return {
        "owner": owner,
        "tax_year": result.get("tax_year"),
        "schedule_count": result.get("schedule_count", 0),
        "alerts": len(alerts),
        "critical": sum(1 for a in alerts if a.get("level") == "critical"),
        "codes": dict(Counter(a["code"] for a in alerts)),
        "breach_month": breach["month"] if breach else None,
    }


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count != 1 else ''}"


def _summary(rows: List[Dict[str, Any]]) -> str:
    alerts = sum(row["alerts"] for row in rows)
    critical = sum(row["critical"] for row in rows)
    summary = f"{_plural(alerts, 'alert')} ({critical} critical) across {_plural(len(rows), 'owner')}"
    breaches = sorted({row["breach_month"] for row in rows if row["breach_month"]})
    if breaches:
        summary += f"; pension breach projected {', '.join(breaches)}"
    return summary


def _result(rows: List[Dict[str, Any]], failed: List[Dict[str, str]]) -> RunResult:
    report = {"owners": rows, "failed": failed}
    if not rows and not failed:
        return RunResult(status="skipped", summary="No owners found", report=report)
    if not failed:
        return RunResult(status="ok", summary=_summary(rows), report=report)
    status: RunStatus = "partial" if rows else "failed"
    error = "\n".join(f"{f['owner']}: {f['error']}" for f in failed)
    return RunResult(status=status, summary=f"{_summary(rows)}; {len(failed)} failed", report=report, error=error)


class AllowanceGuardianBot:
    id = BOT_ID
    name = "Allowance guardian"
    description = (
        "Checks that scheduled pension and ISA contributions arrived and projects both allowances "
        "to the tax year end. Read-only; facts, not advice."
    )
    kind: BotKind = "rules"
    scope: BotScope = "owner"
    settings_model: type[BotSettings] = BotSettings
    # No EventBridge rule: contribution schedules live under the API Lambda's
    # local data_root on AWS, so a separate scheduled Lambda would find none.
    default_schedule: Optional[Schedule] = None
    timeout_minutes = 10

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": "monthly"}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        rows: List[Dict[str, Any]] = []
        failed: List[Dict[str, str]] = []
        for owner in _owners(context):
            try:
                result = guardian_report.run(owner)
            except Exception as exc:  # noqa: BLE001 - one owner's failure is recorded; the others still run
                logger.exception("Allowance guardian failed for %s", sanitise_log_value(owner))
                failed.append({"owner": owner, "error": f"{type(exc).__name__}: {exc}"})
                continue
            rows.append(_owner_row(owner, result))
        return _result(rows, failed)
