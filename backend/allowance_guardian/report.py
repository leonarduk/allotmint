"""The guardian's single entry point: :func:`run` builds one owner's report (#10479).

Facts and arithmetic only. Every report carries :data:`NOT_MODELLED` and
:data:`ADVISER_NOTE`, whatever the figures say. Read-only: it loads transactions
and the saved schedule and writes nothing.

The #10477 bot registry does not exist yet; when it lands, the guardian registers
there as a monthly bot whose ``run`` calls :func:`run` and stores the result.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence
from zoneinfo import ZoneInfo

from backend.allowance_guardian.match import match_contributions
from backend.allowance_guardian.projection import (
    isa_subscribed_minor,
    project_isa_allowance,
    project_pension_allowance,
    tax_year_bounds,
    tax_year_label,
)
from backend.allowance_guardian.schedule import ScheduledContribution, load_schedule
from backend.common.core_optional import UPGRADE_MESSAGE, missing_package
from backend.config import config

LONDON = ZoneInfo("Europe/London")
ISA_DEADLINE_REMINDER_DAYS = 60
_DEFAULT: Any = object()  # run(allowances=...) not given: use the installed allotmint-pro

NOT_MODELLED = [
    "Tapered annual allowance: the pension annual allowance is reduced when adjusted income is over £260,000. "
    "Not modelled; the standard allowance is shown.",
    "Money purchase annual allowance (MPAA): a £10,000 limit applies once flexible benefits have been taken "
    "from a pension. Not modelled.",
    "Pensions not recorded in AllotMint: contributions to workplace or other schemes that are not recorded "
    "here, and employer or salary-sacrifice payments not recorded as tagged deposits, are not counted, so "
    "real allowance use may be higher than shown.",
]

ADVISER_NOTE = (
    "This report states figures, dates and limits only. It is information, not advice: decisions about "
    "pension contributions, carry-forward and pension tax should be taken with a regulated financial adviser."
)

ASSUMPTIONS = [
    "UK tax year 6 April to 5 April, dated in Europe/London.",
    "Scheduled personal contributions with relief at source count at the net amount plus 25% basic-rate "
    "relief; employer and salary-sacrifice contributions count at face value.",
    "Relief at source already paid but not yet credited by the provider is not in the figures to date.",
    "Carry-forward uses the current year's allowance first, then the earliest of the three previous years.",
]


def london_today() -> date:
    return datetime.now(LONDON).date()


def _pro_allowances() -> Optional[Any]:
    """allotmint-pro's allowance functions, or None when allotmint-pro is not installed."""
    try:
        from allotmint_pro.allowances import annual_allowance_info
        from allotmint_pro.mcp_server.pension_tools import carry_forward_view
    except ModuleNotFoundError as exc:
        if not missing_package(exc):
            raise
        return None
    return SimpleNamespace(carry_forward_view=carry_forward_view, annual_allowance_info=annual_allowance_info)


def _owner_transactions(owner: str) -> List[Any]:
    from backend.routes.transactions import load_all_transactions

    return [tx for tx in load_all_transactions() if (tx.owner or "").lower() == owner.lower()]


def _gbp(minor: int) -> str:
    return f"£{minor / 100:,.2f}"


def _pension_section(allowances: Any, transactions: List[Any], schedule: Sequence[ScheduledContribution], today: date):
    if allowances is None:
        return {"available": False, "reason": UPGRADE_MESSAGE}
    view = allowances.carry_forward_view(transactions, today=today)
    return {"available": True, **project_pension_allowance(view, schedule, today)}


def _isa_section(allowances: Any, transactions: List[Any], schedule: Sequence[ScheduledContribution], today: date):
    if allowances is None:
        return {"available": False, "reason": UPGRADE_MESSAGE}
    info = allowances.annual_allowance_info("ISA", tax_year_label(today))
    limit_minor = int(round(float(info["limit_gbp"]) * 100))
    subscribed = isa_subscribed_minor(transactions, today)
    return {
        "available": True,
        "limit_assumed": bool(info.get("assumed")),
        **project_isa_allowance(subscribed, limit_minor, schedule, today),
    }


