"""Annual allowance projection to the UK tax year end (#10479). Arithmetic only.

Pension: starts from the allowance position to date, as computed by allotmint-pro's
``carry_forward_view`` (the single carry-forward implementation, shared with the
MCP ``get_pension_forecast`` tool), then adds the scheduled pension contributions
still to come this tax year. Each future contribution uses the current year's
remaining allowance first, then unused allowance from the earliest of the three
previous years. Reports the date carry-forward would first be needed and the date
the projection would exceed everything available.

ISA: subscriptions so far this tax year plus scheduled subscriptions still to come,
against the ISA subscription limit.

All money is pence (``*_minor``). ``carry_forward_view`` reports GBP; it is
converted once here.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.allowance_guardian.schedule import ScheduledContribution, expected_dates, is_isa_account


def tax_year_bounds(today: date) -> Tuple[date, date]:
    """First and last day (6 April, 5 April) of the UK tax year containing ``today``."""
    start_year = today.year if (today.month, today.day) >= (4, 6) else today.year - 1
    return date(start_year, 4, 6), date(start_year + 1, 4, 5)


def tax_year_label(today: date) -> str:
    start, end = tax_year_bounds(today)
    return f"{start.year}-{end.year}"


def _minor(gbp: Any) -> int:
    return int(round(float(gbp or 0.0) * 100))


def _future_events(
    schedule: Sequence[ScheduledContribution], today: date, year_end: date, pension: bool
) -> List[Tuple[date, int]]:
    """``(date, allowance pence)`` for contributions expected after ``today`` up to ``year_end``."""
    events = []
    for item in schedule:
        if item.is_pension != pension:
            continue
        for due in expected_dates(item, today, year_end):
            if due > today:
                events.append((due, item.allowance_minor() if pension else item.amount_minor))
    return sorted(events)


class _Pots:
    """Remaining current-year allowance, then carry-forward years oldest first."""

    def __init__(self, current_minor: int, carry: List[Tuple[str, int]]):
        self.current = current_minor
        # Tax-year label -> unused pence; insertion order is oldest first.
        self.carry: Dict[str, int] = dict(carry)
        self.excess = 0

    def use(self, amount: int) -> Tuple[bool, bool]:
        """Consume ``amount``; returns (dipped into carry-forward, went over everything)."""
        take = min(self.current, amount)
        self.current -= take
        amount -= take
        dipped = amount > 0
        for label, unused in self.carry.items():
            take = min(unused, amount)
            self.carry[label] = unused - take
            amount -= take
        self.excess += amount
        return dipped, amount > 0

    @property
    def carry_total(self) -> int:
        return sum(self.carry.values())


def _month_row(month: str, rows: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if month not in rows:
        rows[month] = {"month": month, "scheduled_minor": 0}
    return rows[month]


def _walk(events: Iterable[Tuple[date, int]], pots: _Pots, used_to_date: int) -> Dict[str, Any]:
    first_carry: Optional[date] = None
    breach: Optional[date] = None
    cumulative = used_to_date
    months: Dict[str, Dict[str, Any]] = {}
    for due, amount in events:
        dipped, over = pots.use(amount)
        first_carry = first_carry or (due if dipped else None)
        breach = breach or (due if over else None)
        cumulative += amount
        row = _month_row(due.strftime("%Y-%m"), months)
        row["scheduled_minor"] += amount
        row.update(
            projected_used_minor=cumulative,
            current_year_remaining_minor=pots.current,
            carry_forward_remaining_minor=pots.carry_total,
            projected_excess_minor=pots.excess,
        )
    return {"first_carry": first_carry, "breach": breach, "timeline": list(months.values())}


def _when(day: Optional[date]) -> Optional[Dict[str, str]]:
    return {"date": day.isoformat(), "month": day.strftime("%Y-%m")} if day else None


def project_pension_allowance(
    view: Dict[str, Any], schedule: Sequence[ScheduledContribution], today: date
) -> Dict[str, Any]:
    """Project ``view`` (a ``carry_forward_view`` result for ``today``) to the tax year end."""
    rows = view["tax_years"]
    current_row = next(row for row in rows if row["is_current_tax_year"])
    carry = [(row["tax_year"], _minor(row["unused_allowance_gbp"])) for row in rows if not row["is_current_tax_year"]]
    pots = _Pots(_minor(view["current_year_allowance_remaining_gbp"]), carry)
    carry_before = pots.carry_total
    used_to_date = _minor(current_row["gross_contributions_gbp"])
    events = _future_events(schedule, today, tax_year_bounds(today)[1], pension=True)
    walked = _walk(events, pots, used_to_date)
    remaining_after = dict(pots.carry)
    scheduled = sum(amount for _, amount in events)
    return {
        "tax_year": current_row["tax_year"],
        "annual_allowance_minor": _minor(current_row["annual_allowance_gbp"]),
        "annual_allowance_assumed": bool(current_row.get("annual_allowance_assumed")),
        "used_to_date_minor": used_to_date,
        "employer_contributions_to_date_minor": _minor(current_row.get("employer_contributions_gbp")),
        "employer_category_supported": "employer_contributions_gbp" in current_row,
        "already_over_minor": _minor(current_row.get("excess_not_covered_by_carry_forward_gbp")),
        "scheduled_remaining_minor": scheduled,
        "projected_total_minor": used_to_date + scheduled,
        "current_year_remaining_minor": _minor(view["current_year_allowance_remaining_gbp"]),
        "carry_forward_available_minor": carry_before,
        "carry_forward_by_year": [
            {"tax_year": label, "unused_minor": unused, "projected_unused_minor": remaining_after[label]}
            for label, unused in carry
        ],
        "carry_forward_first_needed": _when(walked["first_carry"]),
        "projected_excess_minor": pots.excess,
        "projected_breach": _when(walked["breach"]),
        "timeline": walked["timeline"],
    }


def isa_subscribed_minor(transactions: Iterable[Any], today: date) -> int:
    """Pence paid into ISA accounts this tax year up to ``today`` (transfers between ISAs excluded)."""
    start, _ = tax_year_bounds(today)
    total = 0
    for tx in transactions:
        if (tx.type or "").strip().upper() != "DEPOSIT" or tx.amount_minor is None or not tx.date:
            continue
        if not is_isa_account(tx.account) or "transfer" in (tx.comments or "").lower():
            continue
        if (tx.currency or "GBP").strip().upper() == "GBP" and start <= date.fromisoformat(str(tx.date)[:10]) <= today:
            total += abs(int(round(tx.amount_minor)))
    return total


def project_isa_allowance(
    subscribed_minor: int, limit_minor: int, schedule: Sequence[ScheduledContribution], today: date
) -> Dict[str, Any]:
    """ISA subscriptions so far plus those scheduled, against ``limit_minor``, with days to 5 April."""
    year_end = tax_year_bounds(today)[1]
    events = _future_events(schedule, today, year_end, pension=False)
    scheduled = sum(amount for _, amount in events)
    cumulative, over_on = subscribed_minor, None
    for due, amount in events:
        cumulative += amount
        if over_on is None and cumulative > limit_minor:
            over_on = due
    return {
        "tax_year": tax_year_label(today),
        "limit_minor": limit_minor,
        "subscribed_minor": subscribed_minor,
        "remaining_minor": max(limit_minor - subscribed_minor, 0),
        "already_over_minor": max(subscribed_minor - limit_minor, 0),
        "scheduled_remaining_minor": scheduled,
        "projected_total_minor": subscribed_minor + scheduled,
        "projected_over_limit": _when(over_on),
        "deadline": year_end.isoformat(),
        "days_to_deadline": (year_end - today).days,
    }
