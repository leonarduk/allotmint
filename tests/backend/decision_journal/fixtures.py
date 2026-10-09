"""Synthetic prices and entries shared by the decision-journal tests (#10481).

Tickers and figures are made up; nothing here comes from a real portfolio.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from backend.decision_journal.store import Expectation, ExpectationCheck, JournalEntry, Leg
from backend.timeseries.total_return import PRICE_RETURN_BASIS, total_return_closes

# ticker -> ({date: close}, {ex-date: dividend} or None for "no actions file")
SERIES: dict[str, tuple[dict[str, float], dict[str, float] | None]] = {
    "AAA.L": ({"2026-01-02": 100.0, "2026-04-01": 95.0, "2026-07-01": 90.0, "2026-12-31": 110.0}, {}),
    "BBB.L": ({"2026-01-02": 50.0, "2026-04-01": 52.0, "2026-07-01": 55.0, "2026-12-31": 50.0}, {"2026-04-01": 1.0}),
    # No actions file: price basis only.
    "CCC.L": ({"2026-01-02": 10.0, "2026-07-01": 11.0}, None),
}


def _dividends(divs: dict[str, float]) -> pd.Series:
    return pd.Series(list(divs.values()), dtype=float, index=pd.to_datetime(list(divs)))


def fake_series(ticker: str, start: date, end: date) -> tuple[pd.Series, str]:
    """Stand-in for ``load_return_series``: the fixture closes through the real total-return path."""
    closes_map, divs = SERIES.get(ticker, ({}, None))
    closes = pd.Series(list(closes_map.values()), dtype=float, index=pd.to_datetime(list(closes_map)))
    closes = closes[(closes.index >= pd.Timestamp(start)) & (closes.index <= pd.Timestamp(end))]
    if divs is None:
        return closes, PRICE_RETURN_BASIS
    symbol, exchange = ticker.split(".")
    return total_return_closes(closes, symbol, exchange, load_dividends=lambda _s, _e: _dividends(divs))


def sell_entry(**overrides) -> JournalEntry:
    """Sold £10,000 of AAA on 2 Jan 2026 and put the proceeds into BBB."""
    fields = {
        "id": "dj-sell-aaa",
        "date": date(2026, 1, 2),
        "kind": "trade",
        "source_ref": "alex:isa:7",
        "amount_gbp": 10_000.0,
        "legs": [
            Leg(role="chosen", label="Proceeds to BBB", ticker="BBB.L"),
            Leg(role="alternative", label="Keep holding AAA", ticker="AAA.L"),
            Leg(role="alternative", label="Hold cash", ticker=None),
        ],
        "expectation": Expectation(
            text="BBB beats AAA over 6 months",
            check=ExpectationCheck(leg="Proceeds to BBB", outperforms="Keep holding AAA"),
        ),
        "review_due": [date(2026, 7, 2), date(2027, 1, 2)],
    }
    return JournalEntry(**{**fields, **overrides})
