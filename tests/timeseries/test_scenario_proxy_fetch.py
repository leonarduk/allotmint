"""The scenario proxy ``SPY.N`` is fetchable end to end (#9489).

``is_valid_ticker`` gates both ``fetch_meta_timeseries`` and
``fetch_yahoo_timeseries_range``; before ``data/instruments/N/SPY.json``
existed it skipped every proxy fetch, so ``load_meta_timeseries_range``
returned no rows and holdings without their own history never followed the
proxy. These tests run the real validator against the bundled metadata and
stub only the network boundary (``fetch_yahoo_history``) and FX rates.
"""

from __future__ import annotations

import datetime as dt
import importlib
from pathlib import Path

import pandas as pd
import pytest

from backend.common import instruments
from backend.config import config
from backend.timeseries import ticker_validator
from backend.utils.scenario_tester import apply_historical_event_portfolio

_BUNDLED_INSTRUMENTS = Path(__file__).resolve().parents[2] / "data" / "instruments"
_USD_GBP = 0.5


def _spy_prices(full_ticker: str, start: dt.date, end: dt.date) -> pd.DataFrame:
    """Every weekday in the window; the close falls 1.0 per day from 100."""
    dates = pd.bdate_range(start, end)
    closes = [100.0 - i for i in range(len(dates))]
    return pd.DataFrame(
        {
            "Date": dates.date,
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": 1,
            "Ticker": full_ticker,
            "Source": "Yahoo",
        }
    )


def _clear_caches(cache) -> None:
    cache._load_meta_timeseries_cached.cache_clear()
    cache._memoized_range_cached.cache_clear()
    cache._CACHE_FILE_MTIMES.clear()
    instruments.get_instrument_meta.cache_clear()
    ticker_validator.is_valid_ticker.cache_clear()


@pytest.fixture
def live_pipeline(monkeypatch, tmp_path):
    """Real cache and validator over bundled metadata; Yahoo's HTTP call stubbed.

    Yields the list of full tickers Yahoo was asked for.
    """
    cache = importlib.import_module("backend.timeseries.cache")
    meta_mod = importlib.import_module("backend.timeseries.fetch_meta_timeseries")
    yahoo_mod = importlib.import_module("backend.timeseries.fetch_yahoo_timeseries")
    yahoo_calls: list[str] = []

    def fake_history(full_ticker, start, end):
        yahoo_calls.append(full_ticker)
        return _spy_prices(full_ticker, start, end), pd.DataFrame()

    def fake_fx(base, quote, start, end):
        dates = pd.bdate_range(start, end).date
        return pd.DataFrame({"Date": dates, "Rate": [_USD_GBP] * len(dates)})

    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", _BUNDLED_INSTRUMENTS)
    monkeypatch.delenv(instruments.METADATA_BUCKET_ENV, raising=False)
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(config, "offline_mode", False)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    monkeypatch.setattr(cache, "fetch_meta_timeseries", meta_mod.fetch_meta_timeseries)
    monkeypatch.setattr(cache, "fetch_fx_rate_range", fake_fx)
    monkeypatch.setattr(meta_mod, "fetch_yahoo_timeseries_range", yahoo_mod.fetch_yahoo_timeseries_range)
    monkeypatch.setattr(meta_mod, "fetch_stooq_timeseries_range", lambda *_a, **_k: pd.DataFrame())
    monkeypatch.setattr(meta_mod, "fetch_ft_df", lambda *_a, **_k: pd.DataFrame())
    monkeypatch.setattr(meta_mod.config, "alpha_vantage_enabled", False)
    monkeypatch.setattr(yahoo_mod, "fetch_yahoo_history", fake_history)
    monkeypatch.setattr(yahoo_mod, "record_corporate_actions", lambda *_a, **_k: None)
    _clear_caches(cache)

    yield cache, yahoo_calls

    _clear_caches(cache)


def test_spy_proxy_range_returns_rows(live_pipeline):
    cache, yahoo_calls = live_pipeline

    df = cache.load_meta_timeseries_range("SPY", "N", dt.date(2020, 3, 16), dt.date(2020, 4, 15))

    assert len(df) == len(pd.bdate_range("2020-03-16", "2020-04-15"))
    assert df["Close_gbp"].iloc[0] == pytest.approx(100.0 * _USD_GBP)
    assert yahoo_calls == ["SPY"]


def test_junk_ticker_is_still_skipped(live_pipeline):
    cache, yahoo_calls = live_pipeline

    assert not ticker_validator.is_valid_ticker("ZZJUNK", "N")
    df = cache.load_meta_timeseries_range("ZZJUNK", "N", dt.date(2020, 3, 16), dt.date(2020, 4, 15))

    assert df.empty
    assert yahoo_calls == []


def test_holding_without_history_follows_spy_proxy(live_pipeline):
    """A holding with no 2008 prices takes the SPY.N return, not the coverage fallback."""
    _cache, yahoo_calls = live_pipeline
    event_date = dt.date(2008, 9, 15)
    portfolio = {
        "total_value_estimate_gbp": 1000.0,
        "accounts": [{"holdings": [{"ticker": "NOHIST.L", "market_value_gbp": 1000.0}]}],
    }

    result = apply_historical_event_portfolio(
        portfolio, {"date": event_date.isoformat(), "proxy_index": "SPY.N"}, horizons={"1m": 30}
    )

    # Closes fall 1.0 per weekday from 100 at the fetch window's first weekday.
    weekdays = pd.bdate_range(event_date - dt.timedelta(days=7), event_date + dt.timedelta(days=37)).date
    base = 100.0 - [i for i, d in enumerate(weekdays) if d < event_date][-1]
    target = 100.0 - next(i for i, d in enumerate(weekdays) if d >= event_date + dt.timedelta(days=30))
    expected_delta = 1000.0 * (target - base) / base

    assert result["1m"]["coverage_pct"] == 100.0
    assert result["1m"]["delta_gbp"] == pytest.approx(expected_delta, abs=0.01)
    assert result["1m"]["price_return_tickers"] == ["SPY.N"]
    assert yahoo_calls == ["SPY"]
