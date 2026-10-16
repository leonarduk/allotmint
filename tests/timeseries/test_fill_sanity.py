"""Gap fills on another currency/unit are not merged into a cached series (#10971)."""

import importlib
import sys

import numpy as np
import pandas as pd
import pytest

from backend.timeseries.fill_sanity import mismatched_fills

# Yahoo's SGLN.L history (GBp) as served in October 2026: traded closes at
# ~1790p with zero-volume rows at ~1.64x (the USD line, GBPUSD ~1.63) on the
# dates the GBp line did not trade.
_SGLN_TRADED = [
    ("2011-04-12", 1785.96, 1),
    ("2011-04-13", 1791.69, 330),
    ("2011-04-14", 1797.94, 5865),
    ("2011-04-18", 1842.17, 130),
    ("2011-04-26", 1822.00, 1000),
    ("2011-04-27", 1823.50, 330),
    ("2011-05-03", 1868.00, 1200),
]
_SGLN_USD_ROWS = [
    ("2011-04-08", 2938.98, 0),
    ("2011-04-11", 2935.91, 0),
    ("2011-04-15", 2953.33, 0),
    ("2011-04-19", 2980.75, 0),
    ("2011-04-20", 3001.73, 0),
    ("2011-04-21", 3007.71, 0),
    ("2011-04-28", 3070.55, 0),
    ("2011-04-29", 3070.56, 0),
]
# GBP per USD in April 2011.
_GBP_PER_USD = 0.612


def _frame(rows, source="Yahoo") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime([d for d, _, _ in rows]),
            "Open": [c for _, c, _ in rows],
            "High": [c for _, c, _ in rows],
            "Low": [c for _, c, _ in rows],
            "Close": [c for _, c, _ in rows],
            "Volume": [v for _, _, v in rows],
            "Ticker": "SGLN",
            "Source": source,
        }
    )


def _usd(n: int) -> list[np.ndarray]:
    return [np.full(n, _GBP_PER_USD)]


def test_rejects_untraded_rows_at_the_fx_rate_to_their_neighbours():
    candidates = _frame(_SGLN_USD_ROWS)

    bad = mismatched_fills(_frame(_SGLN_TRADED), candidates, _usd(len(candidates)))

    assert bad.all()


def test_keeps_a_good_fill_between_anchors():
    candidates = _frame([("2011-04-15", 1810.0, 0), ("2011-04-20", 1835.0, 0)])

    assert not mismatched_fills(_frame(_SGLN_TRADED), candidates, _usd(2)).any()


def test_fx_rate_is_not_tried_on_a_traded_row():
    """A crash day that reverts by about an FX rate trades; it is a real price, not a USD print."""
    anchors = _frame([("2020-03-13", 100.0, 500), ("2020-03-17", 100.0, 500)])
    crash = _frame([("2020-03-16", 100.0 * 0.8, 900)])

    assert not mismatched_fills(anchors, crash, [np.array([0.8])]).any()


def test_hundredfold_row_is_rejected_even_when_traded():
    anchors = _frame([("2024-01-02", 1500.0, 500), ("2024-01-04", 1510.0, 500)])
    pounds = _frame([("2024-01-03", 15.05, 700)])

    assert mismatched_fills(anchors, pounds, []).all()


def test_level_shift_kept_when_the_next_anchor_agrees():
    """A real move sits near the next anchor, so it fails the both-sides test."""
    anchors = _frame([("2011-04-12", 1785.96, 1), ("2011-04-14", 2930.0, 10)])
    jump = _frame([("2011-04-13", 2935.0, 0)])

    assert not mismatched_fills(anchors, jump, _usd(1)).any()


@pytest.mark.parametrize(
    ("day", "close", "expected"),
    [
        ("2011-04-11", 2935.91, True),  # anchor 1 day later, 64% off at the FX rate
        ("2011-03-28", 2935.91, False),  # anchor 15 days later: not a neighbour
        ("2011-04-11", 1785.96 * 1.2, False),  # 20% off: a single anchor can't tell this from a move
    ],
)
def test_one_sided_fill_needs_a_near_and_clear_mismatch(day, close, expected):
    anchors = _frame([("2011-04-12", 1785.96, 1), ("2011-04-13", 1791.69, 330)])
    fill = _frame([(day, close, 0)])

    fx = [np.array([_GBP_PER_USD]), np.array([1 / 1.2])]

    assert bool(mismatched_fills(anchors, fill, fx)[0]) is expected


