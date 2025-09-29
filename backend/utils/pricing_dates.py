"""Utilities for consistent pricing/reporting date calculations."""

from __future__ import annotations

import datetime as dt
from functools import cached_property
from typing import Callable, Tuple

from backend.utils.timeseries_helpers import _nearest_weekday


class PricingDateCalculator:
    """Resolve commonly used pricing dates relative to ``today``.

    The calculator normalises weekend handling using
    :func:`backend.utils.timeseries_helpers._nearest_weekday` and exposes
    helpers for the most common anchors and lookback windows used across the
    pricing utilities.
    """

    def __init__(
        self,
        today: dt.date | None = None,
        *,
        weekday_func: Callable[[dt.date, bool], dt.date] | None = None,
        reporting_date: dt.date | None = None,
    ) -> None:
        self._weekday_func = weekday_func or _nearest_weekday
        self._explicit_reporting_date = (
            self.resolve_weekday(reporting_date, forward=False)
            if reporting_date is not None
            else None
        )
        if today is None and self._explicit_reporting_date is not None:
            today = self._explicit_reporting_date + dt.timedelta(days=1)
        self._today = today or dt.date.today()

    def resolve_weekday(self, candidate: dt.date, *, forward: bool) -> dt.date:
        """Normalise ``candidate`` to the nearest weekday using the resolver."""

        return self._weekday_func(candidate, forward)

    @property
    def today(self) -> dt.date:
        """Return the reference date used for calculations."""

        return self._today

    @cached_property
    def reporting_date(self) -> dt.date:
        """Return the primary reporting date (previous trading day)."""

        if self._explicit_reporting_date is not None:
            return self._explicit_reporting_date
        return self.resolve_weekday(self._today - dt.timedelta(days=1), forward=False)

    @cached_property
    def previous_pricing_date(self) -> dt.date:
        """Return the trading day preceding :attr:`reporting_date`."""

        return self.resolve_weekday(self.reporting_date - dt.timedelta(days=1), forward=False)

    def lookback_anchor(
        self,
        days: int,
        *,
        from_date: dt.date | None = None,
        forward: bool = False,
    ) -> dt.date:
        """Return the trading day ``days`` before ``from_date``.

        ``from_date`` defaults to :attr:`reporting_date`. Set ``forward`` to
        ``True`` when the anchor should move forward to the next weekday (used
        for ranges that end on ``today`` rather than the reporting date).
        """

        base = (from_date or self.reporting_date) - dt.timedelta(days=days)
        return self.resolve_weekday(base, forward=forward)

    def lookback_range(
        self,
        days: int,
        *,
        end: dt.date | None = None,
        forward_end: bool = False,
    ) -> Tuple[dt.date, dt.date]:
        """Return a ``(start, end)`` tuple spanning ``days`` backwards."""

        end_candidate = end or self.reporting_date
        resolved_end = self.resolve_weekday(end_candidate, forward=forward_end)
        start_candidate = resolved_end - dt.timedelta(days=days)
        start = self.resolve_weekday(start_candidate, forward=False)
        return start, resolved_end


__all__ = ["PricingDateCalculator"]
