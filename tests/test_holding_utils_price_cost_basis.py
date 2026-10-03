import datetime as dt

import pandas as pd
import pytest

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


def test_load_unscaled_price_for_date_impl_handles_cash_directly(monkeypatch):
    """#8232 review round 4: _load_unscaled_price_for_date_impl is called
    directly by scripts/profile_single_day_lookups.py and by tests, not only
    through the _get_price_for_date_scaled dispatcher that used to be the
    sole place CASH was special-cased -- it must short-circuit CASH itself
    rather than hitting load_meta_timeseries_range for a ticker with no
    backing parquet."""

    def explode(*args, **kwargs):
        raise AssertionError("CASH must never reach load_meta_timeseries_range")

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", explode)
    d = dt.date(2024, 1, 1)
    price, src, scalable, row_date = holding_utils._load_unscaled_price_for_date_impl("CASH", "L", d)
    assert (price, src, scalable, row_date) == (1.0, None, False, d)


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


def test_get_price_for_date_scaled_keyed_on_field(monkeypatch):
    """#8232 review round 7: the memo key includes `field` -- two different
    fields for the same (ticker, exchange, d) must never collide into one
    cache entry."""
    holding_utils._load_unscaled_price_for_date_cache_only.cache_clear()
    d = dt.date(2024, 1, 1)

    def fake_loader(*args, **kwargs):
        return pd.DataFrame({"Close_gbp": [10.0], "Open": [5.0], "Source": ["Yahoo"]})

    monkeypatch.setattr(holding_utils, "load_meta_timeseries_range", fake_loader)
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: 1.0)

    from backend.timeseries.cache import cache_only

    with cache_only():
        close_price, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d, field="Close_gbp")
        open_price, _ = holding_utils._get_price_for_date_scaled("AAA", "L", d, field="Open")

    assert close_price == 10.0
    assert open_price == 5.0
    assert len(holding_utils._unscaled_price_cache) == 2


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


def test_scalable_columns_matches_apply_scaling_exactly():
    """#8232 review round 6: holding_utils._SCALABLE_COLUMNS is a hardcoded
    mirror of apply_scaling's actual behavior (backend/utils/timeseries_helpers.py),
    not derived from it -- so a future column added to apply_scaling (or
    removed) would silently desync the two. Locks the invariant: for every
    known candidate column, apply_scaling changing it must agree exactly with
    whether that column's lowercase name is in _SCALABLE_COLUMNS."""
    from backend.utils.timeseries_helpers import apply_scaling

    candidates = ["Open", "High", "Low", "Close", "Close_gbp", "Adj Close", "Volume", "Source"]
    df = pd.DataFrame({col: [1.0] if col != "Source" else ["Yahoo"] for col in candidates})

    scaled = apply_scaling(df, scale=2.0)

    for col in candidates:
        if col == "Source":
            continue
        actually_scaled = scaled[col].iloc[0] != df[col].iloc[0]
        expected_scalable = col.lower() in holding_utils._SCALABLE_COLUMNS
        assert (
            actually_scaled == expected_scalable
        ), f"{col}: apply_scaling scaled={actually_scaled}, _SCALABLE_COLUMNS says={expected_scalable}"


# ─────── booked cost plausibility (#8472) ───────
def _patch_enrich_env(monkeypatch, current_price, acq_close=None):
    """Isolate enrich_holding from metadata, snapshots and the timeseries cache."""
    from backend.common import instrument_api
    from backend.common import portfolio_utils as pu

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda full, cache: (full.split(".")[0], "L"))
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", {})
    monkeypatch.setattr(holding_utils, "get_instrument_meta", lambda *_: {})
    monkeypatch.setattr(holding_utils, "get_scaling_override", lambda *args, **kwargs: None)
    monkeypatch.setattr(holding_utils, "_get_price_for_date_scaled", lambda *a, **k: (current_price, "mock"))
    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", lambda *a, **k: acq_close)


def test_enrich_holding_flags_implausible_book_cost(monkeypatch):
    """AV. from #8472: 50 units booked at £263 against £672.40 -> +12,679% gain.
    Implied unit cost £5.26 is far below 1/20 of the price, so the holding is
    flagged and its gain withheld, while the booked cost itself is untouched."""
    _patch_enrich_env(monkeypatch, current_price=672.40)
    holding = {TICKER: "AV.L", UNITS: 50, COST_BASIS_GBP: 263}

    out = holding_utils.enrich_holding(holding, dt.date(2026, 10, 1), price_cache={})

    assert out["cost_basis_source"] == holding_utils.BOOK_COST_SUSPECT_SOURCE == "book_suspect"
    assert out["cost_basis_warning"] == "implied_unit_cost_out_of_band"
    assert out[COST_BASIS_GBP] == 263
    assert out["market_value_gbp"] == 33620.0
    for key in ("gain_gbp", "unrealised_gain_gbp", "unrealized_gain_gbp", "gain_pct"):
        assert out[key] is None
    assert holding[COST_BASIS_GBP] == 263, "the caller's holding must never be mutated"


def test_enrich_holding_flags_book_cost_far_above_price(monkeypatch):
    _patch_enrich_env(monkeypatch, current_price=1.0)
    holding = {TICKER: "AAA.L", UNITS: 10, COST_BASIS_GBP: 500}  # £50/unit vs £1

    out = holding_utils.enrich_holding(holding, dt.date(2026, 10, 1), price_cache={})

    assert out["cost_basis_source"] == "book_suspect"
    assert out["gain_pct"] is None


