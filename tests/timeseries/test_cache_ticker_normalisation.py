"""The meta cache stores one canonical Ticker form: the bare cache key (#10908)."""

import importlib
import sys
from datetime import datetime, timedelta

import pandas as pd


def import_cache():
    """Import ``backend.timeseries.cache`` after clearing any previous copy."""
    sys.modules.pop("backend.timeseries.cache", None)
    return importlib.import_module("backend.timeseries.cache")


def _rows(dates, ticker: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Date": pd.to_datetime(dates),
            "Open": [1.0] * len(dates),
            "High": [2.0] * len(dates),
            "Low": [0.5] * len(dates),
            "Close": [1.5 + i for i in range(len(dates))],
            "Volume": [100] * len(dates),
            "Ticker": [ticker] * len(dates),
            "Source": ["Yahoo"] * len(dates),
        }
    )


def _seed_and_refresh(monkeypatch, tmp_path, *, stored: str, fetched: str, canonical: str | None):
    """Seed a cache missing yesterday, refresh it with a fetch, return the stored parquet."""
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    yesterday = datetime.today().date() - timedelta(days=1)
    path = cache._cache_path("meta", "ERNS_L.parquet")
    cache._save_parquet(_rows(pd.bdate_range(end=yesterday, periods=30)[:-1], stored), path)

    def fetch(**kwargs):
        return _rows(pd.bdate_range(kwargs["start_date"], kwargs["end_date"]), fetched)

    result = cache._rolling_cache(fetch, path, {}, days=20, ticker="ERNS", exchange="L", canonical_ticker=canonical)
    return result, pd.read_parquet(path)


def test_with_canonical_ticker_rewrites_every_form(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    df = pd.DataFrame({"Ticker": ["ERNS.L", "ERNS", "erns", None]})

    out = cache.with_canonical_ticker(df, "erns")

    assert list(out["Ticker"]) == ["ERNS"] * 4
    assert list(df["Ticker"].iloc[:3]) == ["ERNS.L", "ERNS", "erns"]  # input untouched


def test_with_canonical_ticker_returns_conforming_frame_as_is(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    df = pd.DataFrame({"Ticker": ["ERNS", "ERNS"]})

    assert cache.with_canonical_ticker(df, "ERNS") is df


def test_merge_write_converges_suffixed_cache_and_fetch(monkeypatch, tmp_path):
    """A suffixed fetch merged into a suffixed cache is stored bare, old rows included."""
    result, stored = _seed_and_refresh(monkeypatch, tmp_path, stored="ERNS.L", fetched="ERNS.L", canonical="ERNS")

    assert len(stored) > 29  # the fetch added rows, so the file was rewritten
    assert set(stored["Ticker"]) == {"ERNS"}
    assert set(result["Ticker"]) == {"ERNS"}


def test_merge_write_does_not_mix_forms(monkeypatch, tmp_path):
    """Bare cache + suffixed fetch (the ERNS regression) stays bare after the merge."""
    _, stored = _seed_and_refresh(monkeypatch, tmp_path, stored="ERNS", fetched="ERNS.L", canonical="ERNS")

    assert set(stored["Ticker"]) == {"ERNS"}


def test_non_meta_caches_are_left_alone(monkeypatch, tmp_path):
    """Without a canonical ticker (the yahoo/stooq/ft caches) rows keep their stamp."""
    _, stored = _seed_and_refresh(monkeypatch, tmp_path, stored="ERNS", fetched="ERNS.L", canonical=None)

    assert set(stored["Ticker"]) == {"ERNS", "ERNS.L"}


def test_meta_loader_passes_cache_key_as_canonical_ticker(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    seen = {}

    def fake_rolling_cache(*_args, **kwargs):
        seen.update(kwargs)
        return cache._empty_ts()

    monkeypatch.setattr(cache, "_rolling_cache", fake_rolling_cache)
    cache._load_meta_timeseries_cached("ERNS", "L", 30)

    assert seen["canonical_ticker"] == "ERNS"


def test_with_canonical_ticker_returns_empty_frame_as_is(monkeypatch, tmp_path):
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    df = cache._empty_ts()

    assert cache.with_canonical_ticker(df, "ERNS") is df


def test_purge_write_normalises_suffixed_cache_without_a_fetch(monkeypatch, tmp_path):
    """Dropping unpriced rows rewrites the file, and that write stores the key too."""
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    cache = import_cache()
    monkeypatch.setattr(cache, "OFFLINE_MODE", False)
    yesterday = datetime.today().date() - timedelta(days=1)
    path = cache._cache_path("meta", "ERNS_L.parquet")
    seeded = _rows(pd.bdate_range(end=yesterday + timedelta(days=7), periods=60), "ERNS.L")
    seeded.loc[0, "Close"] = float("nan")  # an unpriced row forces the purge write
    cache._save_parquet(seeded, path)

    fetches = []

    cache._rolling_cache(fetches.append, path, {}, days=20, ticker="ERNS", exchange="L", canonical_ticker="ERNS")

    assert fetches == []  # the cache covers the window
    stored = pd.read_parquet(path)
    assert len(stored) == 59
    assert set(stored["Ticker"]) == {"ERNS"}
