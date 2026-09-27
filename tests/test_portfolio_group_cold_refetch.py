"""A stale ticker must not be re-fetched in a loop (#7877, #7912, #7990).

A cold ``/portfolio-group/all`` blew the frontend's 30s timeout because one
holding missing its latest close was live-fetched again and again within a
single request. Two fixes followed:

- PR #7881: ``_rolling_cache`` no longer rewrites the parquet when the fetch
  adds no new dates (a rewrite's new mtime cleared the meta LRUs and forced the
  next lookup to fetch again), and a Stooq timeout starts a cooldown, so an
  unreachable Stooq costs one timeout per window rather than one per fetch.
- #7898: page requests price holdings from the timeseries cache only; the
  background snapshot refresh does the live fetching.

These tests drive both paths end to end with Stooq timing out. The page build
must make no live calls at all. The background refresh is where the #7877
guarantees now matter: one Stooq HTTP attempt for the stale ticker, including
a second refresh within the cooldown, and no rewrite of its parquet. They
assert call counts, not wall-clock time.
"""

from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from backend.common import group_portfolio, portfolio_loader, portfolio_utils
from backend.config import config

TICKER = "COLDX"
EXCHANGE = "L"
FULL_TICKER = f"{TICKER}.{EXCHANGE}"
OWNER = "alice"


class _Counters:
    def __init__(self) -> None:
        self.stooq_http = 0
        self.yahoo = 0
        self.saves: list[str] = []


def _stale_history(cache) -> pd.DataFrame:
    """Daily closes ending one weekday before the window the cache wants."""
    _cutoff, window_end = cache._weekday_range(datetime.today().date() - timedelta(days=1), 60)
    dates = pd.bdate_range(end=window_end - timedelta(days=1), periods=400)
    assert window_end not in set(dates.date)
    return cache._ensure_schema(
        pd.DataFrame(
            {
                "Date": dates,
                "Open": 100.0,
                "High": 100.0,
                "Low": 100.0,
                "Close": 100.0,
                "Volume": 1,
                "Ticker": TICKER,
                "Source": "Yahoo",
            }
        )
    )


def _stub_portfolio(monkeypatch) -> None:
    """One group, one owner, one GBP holding in the stale ticker."""
    monkeypatch.setattr(
        group_portfolio,
        "list_groups",
        lambda: [{"slug": "all", "name": "At a glance", "members": [OWNER]}],
    )
    monkeypatch.setattr(
        portfolio_loader,
        "list_portfolios",
        lambda: [
            {
                "owner": OWNER,
                "accounts": [
                    {
                        "account_type": "ISA",
                        "currency": "GBP",
                        "holdings": [{"ticker": FULL_TICKER, "units": 10}],
                    }
                ],
            }
        ],
    )
    monkeypatch.setattr(group_portfolio, "load_approvals", lambda _owner: {})
    monkeypatch.setattr(group_portfolio, "load_user_config", lambda _owner: None)
    monkeypatch.setattr(group_portfolio.owner_portfolio, "build_owner_portfolio", lambda *_a, **_k: {})
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda _ticker: None)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT_TS", None)


def _stub_refresh(monkeypatch) -> None:
    """The background refresh sees only the stale ticker and writes no file."""
    monkeypatch.setattr(portfolio_utils, "list_all_unique_tickers", lambda: [FULL_TICKER])
    monkeypatch.setattr(portfolio_utils, "_PRICES_PATH", None)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT_TS", None)


