"""The allowance guardian as a bot on the Bots page (#10495, #10477).

Registered from :mod:`backend.bots.adapters`. Each run calls
:func:`backend.allowance_guardian.report.run` for every owner (or the one owner
a run names) and records alert counts per owner. The full report, with the
figures, stays on ``GET /allowance-guardian/{owner}``; the stored run report
holds counts, codes, the breach month and the report's ``not_modelled``,
``assumptions`` and ``adviser_note``, since alert messages carry amounts.

Alerts: each owner's report alerts become owner-scoped ``digest_items`` in
the run report (:mod:`backend.bots.digest_models`), so they reach the owner
through the bots digest and whatever channels (in-app, email, Telegram,
immediate alerts) the owner chose in their digest settings. Their text is
factual and amount-free, written here rather than copied from the report.

Triggers: Run now on the Bots page, and :func:`run_after_import` once a
transaction import has persisted rows. There is no EventBridge rule yet:
contribution schedules live under the API Lambda's local ``data_root`` on
AWS, so a separate scheduled Lambda would find none (scheduling bots on AWS is
tracked separately). The bot is read-only: it never writes transactions or
the schedule.
"""

from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import Field

from backend.allowance_guardian import report as guardian_report
from backend.bots.digest_models import DigestItem, Severity
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
from backend.bots.run_records import DIGEST_ITEMS_KEY
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

BOT_ID = "allowance-guardian"

_SEVERITY = {"critical": Severity.HIGH, "warning": Severity.MEDIUM, "info": Severity.LOW}
_CONTRIBUTION_WORDS = {"missing": "missing", "wrong_amount": "a different amount", "late": "late"}


class AllowanceGuardianSettings(BotSettings):
    """Public, non-secret guardian settings shown on the Bots page."""

    cadence: Cadence = "monthly"
    run_after_import: bool = Field(default=True, description="Run after a transaction import persists rows")
    isa_deadline_reminder_days: int = Field(
        default=guardian_report.ISA_DEADLINE_REMINDER_DAYS,
        ge=0,
        le=365,
        description="Days before 5 April from which the ISA deadline alert is raised",
    )
    alerts: bool = Field(default=True, description="Add the report's alerts to the owner's bots digest")


def _owners(context: BotRunContext) -> List[str]:
    if context.owner:
        return [context.owner]
    from backend.common.data_loader import list_plots

    return [plot.owner for plot in list_plots() if plot.owner]


def _owner_row(owner: str, result: Dict[str, Any]) -> Dict[str, Any]:
    alerts = result.get("alerts") or []
    pension = result.get("pension_allowance") or {}
    breach = pension.get("projected_breach") if pension.get("available") else None
    isa = result.get("isa_allowance") or {}
    return {
        "owner": owner,
        "tax_year": result.get("tax_year"),
        "schedule_count": result.get("schedule_count", 0),
        "alerts": len(alerts),
        "critical": sum(1 for a in alerts if a.get("level") == "critical"),
        "codes": dict(Counter(a["code"] for a in alerts)),
        "breach_month": breach["month"] if breach else None,
        "carry_forward_month": (pension.get("carry_forward_first_needed") or {}).get("month"),
        "isa_deadline": isa.get("deadline") if isa.get("available") else None,
        "isa_days_to_deadline": isa.get("days_to_deadline") if isa.get("available") else None,
        "contribution_counts": dict((result.get("contributions") or {}).get("counts") or {}),
    }


def _alert_text(code: str, row: Dict[str, Any]) -> Tuple[str, str]:
    """Title and summary for one alert code: facts only, no amounts and no advice."""

    if code.startswith("contribution_"):
        status = code.removeprefix("contribution_")
        count = row["contribution_counts"].get(status, 0)
        word = _CONTRIBUTION_WORDS.get(status, status.replace("_", " "))
        return (
            f"{count} expected contribution(s) this tax year: {word}",
            "Scheduled pension or ISA contributions were not matched to recorded transactions as expected.",
        )
    texts = {
        "pension_projected_breach": (
            f"Pension annual allowance breach projected for {row['breach_month']}",
            "On the recorded schedule, pension contributions would exceed the annual allowance plus "
            f"carry-forward in {row['breach_month']}.",
        ),
        "pension_over_allowance": (
            "Recorded pension contributions are over the annual allowance",
            "Recorded contributions this tax year are over the annual allowance plus carry-forward.",
        ),
        "pension_carry_forward_needed": (
            f"This year's pension annual allowance projected to be used by {row['carry_forward_month']}",
            "On the recorded schedule, later contributions this tax year would draw on carry-forward.",
        ),
        "isa_over_limit": (
            "Recorded and scheduled ISA subscriptions are over the annual limit",
            "Recorded plus scheduled ISA subscriptions this tax year total more than the ISA allowance.",
        ),
        "isa_deadline": (
            f"ISA allowance resets on {row['isa_deadline']}",
            f"{row['isa_days_to_deadline']} days until the ISA allowance resets; part of this year's limit "
            "is unused.",
        ),
    }
    return texts.get(code, (f"Allowance guardian alert: {code}", ""))


