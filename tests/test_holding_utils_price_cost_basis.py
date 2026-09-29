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
    holding_utils._load_unscaled_price_for_date_cache_only.cache_clear()
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
    holding_utils._load_unscaled_price_for_date_cache_only.cache_clear()
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


def test_get_price_for_date_scaled_never_memoizes_a_missing_result(monkeypatch):
    """#8232 review / test_reports_cache_only.py: a missing day must never be
    memoized, even inside cache_only() -- that's exactly the case where
    load_meta_timeseries_range's refresh_queue.enqueue side effect (#7917)
    matters, and caching the miss would silently suppress it thereafter."""
    holding_utils._load_unscaled_price_for_date_cache_only.cache_clear()
    d = dt.date(2024, 1, 1)
    calls = []

    def fake_loader(*args, **kwargs):
        calls.append(1)
        return pd.DataFrame()

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 1.0)

    from backend.timeseries.cache import cache_only

    with cache_only():
        assert holding_utils._get_price_for_date_scaled("AAA", "L", d) == (None, None)
        assert holding_utils._get_price_for_date_scaled("AAA", "L", d) == (None, None)
    assert len(calls) == 2, "a missing result must never be served from the memo"


def test_get_price_for_date_scaled_applies_scaling_fresh_every_call(monkeypatch):
    """#8232 review: the memo holds only the unscaled price; get_scaling_override
    (which reads data/scaling_overrides.json fresh, uncached, every call) must
    still be re-applied on every call rather than baked into the cached value.

    Uses a bare ``Close`` column (no ``Close_gbp``) since that's the column
    apply_scaling actually touches -- see
    test_get_price_for_date_scaled_never_scales_the_gbp_converted_column."""
    holding_utils._load_unscaled_price_for_date_cache_only.cache_clear()
    d = dt.date(2024, 1, 1)

    def fake_loader(*args, **kwargs):
        return pd.DataFrame({"Close": [10.0], "Source": ["Yahoo"]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)

    scales = [1.0, 2.0]

    def fake_scaling(*args, **kwargs):
        return scales.pop(0)

    monkeypatch.setattr(holding_utils, "get_scaling_override", fake_scaling)

    from backend.timeseries.cache import cache_only

    with cache_only():
        first, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d)
        second, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d)

    assert first == 10.0
    assert second == 20.0, "a changed scaling override must be reflected even though the load is memoized"


def test_get_price_for_date_scaled_never_scales_the_gbp_converted_column(monkeypatch):
    """#8232 review round 2: apply_scaling (backend/utils/timeseries_helpers.py)
    only multiplies the raw Open/High/Low/Close columns -- never Close_gbp,
    "adj close" or "adj_close". A value read from Close_gbp must therefore
    never be scaled, on the cache-only path or the live path, even when a
    non-1.0 scaling override exists for the ticker."""
    holding_utils._load_unscaled_price_for_date_cache_only.cache_clear()
    d = dt.date(2024, 1, 1)

    def fake_loader(*args, **kwargs):
        return pd.DataFrame({"Close_gbp": [10.0], "Source": ["Yahoo"]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 100.0)

    from backend.timeseries.cache import cache_only

    with cache_only():
        cache_only_price, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d)
    live_price, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d)

    assert cache_only_price == 10.0
    assert live_price == 10.0


def test_get_price_for_date_scaled_scales_close_on_the_live_path(monkeypatch):
    """#8232 review round 3: the live (non-cache_only) path must still scale a
    bare Close column exactly like the pre-refactor apply_scaling(df, scale)
    did -- the issue's constraint is that offline_mode: false behavior must
    not change, and this pins that for the scalable-column case (the
    Close_gbp case, which is deliberately *not* scaled, is covered by
    test_get_price_for_date_scaled_never_scales_the_gbp_converted_column)."""
    holding_utils._load_unscaled_price_for_date_cache_only.cache_clear()
    d = dt.date(2024, 1, 1)

    def fake_loader(*args, **kwargs):
        return pd.DataFrame({"Close": [10.0], "Source": ["Yahoo"]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 2.0)

    assert not holding_utils.is_cache_only()
    price, src = holding_utils._get_price_for_date_scaled("AAA", "L", d)

    assert price == 20.0
    assert src == "Yahoo"


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
