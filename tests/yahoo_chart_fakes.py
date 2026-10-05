"""Fake ``yfinance.Ticker`` exposing only the chart-endpoint API.

``backend.common.yahoo_chart.chart_quote`` reads quotes via ``history()`` and
``get_history_metadata()`` rather than ``.info``. This fake deliberately has
no ``info`` attribute, so any regression back to ``quoteSummary`` fails loudly.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd


class FakeChartTicker:
    def __init__(
        self,
        metadata: Optional[Dict[str, Any]] = None,
        history: Optional[pd.DataFrame] = None,
        error: Optional[Exception] = None,
    ) -> None:
        self._metadata = metadata or {}
        self._history = history if history is not None else pd.DataFrame(columns=["Open", "Close"])
        self._error = error
        self.history_calls: list[Dict[str, Any]] = []

    def history(self, **kwargs: Any) -> pd.DataFrame:
        self.history_calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._history

    def get_history_metadata(self) -> Dict[str, Any]:
        return self._metadata
