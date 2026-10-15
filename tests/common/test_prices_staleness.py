"""Live-quote staleness in the price snapshot across market hours (#10929).

The scheduled price refresh runs at 00:00 UTC, after the close. Its live
quotes are then the previous session's last trade, so the plain 15-minute
rule flagged every entry stale. A quote from the latest completed session is
fresh once its market has closed; the 15-minute rule still applies while the
market is open (#8595).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Optional

import pytest

from backend.common import holding_utils, live_prices, prices

TICKER = "3IN.L"
LAST_TRADE = datetime(2026, 10, 14, 15, 35, tzinfo=UTC)  # Wednesday's last trade


def _freeze(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    """Pin ``prices``' clock (``date.today`` and ``datetime.now``) to ``now``."""

    class _FrozenDate(date):
        @classmethod
        def today(cls) -> date:
            return now.date()

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None) -> datetime:
            return now if tz is None else now.astimezone(tz)

    monkeypatch.setattr(prices, "date", _FrozenDate)
    monkeypatch.setattr(prices, "datetime", _FrozenDatetime)


def _snapshot_entry(
    monkeypatch: pytest.MonkeyPatch,
    now: datetime,
    ts: datetime,
    market_state: Optional[str],
) -> dict:
    _freeze(monkeypatch, now)
    monkeypatch.setattr(prices, "_load_latest_closes", lambda tickers: {TICKER: (3.9, ts.date())})
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda tickers: {TICKER: {"price": 3.95, "timestamp": ts, "market_state": market_state}},
    )
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("3IN", "L"))
    monkeypatch.setattr(prices, "_close_on", lambda *args, **kwargs: None)
    return prices.get_price_snapshot([TICKER])[TICKER]


def test_intraday_quote_older_than_15_minutes_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 10, 15, 11, 0, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, now - timedelta(minutes=20), "REGULAR")
    assert entry["is_stale"] is True


def test_intraday_quote_within_15_minutes_is_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 10, 15, 11, 0, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, now - timedelta(minutes=5), "REGULAR")
    assert entry["is_stale"] is False


def test_intraday_quote_from_previous_session_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    # Market open again, but the quote is still yesterday's last trade.
    now = datetime(2026, 10, 15, 11, 0, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, LAST_TRADE, "REGULAR")
    assert entry["is_stale"] is True


@pytest.mark.parametrize("state", ["POST", "CLOSED"])
def test_after_close_same_day_quote_is_fresh(monkeypatch: pytest.MonkeyPatch, state: str) -> None:
    now = datetime(2026, 10, 15, 18, 0, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, datetime(2026, 10, 15, 15, 35, tzinfo=UTC), state)
    assert entry["is_stale"] is False


def test_overnight_refresh_quote_from_latest_session_is_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    # The #10929 repro: refreshed 2026-10-15 05:59Z, last trade 2026-10-14 15:35Z.
    now = datetime(2026, 10, 15, 5, 59, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, LAST_TRADE, "CLOSED")
    assert entry["is_stale"] is False
    assert entry["last_price_date"] == "2026-10-14"
    assert entry["last_price_time"] == "2026-10-14T15:35:00Z"
    # The holding inherits the snapshot's freshness.
    assert holding_utils._snapshot_is_stale(entry, date(2026, 10, 14)) is False


def test_pre_market_quote_from_latest_session_is_fresh(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 10, 15, 7, 30, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, LAST_TRADE, "PRE")
    assert entry["is_stale"] is False


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 10, 17, 10, 0, tzinfo=UTC),  # Saturday
        datetime(2026, 10, 18, 22, 0, tzinfo=UTC),  # Sunday
        datetime(2026, 10, 19, 0, 0, tzinfo=UTC),  # Monday's scheduled run, before the open
    ],
)
def test_weekend_quote_from_friday_session_is_fresh(monkeypatch: pytest.MonkeyPatch, now: datetime) -> None:
    friday_trade = datetime(2026, 10, 16, 15, 35, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, friday_trade, "CLOSED")
    assert entry["is_stale"] is False
    assert entry["last_price_date"] == "2026-10-16"


def test_closed_market_quote_older_than_latest_session_is_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    # Market closed, but the quote predates the latest completed session (no
    # trade on 2026-10-14), so it is not that session's price (#8595).
    now = datetime(2026, 10, 15, 5, 59, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, datetime(2026, 10, 13, 15, 35, tzinfo=UTC), "CLOSED")
    assert entry["is_stale"] is True


def test_unknown_market_state_keeps_15_minute_rule(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 10, 15, 5, 59, tzinfo=UTC)
    entry = _snapshot_entry(monkeypatch, now, LAST_TRADE, None)
    assert entry["is_stale"] is True


@pytest.mark.parametrize("state", [0, "", "  "])
def test_non_string_or_blank_market_state_keeps_15_minute_rule(state: object) -> None:
    now = datetime(2026, 10, 15, 5, 59, tzinfo=UTC)
    assert prices._live_quote_is_stale(LAST_TRADE, state, now, date(2026, 10, 14)) is True  # type: ignore[arg-type]


def test_missing_timestamp_is_stale() -> None:
    now = datetime(2026, 10, 15, 5, 59, tzinfo=UTC)
    assert prices._live_quote_is_stale(None, "CLOSED", now, date(2026, 10, 14)) is True


def test_load_live_prices_passes_market_state_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        live_prices,
        "load_live_quotes",
        lambda tickers: {TICKER: {"price_gbp": 3.95, "timestamp": LAST_TRADE, "market_state": "CLOSED"}},
    )
    assert holding_utils.load_live_prices([TICKER]) == {
        TICKER: {"price": 3.95, "timestamp": LAST_TRADE, "market_state": "CLOSED"}
    }
