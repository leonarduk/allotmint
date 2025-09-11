import pandas as pd
import numpy as np
import pytest

from backend.common import portfolio_utils as pu


def test_compute_var_none_returns_none():
    assert pu.compute_var(None) is None


def test_compute_var_empty_df_returns_none():
    assert pu.compute_var(pd.DataFrame()) is None


def test_compute_var_missing_close_returns_none():
    df = pd.DataFrame({"Open": [1, 2, 3]})
    assert pu.compute_var(df) is None


def test_compute_var_one_valid_close_returns_none():
    df = pd.DataFrame({"Close": [100, np.nan, np.nan]})
    assert pu.compute_var(df) is None


def test_fx_to_gbp_cache_hit(monkeypatch):
    cache = {"USD": 1.25}

    def fake_fetch(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("fetch_fx_rate_range should not be called for cache hit")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    assert pu._fx_to_gbp("usd", cache) == 1.25


def test_fx_to_gbp_empty_lookup(monkeypatch):
    cache: dict[str, float] = {}
    df = pd.DataFrame(columns=["Rate"])
    monkeypatch.setattr(pu, "fetch_fx_rate_range", lambda *args, **kwargs: df)
    rate = pu._fx_to_gbp("USD", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0


def test_fx_to_gbp_fetch_exception(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", boom)
    cache: dict[str, float] = {}
    with caplog.at_level("WARNING"):
        rate = pu._fx_to_gbp("USD", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "Failed to fetch FX rate" in caplog.text
