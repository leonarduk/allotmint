"""UK bank holiday calculation for trading-calendar-aware gap detection.

No third-party holiday/market-calendar library is used here (none is a
dependency of this project); holidays are computed directly from the fixed
rules gov.uk publishes for England & Wales bank holidays, plus the one-off
holidays proclaimed for particular years. Other exchanges' calendars live in
:mod:`backend.utils.market_holidays`.
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


def _christmas_and_boxing_day(year: int) -> tuple[date, date]:
    """Christmas Day and Boxing Day for ``year`` after weekend substitution."""
    christmas = _substitute_if_weekend(date(year, 12, 25))
    boxing_day = _substitute_if_weekend(date(year, 12, 26))
    # If both fixed dates were pushed onto the same weekday (25th on Sat/Sun
    # pushes to the following Mon/Tue and 26th does likewise), they can
    # collide; nudge Boxing Day forward a day in that case.
    if boxing_day == christmas:
        boxing_day += timedelta(days=1)
    return christmas, boxing_day


# One-off changes to the standard England & Wales set, by year: standard dates
# that were moved away (removed) and the one-off or moved dates (added). Taken
# from the royal proclamations gov.uk lists for each year (#10961).
_UK_ONE_OFFS: dict[int, tuple[frozenset[date], frozenset[date]]] = {
    # VE Day 50th anniversary: early May holiday moved from 1 May to 8 May.
    1995: (frozenset({date(1995, 5, 1)}), frozenset({date(1995, 5, 8)})),
    # Millennium.
    1999: (frozenset(), frozenset({date(1999, 12, 31)})),
    # Golden Jubilee: spring holiday moved from 27 May to 4 June, plus 3 June.
    2002: (frozenset({date(2002, 5, 27)}), frozenset({date(2002, 6, 3), date(2002, 6, 4)})),
    # Royal wedding.
    2011: (frozenset(), frozenset({date(2011, 4, 29)})),
    # Diamond Jubilee: spring holiday moved from 28 May to 4 June, plus 5 June.
    2012: (frozenset({date(2012, 5, 28)}), frozenset({date(2012, 6, 4), date(2012, 6, 5)})),
    # VE Day 75th anniversary: early May holiday moved from 4 May to 8 May.
    2020: (frozenset({date(2020, 5, 4)}), frozenset({date(2020, 5, 8)})),
    # Platinum Jubilee: spring holiday moved from 30 May to 2 June, plus 3 June;
    # and the State Funeral of Queen Elizabeth II.
    2022: (
        frozenset({date(2022, 5, 30)}),
        frozenset({date(2022, 6, 2), date(2022, 6, 3), date(2022, 9, 19)}),
    ),
    # Coronation of King Charles III.
    2023: (frozenset(), frozenset({date(2023, 5, 8)})),
}


@lru_cache(maxsize=None)
def uk_bank_holidays(year: int) -> frozenset[date]:
    """Return England & Wales bank holidays for ``year``.

    Covers the standard fixed set: New Year's Day, Good Friday, Easter Monday,
    early May bank holiday, spring bank holiday, summer bank holiday,
    Christmas Day, and Boxing Day, with weekend substitution applied to the
    fixed-date holidays, plus the one-off holidays and moved dates in
    ``_UK_ONE_OFFS`` (jubilees, royal events, VE Day anniversaries).
    """
    moved_away, added = _UK_ONE_OFFS.get(year, (frozenset(), frozenset()))
    return (_standard_uk_bank_holidays(year) - moved_away) | added


def _standard_uk_bank_holidays(year: int) -> frozenset[date]:
    """The standard England & Wales set for ``year``, before one-off changes."""
    easter = _easter_sunday(year)
    good_friday = easter - timedelta(days=2)
    easter_monday = easter + timedelta(days=1)

    christmas, boxing_day = _christmas_and_boxing_day(year)
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