def _digest_items(row: Dict[str, Any], levels: Dict[str, str], created: datetime) -> List[Dict[str, Any]]:
    items = []
    for code in row["codes"]:
        title, summary = _alert_text(code, row)
        key = f"{BOT_ID}:{row['owner']}:{code}"
        severity = _SEVERITY.get(levels.get(code, "info"), Severity.LOW)
        item = DigestItem(
            id=key,
            bot=BOT_ID,
            owner=row["owner"],
            severity=severity,
            title=title,
            summary=summary,
            link="/bots",
            action_required=severity in (Severity.HIGH, Severity.MEDIUM),
            created=created,
            dedupe_key=key,
        )
        items.append(item.model_dump(mode="json"))
    return items


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


def _report(rows: List[Dict[str, Any]], failed: List[Dict[str, str]], items: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Every stored report keeps the not-modelled list and the adviser note (#10495).
    return {
        "owners": rows,
        "failed": failed,
        DIGEST_ITEMS_KEY: items,
        "not_modelled": list(guardian_report.NOT_MODELLED),
        "assumptions": list(guardian_report.ASSUMPTIONS),
        "adviser_note": guardian_report.ADVISER_NOTE,
    }


def _result(rows: List[Dict[str, Any]], failed: List[Dict[str, str]], items: List[Dict[str, Any]]) -> RunResult:
    report = _report(rows, failed, items)
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
        "to the tax year end. Runs after transaction imports. Read-only; facts, not advice."
    )
    kind: BotKind = "rules"
    scope: BotScope = "owner"
    settings_model: type[BotSettings] = AllowanceGuardianSettings
    # No EventBridge rule: see the module docstring.
    default_schedule: Optional[Schedule] = None
    timeout_minutes = 10

    def default_settings(self) -> Dict[str, Any]:
        return {"enabled": True, "cadence": "monthly"}

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        reminder_days = getattr(settings, "isa_deadline_reminder_days", guardian_report.ISA_DEADLINE_REMINDER_DAYS)
        alerts_on = getattr(settings, "alerts", True)
        rows: List[Dict[str, Any]] = []
        failed: List[Dict[str, str]] = []
        items: List[Dict[str, Any]] = []
        for owner in _owners(context):
            try:
                result = guardian_report.run(owner, isa_reminder_days=reminder_days)
            except Exception as exc:  # noqa: BLE001 - one owner's failure is recorded; the others still run
                logger.exception("Allowance guardian failed for %s", sanitise_log_value(owner))
                failed.append({"owner": owner, "error": f"{type(exc).__name__}: {exc}"})
                continue
            row = _owner_row(owner, result)
            rows.append(row)
            if alerts_on:
                levels = {a["code"]: a.get("level", "info") for a in result.get("alerts") or []}
                items.extend(_digest_items(row, levels, context.started_at))
        return _result(rows, failed, items)


def run_after_import(actor: Optional[str] = None) -> None:
    """Run the guardian for every owner after a transaction import persisted rows.

    Every owner, not just the importing one: the digest reads only the bot's
    latest run, so a single-owner run would make other owners' open alerts
    look resolved. Skipped (no run recorded) when the bot is disabled or
    ``run_after_import`` is off. Never raises: an import must not fail
    because its follow-up run could not be recorded.
    """

    from backend.bots import runner
    from backend.bots.registry import get_bot
    from backend.bots.settings import load_settings

    try:
        settings = load_settings(get_bot(BOT_ID))
        if not settings.enabled or not getattr(settings, "run_after_import", True):
            return
        # The run record holds the outcome; the raw result is only for direct callers.
        record, _raw = runner.execute(BOT_ID, "event", actor=actor, payload={"reason": "transaction_import"})
        logger.info("Allowance guardian run after import: %s", sanitise_log_value(record.status))
    except Exception as exc:
        logger.error("Allowance guardian run after import failed: %s", sanitise_log_value(type(exc).__name__))
