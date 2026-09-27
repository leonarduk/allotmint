"""A cold group-portfolio build must not re-fetch a stale ticker in a loop (#7877, #7912).

A cold ``/portfolio-group/all`` blew the frontend's 30s timeout because one
holding missing its latest close was live-fetched again and again within a
single request. PR #7881 fixed two causes, each with its own unit test:

- ``_rolling_cache`` no longer rewrites the parquet when the fetch adds no new
  dates, so the rewrite's new mtime no longer clears the meta LRUs and forces
  the next lookup to fetch again.
- A Stooq timeout starts a cooldown, so an unreachable Stooq costs one timeout
  per window rather than one per fetch.

This test drives ``build_group_portfolio`` end to end with Stooq timing out and
checks the user-facing symptom: one Stooq HTTP attempt for the stale ticker,
including a second build within the cooldown, and no rewrite of its parquet.
It asserts call counts, not wall-clock time.
"""

from __future__ import annotations

import importlib
import os
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
import requests

from backend.common import group_portfolio, holding_utils, portfolio_loader, portfolio_utils
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


def _stub_price_sources(monkeypatch, cache, history: pd.DataFrame) -> _Counters:
    """Yahoo returns only already-cached rows, Stooq times out, the rest are empty.

    Stubs are installed on the modules the live ``cache`` actually calls into,
    since other tests re-import ``backend.timeseries.cache``.
    """
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
    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", cache.load_meta_timeseries_range)
    _clear_meta_caches(cache)

    history = _stale_history(cache)
    path = cache.meta_timeseries_cache_path(TICKER, EXCHANGE)
    cache._save_parquet(history, path)

    yield cache, history, path

    _clear_meta_caches(cache)


def test_cold_group_build_makes_one_stooq_attempt_for_stale_ticker(monkeypatch, cold_cache):
    cache, history, path = cold_cache
    _stub_portfolio(monkeypatch)
    counters = _stub_price_sources(monkeypatch, cache, history)
    mtime_before = os.stat(path).st_mtime_ns

    first = group_portfolio.build_group_portfolio("all")

    # The build did reach the live fetch path and priced the holding from cache.
    assert counters.yahoo >= 1
    holding = first["accounts"][0]["holdings"][0]
    assert holding["price"] == pytest.approx(100.0)
    assert counters.stooq_http == 1
    assert counters.saves == []

    # A later request in the same process, after something else (e.g. another
    # ticker's refresh) has cleared the meta LRUs, fetches again but must not
    # hit Stooq again while the cooldown is running.
    _clear_meta_caches(cache)
    yahoo_after_first = counters.yahoo

    group_portfolio.build_group_portfolio("all")

    assert counters.yahoo > yahoo_after_first
    assert counters.stooq_http == 1
    assert counters.saves == []
    assert os.stat(path).st_mtime_ns == mtime_before
