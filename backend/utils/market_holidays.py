"""Exchange trading calendars for gap detection (#10961).

Like :mod:`backend.utils.uk_holidays`, the calendars are computed from each
exchange's published holiday rules rather than a third-party library. The
exchange is the suffix of a ``TICKER.EXCHANGE`` code (``L``, ``N``, ``DE``,
``TO`` …); an exchange with no calendar of its own keeps the UK one, which is
what every series used before.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache
from typing import Callable

from backend.utils.uk_holidays import (
    _christmas_and_boxing_day,
    _easter_sunday,
    _last_weekday_of_month,
    _nth_weekday_of_month,
    _substitute_if_weekend,
    uk_bank_holidays,
)

_MON, _THU = 0, 3

# Unscheduled NYSE closures: state funerals, 9/11 and Hurricane Sandy.
_NYSE_SPECIAL_CLOSURES = frozenset(
    {
        date(1994, 4, 27),
        date(2001, 9, 11),
        date(2001, 9, 12),
        date(2001, 9, 13),
        date(2001, 9, 14),
        date(2004, 6, 11),
        date(2007, 1, 2),
        date(2012, 10, 29),
        date(2012, 10, 30),
        date(2018, 12, 5),
        date(2025, 1, 9),
    }
)


def _nearest_weekday(d: date) -> date:
    """NYSE observance: a Saturday holiday moves to Friday, a Sunday one to Monday."""
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def nyse_holidays(year: int) -> frozenset[date]:
    """Full-day NYSE/Nasdaq closures for ``year``."""
    good_friday = _easter_sunday(year) - timedelta(days=2)
    days = {
        good_friday,
        _nth_weekday_of_month(year, 2, _MON, 3),  # Washington's Birthday
        _last_weekday_of_month(year, 5, _MON),  # Memorial Day
        _nearest_weekday(date(year, 7, 4)),  # Independence Day
        _nth_weekday_of_month(year, 9, _MON, 1),  # Labor Day
        _nth_weekday_of_month(year, 11, _THU, 4),  # Thanksgiving
        _nearest_weekday(date(year, 12, 25)),  # Christmas
    }
    # New Year's Day on a Sunday is observed on the Monday; on a Saturday the
    # NYSE does not close on the Friday before (it would end the prior year).
    new_year = date(year, 1, 1)
    if new_year.weekday() != 5:
        days.add(_nearest_weekday(new_year))
    if year >= 1998:
        days.add(_nth_weekday_of_month(year, 1, _MON, 3))  # Martin Luther King Jr. Day
    if year >= 2022:
        days.add(_nearest_weekday(date(year, 6, 19)))  # Juneteenth
    return frozenset(days | {d for d in _NYSE_SPECIAL_CLOSURES if d.year == year})


@lru_cache(maxsize=None)
def xetra_holidays(year: int) -> frozenset[date]:
    """Full-day Xetra / Frankfurt closures for ``year`` (no weekend substitution)."""
    easter = _easter_sunday(year)
    return frozenset(
        {
            date(year, 1, 1),
            easter - timedelta(days=2),  # Good Friday
            easter + timedelta(days=1),  # Easter Monday
            date(year, 5, 1),  # Labour Day
            date(year, 12, 24),
            date(year, 12, 25),
            date(year, 12, 26),
            date(year, 12, 31),
        }
    )


@lru_cache(maxsize=None)
def tsx_holidays(year: int) -> frozenset[date]:
    """Full-day Toronto Stock Exchange closures for ``year``."""
    christmas, boxing_day = _christmas_and_boxing_day(year)
    may_24 = date(year, 5, 24)
    days = {
        _substitute_if_weekend(date(year, 1, 1)),
        _easter_sunday(year) - timedelta(days=2),  # Good Friday
        may_24 - timedelta(days=may_24.weekday()),  # Victoria Day: Monday on or before 24 May
        _substitute_if_weekend(date(year, 7, 1)),  # Canada Day
        _nth_weekday_of_month(year, 8, _MON, 1),  # Civic Holiday
        _nth_weekday_of_month(year, 9, _MON, 1),  # Labour Day
        _nth_weekday_of_month(year, 10, _MON, 2),  # Thanksgiving
        christmas,
        boxing_day,
    }
    if year >= 2008:
        days.add(_nth_weekday_of_month(year, 2, _MON, 3))  # Family Day
    return frozenset(days)


_CALENDARS: dict[str, Callable[[int], frozenset[date]]] = {
    "L": uk_bank_holidays,
    "LSE": uk_bank_holidays,
    "UK": uk_bank_holidays,
    "N": nyse_holidays,
    "US": nyse_holidays,
    "NYSE": nyse_holidays,
    "NASDAQ": nyse_holidays,
    "DE": xetra_holidays,
    "F": xetra_holidays,
    "XETRA": xetra_holidays,
    "TO": tsx_holidays,
    "TSX": tsx_holidays,
    "CA": tsx_holidays,
}


def exchange_holidays(exchange: str | None, year: int) -> frozenset[date]:
    """Holidays for ``exchange`` in ``year``; the UK set when the exchange has no calendar."""
    calendar = _CALENDARS.get((exchange or "").strip().upper(), uk_bank_holidays)
    return calendar(year)


def business_days_between(start: date, end: date, exchange: str | None = None) -> list[date]:
    """Trading days on ``exchange`` in the inclusive range [start, end]."""
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in exchange_holidays(exchange, d.year):
            days.append(d)
        d += timedelta(days=1)
    return days
