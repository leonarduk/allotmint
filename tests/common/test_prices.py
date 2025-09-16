"""Unit tests for :mod:`backend.common.prices`."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Dict, List

import pandas as pd
import pytest

from unittest.mock import Mock

from backend.common import prices


def test_close_on_returns_value_from_timeseries(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should read the GBP close from cached timeseries data."""

    queried: Dict[str, List] = {}
    sample_date = date(2024, 1, 2)
    frame = pd.DataFrame({"close_gbp": [101.23], "close": [99.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)

    def fake_load(sym: str, exch: str, start_date: date, end_date: date) -> pd.DataFrame:
        queried["args"] = [sym, exch, start_date, end_date]
        return frame

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load)

    result = prices._close_on("ABC", "L", sample_date)

    assert result == pytest.approx(101.23)
    assert queried["args"] == ["ABC", "L", sample_date, sample_date]


def test_get_price_snapshot_uses_latest_and_live(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "ABC.L"
    now = datetime.now(UTC)
    yday = date.today() - timedelta(days=1)
    seven_day = yday - timedelta(days=7)
    thirty_day = yday - timedelta(days=30)

    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: 118.5})
    monkeypatch.setattr(
        prices, "load_live_prices", lambda tickers: {ticker.upper(): {"price": 120.5, "timestamp": now}}
    )
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: ("ABC", "L"))

    requested_dates: List[date] = []
    price_lookup = {seven_day: 100.0, thirty_day: 90.0}

    def fake_close_on(sym: str, exch: str, requested_date: date) -> float:
        requested_dates.append(requested_date)
        return price_lookup[requested_date]

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot([ticker])
    info = snapshot[ticker]

    assert info["last_price"] == pytest.approx(120.5)
    assert info["last_price_date"] == yday.isoformat()
    assert info["last_price_time"] == now.isoformat().replace("+00:00", "Z")
    assert info["is_stale"] is False
    assert info["change_7d_pct"] == pytest.approx((120.5 / 100.0 - 1.0) * 100.0)
    assert info["change_30d_pct"] == pytest.approx((120.5 / 90.0 - 1.0) * 100.0)
    assert requested_dates == [seven_day, thirty_day]

    requested_dates.clear()
    old_timestamp = now - timedelta(minutes=20)
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda tickers: {ticker.upper(): {"price": 120.5, "timestamp": old_timestamp}},
    )

    stale_snapshot = prices.get_price_snapshot([ticker])
    stale_info = stale_snapshot[ticker]

    assert stale_info["last_price"] == pytest.approx(120.5)
    assert stale_info["last_price_time"] == old_timestamp.isoformat().replace("+00:00", "Z")
    assert stale_info["is_stale"] is True
    assert stale_info["change_7d_pct"] == pytest.approx((120.5 / 100.0 - 1.0) * 100.0)
    assert stale_info["change_30d_pct"] == pytest.approx((120.5 / 90.0 - 1.0) * 100.0)
    assert requested_dates == [seven_day, thirty_day]


def test_get_price_snapshot_defaults_to_cached_close(monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "XYZ.L"
    base = ticker.split(".", 1)[0]
    yday = date.today() - timedelta(days=1)
    seven_day = yday - timedelta(days=7)
    thirty_day = yday - timedelta(days=30)

    monkeypatch.setattr(prices, "_load_latest_prices", lambda tickers: {ticker: 99.5})
    monkeypatch.setattr(prices, "load_live_prices", lambda tickers: {})
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: None)

    requested: List[tuple[str, str, date]] = []

    def fake_close_on(sym: str, exch: str, requested_date: date) -> float | None:
        requested.append((sym, exch, requested_date))
        if requested_date == seven_day:
            return 88.0
        if requested_date == thirty_day:
            return None
        raise AssertionError(f"Unexpected date requested: {requested_date}")

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot([ticker])
    info = snapshot[ticker]

    assert info["last_price"] == pytest.approx(99.5)
    assert info["last_price_date"] == yday.isoformat()
    assert info["last_price_time"] is None
    assert info["is_stale"] is True
    assert info["change_7d_pct"] == pytest.approx((99.5 / 88.0 - 1.0) * 100.0)
    assert info["change_30d_pct"] is None
    assert requested == [
        (base, "L", seven_day),
        (base, "L", thirty_day),
    ]


def test_build_securities_from_portfolios(monkeypatch: pytest.MonkeyPatch) -> None:
    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "abc", "name": "Alpha"},
                        {"ticker": "DEF"},
                        {"ticker": ""},
                        {"ticker": None},
                    ]
                }
            ]
        },
        {"accounts": []},
    ]
    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)

    result = prices._build_securities_from_portfolios()

    assert result == {
        "ABC": {"ticker": "ABC", "name": "Alpha"},
        "DEF": {"ticker": "DEF", "name": "DEF"},
    }


def test_refresh_prices_writes_json_and_updates_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    ticker = "XYZ.L"
    snapshot = {
        ticker: {
            "last_price": 145.0,
            "change_7d_pct": 3.2,
            "change_30d_pct": 5.4,
            "last_price_date": "2024-04-01",
            "last_price_time": None,
            "is_stale": True,
        }
    }

    monkeypatch.setattr(prices, "list_all_unique_tickers", lambda: [ticker])

    def fake_get_price_snapshot(tickers):
        assert tickers == [ticker]
        return snapshot

    monkeypatch.setattr(prices, "get_price_snapshot", fake_get_price_snapshot)
    refresh_mock = Mock()
    alerts_mock = Mock()
    monkeypatch.setattr(prices, "refresh_snapshot_in_memory", refresh_mock)
    monkeypatch.setattr(prices, "check_price_alerts", alerts_mock)

    output_path = tmp_path / "prices.json"
    monkeypatch.setattr(prices.config, "prices_json", output_path)
    monkeypatch.setattr(prices, "_price_cache", {})

    result = prices.refresh_prices()

    assert json.loads(output_path.read_text()) == snapshot
    assert result["tickers"] == [ticker]
    assert result["snapshot"] == snapshot
    assert result["timestamp"].endswith("Z")
    assert prices._price_cache == {ticker.upper(): snapshot[ticker]["last_price"]}
    refresh_mock.assert_called_once_with(snapshot)
    alerts_mock.assert_called_once_with()