def test_without_a_volume_column_every_row_counts_as_untraded():
    candidates = _frame(_SGLN_USD_ROWS).drop(columns="Volume")

    assert mismatched_fills(_frame(_SGLN_TRADED), candidates, _usd(len(candidates))).all()


def test_no_anchors_or_no_candidates_flags_nothing():
    rows = _frame(_SGLN_USD_ROWS)

    assert not mismatched_fills(rows.iloc[:0], rows, _usd(len(rows))).any()
    assert mismatched_fills(rows, rows.iloc[:0], []).shape == (0,)


def test_without_fx_rates_only_the_hundredfold_factor_applies():
    candidates = _frame(_SGLN_USD_ROWS + [("2011-04-15", 17.98, 0)])

    bad = mismatched_fills(_frame(_SGLN_TRADED), candidates, [])

    assert bad.tolist() == [False] * len(_SGLN_USD_ROWS) + [True]


def test_duplicate_anchor_dates_use_the_last_row():
    anchors = pd.concat([_frame([("2011-04-12", 2940.0, 1)]), _frame(_SGLN_TRADED)], ignore_index=True)

    assert mismatched_fills(anchors, _frame([("2011-04-11", 2935.91, 0)]), _usd(1)).all()


# ── _rolling_cache integration ─────────────────────────────────


@pytest.fixture
def cache(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    sys.modules.pop("backend.timeseries.cache", None)
    mod = importlib.import_module("backend.timeseries.cache")
    monkeypatch.setattr(mod, "OFFLINE_MODE", False)
    monkeypatch.setattr(mod, "fx_reference_currencies", lambda: ["USD"])
    fx_path = mod._fx_cache_path("USD")
    mod._ensure_local_dir(fx_path)
    pd.DataFrame({"Date": pd.bdate_range("2011-03-01", "2011-06-30"), "Rate": _GBP_PER_USD}).to_parquet(fx_path)
    return mod


def _yahoo_history() -> pd.DataFrame:
    return _frame(_SGLN_TRADED + _SGLN_USD_ROWS).sort_values("Date").reset_index(drop=True)


def _rolling(cache, path):
    return cache._rolling_cache(
        lambda **_k: _yahoo_history(), path, {}, 10000, ticker="SGLN", exchange="L", canonical_ticker="SGLN"
    )


def test_cold_fetch_stores_only_the_traded_basis(cache):
    """An empty/unreadable cache refetches the full history: the USD rows must not be stored."""
    path = cache._cache_path("meta", "SGLN_L.parquet")

    _rolling(cache, path)

    stored = cache._load_parquet(path)
    assert sorted(stored["Date"].dt.strftime("%Y-%m-%d")) == [d for d, _, _ in _SGLN_TRADED]


def test_backfill_against_cached_series_rejects_the_usd_rows(cache):
    """Rows added on dates the cache lacks are checked against the cached closes."""
    path = cache._cache_path("meta", "SGLN_L.parquet")
    cache._save_parquet(_frame(_SGLN_TRADED[2:]), path)

    _rolling(cache, path)

    stored = cache._load_parquet(path)
    assert sorted(stored["Date"].dt.strftime("%Y-%m-%d")) == [d for d, _, _ in _SGLN_TRADED]
    assert stored["Close"].max() < 2000


def test_cold_fetch_with_no_traded_rows_is_stored_as_fetched(cache):
    """No traded rows means no anchors: the check has nothing to judge against."""
    path = cache._cache_path("meta", "SGLN_L.parquet")
    untraded = _frame([(d, c, 0) for d, c, _ in _SGLN_TRADED + _SGLN_USD_ROWS])

    cache._rolling_cache(lambda **_k: untraded, path, {}, 10000, ticker="SGLN", exchange="L")

    assert len(cache._load_parquet(path)) == len(untraded)


def test_refetch_over_a_clean_cache_keeps_every_row(cache):
    path = cache._cache_path("meta", "SGLN_L.parquet")
    traded = _frame(_SGLN_TRADED)
    cache._save_parquet(traded.iloc[::2], path)

    cache._rolling_cache(lambda **_k: traded, path, {}, 10000, ticker="SGLN", exchange="L")

    assert len(cache._load_parquet(path)) == len(traded)