def _stub_price_sources(monkeypatch, cache, history: pd.DataFrame) -> _Counters:
    """Yahoo returns only already-cached rows, Stooq times out, the rest are empty."""
    meta_mod = importlib.import_module("backend.timeseries.fetch_meta_timeseries")
    stooq_mod = importlib.import_module("backend.timeseries.fetch_stooq_timeseries")
    counters = _Counters()

    def fake_yahoo(ticker, exchange, start_date, end_date):
        # Like ISXF on a weekend: the provider has nothing newer than the cache.
        counters.yahoo += 1
        return history.tail(1).copy()

    def fake_stooq_get(url, *args, **kwargs):
        counters.stooq_http += 1
        raise requests.exceptions.Timeout("stooq unreachable")

    real_save = cache._save_parquet

    def counting_save(df, path):
        counters.saves.append(path)
        real_save(df, path)

    monkeypatch.setattr(meta_mod, "fetch_yahoo_timeseries_range", fake_yahoo)
    monkeypatch.setattr(meta_mod, "fetch_ft_df", lambda *_a, **_k: pd.DataFrame())
    monkeypatch.setattr(meta_mod, "is_valid_ticker", lambda _t, _e: True)
    monkeypatch.setattr(meta_mod.config, "alpha_vantage_enabled", False)
    monkeypatch.setattr(meta_mod, "fetch_stooq_timeseries_range", stooq_mod.fetch_stooq_timeseries_range)
    monkeypatch.setattr(stooq_mod, "is_valid_ticker", lambda _t, _e: True)
    monkeypatch.setattr(stooq_mod, "requests", SimpleNamespace(get=fake_stooq_get, exceptions=requests.exceptions))
    monkeypatch.setattr(cache, "fetch_meta_timeseries", meta_mod.fetch_meta_timeseries)
    monkeypatch.setattr(cache, "_save_parquet", counting_save)
    return counters


def _clear_meta_caches(cache) -> None:
    cache._load_meta_timeseries_cached.cache_clear()
    cache._memoized_range_cached.cache_clear()
    cache._CACHE_FILE_MTIMES.clear()


@pytest.fixture
def cold_cache(monkeypatch, tmp_path):
    """A live-mode meta cache under ``tmp_path`` holding one stale ticker."""
    cache = importlib.import_module("backend.timeseries.cache")
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr(config, "offline_mode", False)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    _clear_meta_caches(cache)

    history = _stale_history(cache)
    path = cache.meta_timeseries_cache_path(TICKER, EXCHANGE)
    cache._save_parquet(history, path)

    yield cache, history, path

    _clear_meta_caches(cache)


def test_cold_group_build_prices_stale_ticker_from_cache_without_fetching(monkeypatch, cold_cache):
    cache, history, path = cold_cache
    _stub_portfolio(monkeypatch)
    counters = _stub_price_sources(monkeypatch, cache, history)

    built = group_portfolio.build_group_portfolio("all")

    holding = built["accounts"][0]["holdings"][0]
    assert holding["price"] == pytest.approx(100.0)
    assert counters.yahoo == 0
    assert counters.stooq_http == 0
    assert counters.saves == []


def test_background_refresh_makes_one_stooq_attempt_for_stale_ticker(monkeypatch, cold_cache):
    cache, history, path = cold_cache
    _stub_refresh(monkeypatch)
    counters = _stub_price_sources(monkeypatch, cache, history)
    mtime_before = os.stat(path).st_mtime_ns

    portfolio_utils.refresh_snapshot_in_memory_from_timeseries()

    # The refresh reached the live fetch path and still priced the ticker from cache.
    assert counters.yahoo >= 1
    assert counters.stooq_http == 1
    assert counters.saves == []
    entry = portfolio_utils._PRICE_SNAPSHOT[FULL_TICKER]
    assert entry["last_price"] == pytest.approx(100.0)
    assert entry["last_price_date"] == history["Date"].iloc[-1].strftime("%Y-%m-%d")

    # A later refresh in the same process, after something else (e.g. another
    # ticker's refresh) has cleared the meta LRUs, fetches again but must not
    # hit Stooq again while the cooldown is running.
    _clear_meta_caches(cache)
    yahoo_after_first = counters.yahoo

    portfolio_utils.refresh_snapshot_in_memory_from_timeseries()

    assert counters.yahoo > yahoo_after_first
    assert counters.stooq_http == 1
    assert counters.saves == []
    assert os.stat(path).st_mtime_ns == mtime_before
