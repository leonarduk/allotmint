"""Declared price adjustments for unrecorded splits (#10040, #10024).

JEGI.L's raw Yahoo history steps from 177.75 to 44.56 (~1/4) across a share
sub-division Yahoo never recorded. A ``price_adjustments`` block in the
instrument metadata restates the old-basis rows at read time, so the served
series is continuous, a live refetch of raw rows cannot undo it, and an
instrument without the block is untouched.
"""

import importlib
import logging
import sys
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from backend.timeseries import price_adjustments as pa
from backend.timeseries import total_return as tr

BASIS_CHANGE = date(2011, 1, 4)
JEGI_BLOCK = {
    "before": "2011-01-04",
    "factor": 0.25,
    "rationale": "4-for-1 sub-division Yahoo never recorded",
    "reviewed": "2026-10-11",
}


def _meta(*entries):
    return {"price_adjustments": list(entries)}


@pytest.fixture
def declare(monkeypatch):
    """Serve ``price_adjustments`` metadata for ``JEGI.L`` and none for anything else."""
    metas: dict[str, dict] = {}
    monkeypatch.setattr(pa, "get_instrument_meta", lambda ticker: metas.get(ticker, {}))

    def _declare(*entries, ticker="JEGI.L"):
        metas[ticker] = _meta(*entries)

    return _declare


def _frame(days, closes, volumes=None):
    n = len(days)
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(list(days)),
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": volumes if volumes is not None else [1000] * n,
            "Ticker": ["JEGI"] * n,
            "Source": ["Yahoo"] * n,
        }
    )


def _max_daily_move(closes) -> float:
    values = np.asarray(closes, dtype=float)
    return float(np.max(np.abs(values[1:] / values[:-1] - 1.0)))


# ──────────────────────────── validation ────────────────────────────


def test_valid_block_parses_with_dividends_before_defaulting_to_before():
    (adj,) = pa.parse_price_adjustments(_meta(JEGI_BLOCK))
    assert adj.before == BASIS_CHANGE
    assert adj.factor == 0.25
    assert adj.dividends_before == BASIS_CHANGE
    assert adj.reviewed == date(2026, 10, 11)


def test_absent_block_is_valid_and_empty():
    assert pa.validate_price_adjustments({}) == []
    assert pa.validate_price_adjustments(None) == []
    assert pa.parse_price_adjustments({"currency": "GBP"}) == ()


@pytest.mark.parametrize(
    "change, fragment",
    [
        ({"factor": 1}, "factor"),
        ({"factor": 0}, "factor"),
        ({"factor": -0.25}, "factor"),
        ({"factor": float("nan")}, "factor"),
        ({"factor": True}, "factor"),
        ({"factor": "0.25"}, "factor"),
        ({"before": "04/01/2011"}, "before"),
        ({"before": None}, "before"),
        ({"dividends_before": "soon"}, "dividends_before"),
        ({"rationale": "  "}, "rationale"),
        ({"reviewed": None}, "reviewed"),
        ({"kind": "currency"}, "kind"),
        ({"kind": None}, "kind"),
    ],
)
def test_invalid_entries_are_reported(change, fragment):
    problems = pa.validate_price_adjustments(_meta({**JEGI_BLOCK, **change}))
    assert len(problems) == 1 and fragment in problems[0]
    with pytest.raises(ValueError):
        pa.parse_price_adjustments(_meta({**JEGI_BLOCK, **change}))


def test_non_list_block_and_duplicate_dates_are_reported():
    assert pa.validate_price_adjustments({"price_adjustments": JEGI_BLOCK}) == ["price_adjustments must be a JSON list"]
    assert pa.validate_price_adjustments(_meta(JEGI_BLOCK, "x")) == ["price_adjustments[1] must be a JSON object"]
    assert "share a before date" in pa.validate_price_adjustments(_meta(JEGI_BLOCK, {**JEGI_BLOCK, "factor": 2}))[0]
    respelled = {**JEGI_BLOCK, "before": "20110104", "factor": 2}
    assert "share a before date" in pa.validate_price_adjustments(_meta(JEGI_BLOCK, respelled))[0]


def test_invalid_block_is_ignored_with_a_warning(declare, caplog):
    declare({**JEGI_BLOCK, "reviewed": None})
    with caplog.at_level(logging.WARNING, logger=pa.__name__):
        assert pa.adjustments_for("JEGI", "L") == ()
    assert "Ignoring invalid price_adjustments for JEGI.L" in caplog.text


# ──────────────────────────── application ────────────────────────────