def _contribution_alerts(counts: Dict[str, int]) -> List[Dict[str, str]]:
    alerts = []
    for status, label in (("missing", "missing"), ("wrong_amount", "a different amount"), ("late", "late")):
        if counts.get(status):
            message = f"{counts[status]} expected contribution(s) this tax year: {label}."
            alerts.append({"level": "warning", "code": f"contribution_{status}", "message": message})
    return alerts


def _pension_alerts(pension: Dict[str, Any]) -> List[Dict[str, str]]:
    if not pension.get("available"):
        return []
    alerts = []
    if pension["already_over_minor"]:
        over = _gbp(pension["already_over_minor"])
        message = f"Recorded contributions are {over} over the allowance plus carry-forward."
        alerts.append({"level": "critical", "code": "pension_over_allowance", "message": message})
    if pension["projected_breach"]:
        message = (
            f"On the recorded schedule, pension contributions would exceed the annual allowance plus carry-forward "
            f"in {pension['projected_breach']['month']}, by {_gbp(pension['projected_excess_minor'])} by 5 April."
        )
        alerts.append({"level": "critical", "code": "pension_projected_breach", "message": message})
    elif pension["carry_forward_first_needed"]:
        message = (
            "On the recorded schedule, this year's annual allowance would be fully used in "
            f"{pension['carry_forward_first_needed']['month']}; contributions after that would draw on "
            "carry-forward from earlier years."
        )
        alerts.append({"level": "warning", "code": "pension_carry_forward_needed", "message": message})
    return alerts


def _isa_alerts(isa: Dict[str, Any]) -> List[Dict[str, str]]:
    if not isa.get("available"):
        return []
    alerts = []
    if isa["projected_total_minor"] > isa["limit_minor"]:
        total, limit = _gbp(isa["projected_total_minor"]), _gbp(isa["limit_minor"])
        message = f"Recorded and scheduled ISA subscriptions total {total}, over the {limit} limit."
        alerts.append({"level": "critical", "code": "isa_over_limit", "message": message})
    if isa["days_to_deadline"] <= ISA_DEADLINE_REMINDER_DAYS:
        message = (
            f"{isa['days_to_deadline']} days until the ISA allowance resets on {isa['deadline']}; "
            f"{_gbp(isa['remaining_minor'])} of this year's limit is unused."
        )
        alerts.append({"level": "info", "code": "isa_deadline", "message": message})
    return alerts


def run(
    owner: str,
    *,
    today: Optional[date] = None,
    data_root: Optional[Path] = None,
    transactions: Optional[List[Any]] = None,
    schedule: Optional[Sequence[ScheduledContribution]] = None,
    allowances: Any = _DEFAULT,
) -> Dict[str, Any]:
    """Build ``owner``'s contribution and allowance report.

    ``today`` defaults to the Europe/London date. ``transactions`` (one owner's
    ``Transaction``-like rows), ``schedule`` and ``allowances`` (an object with
    allotmint-pro's ``carry_forward_view`` and ``annual_allowance_info``; None when
    unavailable) default to the stored data and the installed allotmint-pro.
    """
    today = today or london_today()
    if transactions is None:
        transactions = _owner_transactions(owner)
    if schedule is None:
        root = data_root or Path(config.data_root or Path(__file__).resolve().parents[2] / "data")
        schedule = load_schedule(owner, root).contributions
    if allowances is _DEFAULT:
        allowances = _pro_allowances()
    contributions = match_contributions(schedule, transactions, tax_year_bounds(today)[0], today)
    pension = _pension_section(allowances, transactions, schedule, today)
    isa = _isa_section(allowances, transactions, schedule, today)
    return {
        "owner": owner,
        "as_of": today.isoformat(),
        "tax_year": tax_year_label(today),
        "schedule_count": len(schedule),
        "contributions": contributions,
        "pension_allowance": pension,
        "isa_allowance": isa,
        "alerts": _contribution_alerts(contributions["counts"]) + _pension_alerts(pension) + _isa_alerts(isa),
        "not_modelled": list(NOT_MODELLED),
        "assumptions": list(ASSUMPTIONS),
        "adviser_note": ADVISER_NOTE,
    }
