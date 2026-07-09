"""UK bank holiday calculation for trading-calendar-aware gap detection.

No third-party holiday/market-calendar library is used here (none is a
dependency of this project); holidays are computed directly from the fixed
rules gov.uk publishes for England & Wales bank holidays.
"""

from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def _easter_sunday(year: int) -> date:
    """Anonymous Gregorian algorithm for the date of Easter Sunday."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    ll = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ll) // 451
    month = (h + ll - 7 * m + 114) // 31
    day = ((h + ll - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _substitute_if_weekend(d: date) -> date:
    """Move a fixed-date holiday to the following Monday if it falls on a weekend."""
    if d.weekday() == 5:  # Saturday
        return d + timedelta(days=2)
    if d.weekday() == 6:  # Sunday
        return d + timedelta(days=1)
    return d


def _nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date:
    """The n-th occurrence (1-indexed) of ``weekday`` (Mon=0) in ``month``."""
    d = date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    d += timedelta(days=offset + 7 * (n - 1))
    return d


def _last_weekday_of_month(year: int, month: int, weekday: int) -> date:
    """The last occurrence of ``weekday`` (Mon=0) in ``month``."""
    if month == 12:
        d = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d = date(year, month + 1, 1) - timedelta(days=1)
    offset = (d.weekday() - weekday) % 7
    return d - timedelta(days=offset)


@lru_cache(maxsize=None)
def uk_bank_holidays(year: int) -> frozenset[date]:
    """Return England & Wales bank holidays for ``year``.

    Covers the standard fixed set: New Year's Day, Good Friday, Easter Monday,
    early May bank holiday, spring bank holiday, summer bank holiday,
    Christmas Day, and Boxing Day, with weekend substitution applied to the
    fixed-date holidays.
    """
    easter = _easter_sunday(year)
    good_friday = easter - timedelta(days=2)
    easter_monday = easter + timedelta(days=1)

    christmas = _substitute_if_weekend(date(year, 12, 25))
    boxing_day = _substitute_if_weekend(date(year, 12, 26))
    # If both fixed dates were pushed onto the same weekday (25th on Sat/Sun
    # pushes to the following Mon/Tue and 26th does likewise), they can
    # collide; nudge Boxing Day forward a day in that case.
    if boxing_day == christmas:
        boxing_day += timedelta(days=1)

    return frozenset(
        {
            _substitute_if_weekend(date(year, 1, 1)),
            good_friday,
            easter_monday,
            _nth_weekday_of_month(year, 5, 0, 1),  # early May bank holiday
            _last_weekday_of_month(year, 5, 0),  # spring bank holiday
            _last_weekday_of_month(year, 8, 0),  # summer bank holiday
            christmas,
            boxing_day,
        }
    )


def is_uk_business_day(d: date) -> bool:
    """Return True if ``d`` is a weekday and not a UK bank holiday."""
    return d.weekday() < 5 and d not in uk_bank_holidays(d.year)


def uk_business_days_between(start: date, end: date) -> list[date]:
    """Return all UK business days in the inclusive range [start, end]."""
    if start > end:
        return []
    days = []
    d = start
    while d <= end:
        if is_uk_business_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days