def test_rows_before_the_basis_change_are_restated():
    raw = _frame([date(2010, 12, 30), date(2010, 12, 31), BASIS_CHANGE], [177.0, 177.75, 44.56], [100, 200, 900])
    snapshot = raw.copy()

    out = pa.apply_price_adjustments(raw, pa.parse_price_adjustments(_meta(JEGI_BLOCK)))

    assert out["Close"].tolist() == pytest.approx([44.25, 44.4375, 44.56])
    assert out["High"].tolist() == pytest.approx([44.25 * 1.01, 44.4375 * 1.01, 44.56 * 1.01])
    assert out["Volume"].tolist() == [400, 800, 900]
    pd.testing.assert_frame_equal(raw, snapshot)  # input not mutated


def test_kind_defaults_to_split_and_split_restates_volume():
    (default,) = pa.parse_price_adjustments(_meta(JEGI_BLOCK))
    (explicit,) = pa.parse_price_adjustments(_meta({**JEGI_BLOCK, "kind": "split"}))
    assert default.kind == explicit.kind == "split"
    raw = _frame([date(2010, 12, 31), BASIS_CHANGE], [177.75, 44.56], [200, 900])
    assert pa.apply_price_adjustments(raw, (explicit,))["Volume"].tolist() == [800, 900]


def test_unit_change_restates_prices_but_not_volume():
    """A pence-to-pounds switch (BCG.L) leaves the share count, so Volume, unchanged (#10734)."""
    block = {**JEGI_BLOCK, "before": "2026-08-24", "factor": 0.01, "kind": "units"}
    raw = _frame([date(2026, 8, 21), date(2026, 8, 24)], [203.4, 2.046], [1006102, 589194])

    out = pa.apply_price_adjustments(raw, pa.parse_price_adjustments(_meta(block)))

    assert out["Close"].tolist() == pytest.approx([2.034, 2.046])
    assert out["Volume"].tolist() == [1006102, 589194]


def test_mixed_kinds_scale_volume_only_for_splits():
    split = {**JEGI_BLOCK, "before": "2000-01-04", "factor": 0.5}
    units = {**JEGI_BLOCK, "factor": 100, "kind": "units"}
    raw = _frame([date(1999, 12, 31), date(2005, 6, 1), BASIS_CHANGE], [1.0, 1.0, 100.0], [10, 10, 10])

    out = pa.apply_price_adjustments(raw, pa.parse_price_adjustments(_meta(split, units)))

    assert out["Close"].tolist() == pytest.approx([50.0, 100.0, 100.0])
    assert out["Volume"].tolist() == [20, 10, 10]


def test_entries_compound():
    adjustments = pa.parse_price_adjustments(_meta(JEGI_BLOCK, {**JEGI_BLOCK, "before": "2000-01-04", "factor": 0.5}))
    raw = _frame([date(1999, 12, 31), date(2005, 6, 1), BASIS_CHANGE], [400.0, 200.0, 50.0])
    out = pa.apply_price_adjustments(raw, adjustments)
    assert out["Close"].tolist() == pytest.approx([50.0, 50.0, 50.0])


def test_no_adjustment_or_no_old_basis_rows_returns_the_same_object():
    raw = _frame([BASIS_CHANGE, date(2011, 1, 5)], [44.56, 44.8])
    assert pa.apply_price_adjustments(raw, ()) is raw
    assert pa.apply_price_adjustments(raw, pa.parse_price_adjustments(_meta(JEGI_BLOCK))) is raw


def test_tz_aware_dates_compare_on_their_calendar_day():
    raw = _frame([date(2010, 12, 31), BASIS_CHANGE], [177.75, 44.56])
    raw["Date"] = raw["Date"].dt.tz_localize("Europe/London")
    out = pa.apply_price_adjustments(raw, pa.parse_price_adjustments(_meta(JEGI_BLOCK)))
    assert out["Close"].tolist() == pytest.approx([44.4375, 44.56])


# ──────────────────────────── served series (cache.py) ────────────────────────────


def _import_cache():
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def _raw_history(basis_change: date, end: date) -> pd.DataFrame:
    """Raw Yahoo-shaped history with a ~1/4 cliff at ``basis_change``, ending ``end``."""
    days = [d.date() for d in pd.bdate_range(basis_change - timedelta(days=21), end)]
    closes = [177.75 + 0.1 * i if d < basis_change else 44.56 + 0.025 * i for i, d in enumerate(days)]
    return _frame(days, closes)


@pytest.fixture
def live_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = _import_cache()
    monkeypatch.setattr(cache.config, "offline_mode", False)
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    return cache


def _end() -> date:
    return datetime.today().date() - timedelta(days=1)


