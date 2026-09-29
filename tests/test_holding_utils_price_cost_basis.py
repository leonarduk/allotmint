import datetime as dt

import pandas as pd

from backend.common import holding_utils
from backend.common.constants import (
    ACQUIRED_DATE,
    COST_BASIS_GBP,
    TICKER,
    UNITS,
)


def test_get_price_for_date_scaled_cash():
    d = dt.date(2024, 1, 1)
    price, src = holding_utils._get_price_for_date_scaled("CASH", "L", d)
    assert price == 1.0
    assert src is None


def test_get_price_for_date_scaled_empty_data(monkeypatch):
    def fake_loader(*args, **kwargs):
        return pd.DataFrame()

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    d = dt.date(2024, 1, 1)
    price, src = holding_utils._get_price_for_date_scaled("AAA", "L", d)
    assert price is None
    assert src is None


def test_get_price_for_date_scaled_nan_close(monkeypatch):
    """A NaN close (e.g. a gap-filled row for a date outside the cache) must not leak out."""

    def fake_loader(*args, **kwargs):
        return pd.DataFrame({"Close_gbp": [float("nan")], "Source": ["Yahoo"]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(holding_utils, "apply_scaling", lambda df, scale: df)
    d = dt.date(2024, 1, 1)
    price, src = holding_utils._get_price_for_date_scaled("AAA", "L", d)
    assert price is None
    assert src is None


def test_get_price_for_date_scaled_memoizes_only_inside_cache_only(monkeypatch):
    """#8211: _get_price_for_date_scaled should skip repeat load_meta_timeseries_range
    calls for the same (ticker, exchange, d, field) inside cache_only(), but never
    memoize outside it -- a live/background-refresh read must always see fresh data."""
    holding_utils._get_price_for_date_scaled_cache_only.cache_clear()
    d = dt.date(2024, 1, 1)
    calls = []

    def fake_loader(*args, **kwargs):
        calls.append(1)
        return pd.DataFrame({"Close_gbp": [123.45], "Source": ["Yahoo"]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(holding_utils, "apply_scaling", lambda df, scale: df)

    from backend.timeseries.cache import cache_only

    with cache_only():
        assert holding_utils._get_price_for_date_scaled("AAA", "L", d) == (123.45, "Yahoo")
        assert holding_utils._get_price_for_date_scaled("AAA", "L", d) == (123.45, "Yahoo")
    assert len(calls) == 1, "second cache-only call must hit the memo, not load_meta_timeseries_range again"

    assert holding_utils._get_price_for_date_scaled("AAA", "L", d) == (123.45, "Yahoo")
    assert len(calls) == 2, "a call outside cache_only() must never be served from the cache-only memo"


def test_get_price_for_date_scaled_cache_only_memo_cleared_by_meta_cache_invalidation(monkeypatch):
    """#8211: the new memo must be registered with cache.py's invalidation
    hook so a stale underlying file still busts it, same as the module's own
    meta LRUs."""
    holding_utils._get_price_for_date_scaled_cache_only.cache_clear()
    d = dt.date(2024, 1, 1)
    calls = []

    def fake_loader(*args, **kwargs):
        calls.append(1)
        return pd.DataFrame({"Close_gbp": [float(len(calls))], "Source": ["Yahoo"]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 1.0)
    monkeypatch.setattr(holding_utils, "apply_scaling", lambda df, scale: df)

    from backend.timeseries import cache as cache_mod

    with cache_mod.cache_only():
        first, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d)
        assert len(calls) == 1

        for clear_fn in cache_mod._EXTRA_META_CACHE_CLEARERS:
            clear_fn()

        second, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d)
        assert len(calls) == 2, "clearing the registered clearer must force a fresh lookup"
        assert second != first


def test_get_effective_cost_basis_gbp_booked_cost(monkeypatch):
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 1.0)
    holding = {TICKER: "AAA.L", UNITS: 10, COST_BASIS_GBP: 123.45}
    assert holding_utils.get_effective_cost_basis_gbp(holding, {}) == 123.45


def test_get_effective_cost_basis_gbp_updates_booked_cost_when_scaled(monkeypatch):
    from backend.common import instrument_api

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".")[0], "L"),
    )
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 0.5)

    holding = {TICKER: "ABC.L", UNITS: 10, COST_BASIS_GBP: 123.45}

    assert holding_utils.get_effective_cost_basis_gbp(holding, {}) == 61.73
    assert holding[COST_BASIS_GBP] == 61.73


def test_get_effective_cost_basis_gbp_derived(monkeypatch):
    def fake_derived(ticker, exchange, acq, cache):
        return 2.0

    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", fake_derived)
    from backend.common import instrument_api

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".")[0], "L"),
    )
    holding = {TICKER: "BBB.L", UNITS: 10, ACQUIRED_DATE: "2024-01-01"}
    assert holding_utils.get_effective_cost_basis_gbp(holding, {}) == 20.0


def test_get_effective_cost_basis_gbp_cache_fallback(monkeypatch):
    def fake_derived(ticker, exchange, acq, cache):
        return None

    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", fake_derived)
    from backend.common import instrument_api

    monkeypatch.setattr(
        instrument_api,
        "_resolve_full_ticker",
        lambda full, cache: (full.split(".")[0], "L"),
    )
    price_cache = {"CCC.L": 5.0}
    holding = {TICKER: "CCC.L", UNITS: 3, ACQUIRED_DATE: "2024-01-01"}
    assert holding_utils.get_effective_cost_basis_gbp(holding, price_cache) == 15.0