def test_enrich_holding_plausible_book_cost_unchanged(monkeypatch):
    _patch_enrich_env(monkeypatch, current_price=672.40)
    holding = {TICKER: "AV.L", UNITS: 50, COST_BASIS_GBP: 26300}

    out = holding_utils.enrich_holding(holding, dt.date(2026, 10, 1), price_cache={})

    assert out["cost_basis_source"] == "book"
    assert "cost_basis_warning" not in out
    assert out[COST_BASIS_GBP] == 26300
    assert out["gain_gbp"] == 7320.0
    assert out["gain_pct"] == pytest.approx(7320.0 / 26300 * 100)


def test_enrich_holding_big_genuine_gain_supported_by_acquisition_close(monkeypatch):
    """A real 30-bagger: £1/unit booked, now £30, but it closed at ~£1 on the
    acquisition date -- judged against that close it is plausible."""
    _patch_enrich_env(monkeypatch, current_price=30.0, acq_close=1.05)
    holding = {TICKER: "BIG.L", UNITS: 100, COST_BASIS_GBP: 100, ACQUIRED_DATE: "2010-01-04"}

    out = holding_utils.enrich_holding(holding, dt.date(2026, 10, 1), price_cache={})

    assert out["cost_basis_source"] == "book"
    assert out["gain_gbp"] == 2900.0
    assert out["gain_pct"] == pytest.approx(2900.0)


def test_enrich_holding_uses_acquisition_close_over_current_price(monkeypatch):
    """Acquisition-date close wins as reference even when the current price
    would have accepted the booked cost."""
    _patch_enrich_env(monkeypatch, current_price=10.0, acq_close=1000.0)
    holding = {TICKER: "DROP.L", UNITS: 10, COST_BASIS_GBP: 100, ACQUIRED_DATE: "2020-01-02"}

    out = holding_utils.enrich_holding(holding, dt.date(2026, 10, 1), price_cache={})

    assert out["cost_basis_source"] == "book_suspect"


def test_enrich_holding_no_reference_price_is_not_flagged(monkeypatch):
    _patch_enrich_env(monkeypatch, current_price=None)
    holding = {TICKER: "NOPX.L", UNITS: 50, COST_BASIS_GBP: 263}

    out = holding_utils.enrich_holding(holding, dt.date(2026, 10, 1), price_cache={})

    assert out["cost_basis_source"] == "book"
    assert "cost_basis_warning" not in out


def test_enrich_holding_acquisition_close_lookup_error_falls_back_to_current_price(monkeypatch):
    """Offline mode with no cached series raises ValueError from the
    acquisition-close lookup; the check must fall back to the current price
    instead of failing enrichment."""
    _patch_enrich_env(monkeypatch, current_price=672.40)

    def boom(*args, **kwargs):
        raise ValueError("Offline mode: no cache available")

    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", boom)
    holding = {TICKER: "AV.L", UNITS: 50, COST_BASIS_GBP: 263, ACQUIRED_DATE: "2020-01-02"}

    out = holding_utils.enrich_holding(holding, dt.date(2026, 10, 1), price_cache={})

    assert out["cost_basis_source"] == "book_suspect"


@pytest.mark.parametrize("cost", [None, 0, 0.0, "", "not-a-number", float("nan")])
def test_flag_implausible_book_cost_ignores_missing_or_zero_cost(monkeypatch, cost):
    """A "book" source with a missing/zero/garbage cost must be skipped, never
    raise -- one bad record must not break enrich_holding for a portfolio."""
    _patch_enrich_env(monkeypatch, current_price=672.40)
    out = {TICKER: "AV.L", UNITS: 50, "cost_basis_source": "book", "gain_gbp": 1.0}
    if cost is not None:
        out[COST_BASIS_GBP] = cost

    holding_utils._flag_implausible_book_cost(out, 50, "AV", "L", None, 672.40, {})

    assert out["cost_basis_source"] == "book"
    assert out["gain_gbp"] == 1.0


def test_flag_implausible_book_cost_ignores_zero_units(monkeypatch):
    _patch_enrich_env(monkeypatch, current_price=672.40)
    out = {TICKER: "AV.L", UNITS: 0, COST_BASIS_GBP: 263, "cost_basis_source": "book"}

    holding_utils._flag_implausible_book_cost(out, 0, "AV", "L", None, 672.40, {})

    assert out["cost_basis_source"] == "book"


def test_acquisition_close_failure_warns_once_per_ticker(monkeypatch, caplog):
    import logging

    _patch_enrich_env(monkeypatch, current_price=672.40)

    def boom(*args, **kwargs):
        raise ValueError("Offline mode: no cache available")

    monkeypatch.setattr(holding_utils, "_derived_cost_basis_close_px", boom)
    monkeypatch.setattr(holding_utils, "_ACQ_CLOSE_FAILURE_WARNED", set())
    acq = dt.date(2020, 1, 2)

    with caplog.at_level(logging.DEBUG, logger=holding_utils.logger.name):
        for _ in range(3):
            holding_utils._book_cost_reference_price("AV", "L", acq, 672.40, {})

    records = [r for r in caplog.records if "acquisition close unavailable" in r.getMessage()]
    assert [r.levelno for r in records] == [logging.WARNING, logging.DEBUG, logging.DEBUG]


def test_cost_basis_unreliable_sources_contents():
    """Pinned set; must match UNRELIABLE_SOURCES in frontend/src/lib/costBasis.ts
    (whose own test, frontend/tests/unit/lib/costBasis.test.ts, pins the same list)."""
    assert holding_utils.COST_BASIS_UNRELIABLE_SOURCES == frozenset({"unknown", "book_suspect"})
    assert holding_utils.is_cost_basis_unreliable("book_suspect")
    assert holding_utils.is_cost_basis_unreliable("unknown")
    for source in ("book", "derived", "cash", "none", None):
        assert not holding_utils.is_cost_basis_unreliable(source)