@pytest.mark.parametrize("stored", ["raw", "truncated"])
def test_live_refetch_of_raw_rows_serves_a_continuous_series_and_keeps_the_store_raw(
    live_cache, declare, monkeypatch, stored
):
    """A days=all refresh refetches raw Yahoo rows; the served series stays continuous.

    ``raw``: the parquet holds the full unadjusted history and the refetch
    returns identical rows (nothing to merge). ``truncated``: a data-only repair
    cut the parquet at the basis change, so the refetch re-adds the raw
    pre-change rows as new dates -- the case a data-only fix could not survive.
    """
    cache = live_cache
    end = _end()
    basis_change = (pd.Timestamp(end) - pd.offsets.BDay(10)).date()
    declare({**JEGI_BLOCK, "before": basis_change.isoformat()})
    raw = _raw_history(basis_change, end)
    path = cache.meta_timeseries_cache_path("JEGI", "L")
    seed = raw if stored == "raw" else raw[raw["Date"].dt.date >= basis_change]
    cache._save_parquet(seed.reset_index(drop=True), path)

    def fetch(**kwargs):
        days = raw["Date"].dt.date
        return raw[(days >= kwargs["start_date"]) & (days <= kwargs["end_date"])].reset_index(drop=True)

    monkeypatch.setattr(cache, "fetch_meta_timeseries", fetch)
    days = (end - raw["Date"].iloc[0].date()).days + 5

    served = cache.load_meta_timeseries("JEGI", "L", days)

    assert served["Date"].dt.date.tolist() == raw["Date"].dt.date.tolist()
    assert _max_daily_move(served["Close"]) < 0.01
    stored_closes = cache._load_parquet(path)["Close"].tolist()
    assert stored_closes == pytest.approx(raw["Close"].tolist())  # store stays raw Yahoo


def test_cache_only_range_read_is_restated_and_recomputed_when_metadata_changes(live_cache, declare, monkeypatch):
    cache = live_cache
    end = _end()
    basis_change = (pd.Timestamp(end) - pd.offsets.BDay(10)).date()
    raw = _raw_history(basis_change, end)
    monkeypatch.setattr(cache, "_load_meta_parquet_cached", lambda path: raw)
    monkeypatch.setattr(cache, "_queue_if_stale", lambda *a, **k: None)
    start, stop = raw["Date"].iloc[0].date().isoformat(), end.isoformat()

    def read():
        cache._memoized_range_cached.cache_clear()
        token = cache._CACHE_ONLY.set(True)
        try:
            return cache._memoized_range("JEGI", "L", start, stop)
        finally:
            cache._CACHE_ONLY.reset(token)

    assert _max_daily_move(read()["Close"]) > 0.7  # undeclared: raw cliff served as stored
    declare({**JEGI_BLOCK, "before": basis_change.isoformat()})
    assert _max_daily_move(read()["Close"]) < 0.01


def test_instrument_without_the_block_is_unchanged(live_cache, declare, monkeypatch):
    cache = live_cache
    declare(JEGI_BLOCK)  # declared for JEGI.L only
    end = _end()
    raw = _raw_history((pd.Timestamp(end) - pd.offsets.BDay(10)).date(), end)
    monkeypatch.setattr(cache, "_load_meta_parquet_cached", lambda path: raw)
    monkeypatch.setattr(cache, "_queue_if_stale", lambda *a, **k: None)
    token = cache._CACHE_ONLY.set(True)
    try:
        served = cache._memoized_range("OTHR", "L", raw["Date"].iloc[0].date().isoformat(), end.isoformat())
    finally:
        cache._CACHE_ONLY.reset(token)
    assert served["Close"].tolist() == raw["Close"].tolist()


# ──────────────────────────── dividends (total_return.py) ────────────────────────────


def test_dividends_before_their_own_basis_change_are_restated(declare):
    declare({**JEGI_BLOCK, "dividends_before": "2021-06-01"})
    stored = pd.Series([8.0, 8.0, 2.1], index=pd.to_datetime(["2010-11-01", "2020-11-01", "2021-11-01"]))
    stored.attrs["confirmed_from"] = "2000-01-01"

    restated = tr._dividends_for("JEGI", "L", lambda _t, _e: stored)

    assert restated.tolist() == [2.0, 2.0, 2.1]
    assert restated.attrs == stored.attrs
    assert stored.tolist() == [8.0, 8.0, 2.1]  # loader's series not mutated


def test_dividends_without_the_block_are_returned_as_stored(declare):
    stored = pd.Series([8.0], index=pd.to_datetime(["2010-11-01"]))
    assert tr._dividends_for("OTHR", "L", lambda _t, _e: stored) is stored
