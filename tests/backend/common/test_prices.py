"""Tests for :mod:`backend.common.prices`."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Dict, List, Tuple

import pandas as pd
import pytest

from backend.common import prices


def test_close_on_falls_back_to_close_column(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should use the first available close column."""

    sample_date = date(2024, 5, 6)
    frame = pd.DataFrame({"Close": [99.25]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)

    captured: List[Tuple[str, str, date, date]] = []

    def fake_load(sym: str, exch: str, start_date: date, end_date: date):
        captured.append((sym, exch, start_date, end_date))
        return frame

    monkeypatch.setattr(prices, "load_meta_timeseries_range", fake_load)

    result = prices._close_on("XYZ", "L", sample_date)

    assert result == pytest.approx(99.25)
    assert captured == [("XYZ", "L", sample_date, sample_date)]


def test_close_on_returns_none_when_no_price_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_close_on`` should return ``None`` if no recognised columns exist."""

    sample_date = date(2024, 5, 7)
    frame = pd.DataFrame({"open": [10.0], "high": [11.0]})

    monkeypatch.setattr(prices, "_nearest_weekday", lambda d, forward=False: sample_date)
    monkeypatch.setattr(
        prices,
        "load_meta_timeseries_range",
        lambda sym, exch, start_date, end_date: frame,
    )

    assert prices._close_on("ABC", "N", sample_date) is None


def test_get_price_snapshot_handles_stale_and_missing_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_price_snapshot`` should correctly combine live and cached data."""

    tickers = ["ABC.L", "DEF.N", "GHI.L"]
    now = datetime.now(UTC)
    stale_ts = now - timedelta(minutes=30)
    latest = {"ABC.L": 100.0, "DEF.N": 55.0, "GHI.L": 40.0}

    monkeypatch.setattr(prices, "_load_latest_prices", lambda requested: latest)
    monkeypatch.setattr(
        prices,
        "load_live_prices",
        lambda requested: {
            "ABC.L": {"price": 101.0, "timestamp": now},
            "DEF.N": {"price": 55.0, "timestamp": stale_ts},
        },
    )

    mapping = {"ABC.L": ("ABC", "L"), "DEF.N": ("DEF", "N"), "GHI.L": ("GHI", "L")}
    monkeypatch.setattr(prices.instrument_api, "_resolve_full_ticker", lambda full, latest: mapping.get(full))

    yday = date.today() - timedelta(days=1)
    seven_day = yday - timedelta(days=7)
    thirty_day = yday - timedelta(days=30)

    close_lookup: Dict[Tuple[str, str, date], float | None] = {
        ("ABC", "L", seven_day): 95.0,
        ("ABC", "L", thirty_day): 90.0,
        ("DEF", "N", seven_day): None,
        ("DEF", "N", thirty_day): 50.0,
        ("GHI", "L", seven_day): 39.0,
        ("GHI", "L", thirty_day): 38.0,
    }

    requested: List[Tuple[str, str, date]] = []

    def fake_close_on(sym: str, exch: str, requested_date: date):
        requested.append((sym, exch, requested_date))
        return close_lookup.get((sym, exch, requested_date))

    monkeypatch.setattr(prices, "_close_on", fake_close_on)

    snapshot = prices.get_price_snapshot(tickers)

    info_abc = snapshot["ABC.L"]
    assert info_abc["last_price"] == pytest.approx(101.0)
    assert info_abc["is_stale"] is False
    assert info_abc["last_price_time"] == now.isoformat().replace("+00:00", "Z")
    assert info_abc["last_price_date"] == yday.isoformat()
    assert info_abc["change_7d_pct"] == pytest.approx((101.0 / 95.0 - 1.0) * 100.0)
    assert info_abc["change_30d_pct"] == pytest.approx((101.0 / 90.0 - 1.0) * 100.0)

    info_def = snapshot["DEF.N"]
    assert info_def["last_price"] == pytest.approx(55.0)
    assert info_def["is_stale"] is True
    assert info_def["last_price_time"] == stale_ts.isoformat().replace("+00:00", "Z")
    assert info_def["change_7d_pct"] is None
    assert info_def["change_30d_pct"] == pytest.approx((55.0 / 50.0 - 1.0) * 100.0)

    info_ghi = snapshot["GHI.L"]
    assert info_ghi["last_price"] == pytest.approx(40.0)
    assert info_ghi["is_stale"] is True
    assert info_ghi["last_price_time"] is None
    assert info_ghi["change_7d_pct"] == pytest.approx((40.0 / 39.0 - 1.0) * 100.0)
    assert info_ghi["change_30d_pct"] == pytest.approx((40.0 / 38.0 - 1.0) * 100.0)

    assert requested == [
        ("ABC", "L", seven_day),
        ("ABC", "L", thirty_day),
        ("DEF", "N", seven_day),
        ("DEF", "N", thirty_day),
        ("GHI", "L", seven_day),
        ("GHI", "L", thirty_day),
    ]


def test_build_securities_and_get_security_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    """Security metadata should be derived from current portfolios."""

    portfolios = [
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "abc", "name": "Alpha"},
                        {"ticker": "def"},
                        {"ticker": ""},
                        {},
                    ]
                }
            ]
        },
        {
            "accounts": [
                {
                    "holdings": [
                        {"ticker": "GHI", "name": "Gamma"},
                        {"ticker": None},
                    ]
                }
            ]
        },
    ]

    monkeypatch.setattr(prices, "list_portfolios", lambda: portfolios)

    securities = prices._build_securities_from_portfolios()

    assert securities == {
        "ABC": {"ticker": "ABC", "name": "Alpha"},
        "DEF": {"ticker": "DEF", "name": "DEF"},
        "GHI": {"ticker": "GHI", "name": "Gamma"},
    }

    assert prices.get_security_meta("abc") == {"ticker": "ABC", "name": "Alpha"}
    assert prices.get_security_meta("DEF") == {"ticker": "DEF", "name": "DEF"}
    assert prices.get_security_meta("missing") is None
