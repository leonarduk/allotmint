"""Project when a savings goal will be reached from its recorded history.

The method is deliberately simple and isolated here so it is easy to change:
a straight line through the *first* and *latest* recorded amounts gives an
average rate of saving, which is extended from the latest amount until it
meets the target. A projection is only produced when the history spans at
least ``MIN_HISTORY_POINTS`` amounts recorded on different dates and at least
``MIN_HISTORY_DAYS`` days, so it is never extrapolated from a single data point
or a few days of noise (#7829).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, timedelta
from typing import Dict, Literal, Optional, Sequence, Tuple

MIN_HISTORY_POINTS = 2
MIN_HISTORY_DAYS = 30
METHOD = "linear_first_to_latest"
_DAYS_PER_MONTH = 365.25 / 12

ProjectionStatus = Literal["projected", "reached", "insufficient_history", "not_progressing"]


@dataclass(frozen=True)
class Projection:
    """Outcome of :func:`project_completion`, including the assumptions used."""

    status: ProjectionStatus
    points: int
    history_start: Optional[date] = None
    history_end: Optional[date] = None
    projected_date: Optional[date] = None
    on_track: Optional[bool] = None
    monthly_rate: Optional[float] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "status": self.status,
            "method": METHOD,
            "points": self.points,
            "min_points": MIN_HISTORY_POINTS,
            "min_days": MIN_HISTORY_DAYS,
            "history_start": self.history_start.isoformat() if self.history_start else None,
            "history_end": self.history_end.isoformat() if self.history_end else None,
            "projected_date": self.projected_date.isoformat() if self.projected_date else None,
            "on_track": self.on_track,
            "monthly_rate": self.monthly_rate,
        }


def _dedupe_by_date(history: Sequence[Tuple[date, float]]) -> list[Tuple[date, float]]:
    """Sort by date, keeping the last amount recorded for any one day."""
    by_day: Dict[date, float] = {}
    for day, amount in history:
        by_day[day] = float(amount)
    return sorted(by_day.items())


def project_completion(
    history: Sequence[Tuple[date, float]],
    target_amount: float,
    target_date: date,
) -> Projection:
    """Return a :class:`Projection` for reaching ``target_amount``.

    ``history`` is a sequence of ``(date, amount saved)`` pairs in any order.
    """
    points = _dedupe_by_date(history)
    if not points:
        return Projection(status="insufficient_history", points=0)

    (first_day, first_amount), (last_day, last_amount) = points[0], points[-1]
    span = Projection(status="insufficient_history", points=len(points), history_start=first_day, history_end=last_day)

    if target_amount > 0 and last_amount >= target_amount:
        return replace(span, status="reached", on_track=last_day <= target_date)

    days = (last_day - first_day).days
    if len(points) < MIN_HISTORY_POINTS or days < MIN_HISTORY_DAYS:
        return span

    daily_rate = (last_amount - first_amount) / days
    monthly_rate = round(daily_rate * _DAYS_PER_MONTH, 2)
    if daily_rate <= 0:
        return replace(span, status="not_progressing", monthly_rate=monthly_rate)

    try:
        projected = last_day + timedelta(days=math.ceil((target_amount - last_amount) / daily_rate))
    except OverflowError:
        # So slow the date is beyond the calendar: treat as not progressing.
        return replace(span, status="not_progressing", monthly_rate=monthly_rate)

    return replace(
        span,
        status="projected",
        projected_date=projected,
        on_track=projected <= target_date,
        monthly_rate=monthly_rate,
    )


__all__ = ["MIN_HISTORY_DAYS", "MIN_HISTORY_POINTS", "METHOD", "Projection", "project_completion"]
