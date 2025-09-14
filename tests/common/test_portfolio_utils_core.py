import json
from datetime import datetime

import pandas as pd
import numpy as np
import pytest

from backend.common import portfolio_utils as pu


def test_compute_var_returns_value():
    df = pd.DataFrame({"Close": [100, 90, 80]})
    expected = -np.quantile(df["Close"].pct_change().dropna(), 0.05) * 80
    var = pu.compute_var(df)
    assert var == pytest.approx(expected)


def test_compute_var_insufficient_data():
    df = pd.DataFrame({"Close": [100]})
    assert pu.compute_var(df) is None


def test_fx_to_base_cache_hit(monkeypatch):
    cache = {"USD": 1.25}

    def fake_fetch(*args, **kwargs):
        raise AssertionError("fetch_fx_rate_range should not be called for cache hit")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    assert pu._fx_to_base("usd", "GBP", cache) == 1.25


def test_fx_to_base_cache_miss(monkeypatch):
    cache = {}
    df = pd.DataFrame({"Rate": [1.3]})
    monkeypatch.setattr(pu, "fetch_fx_rate_range", lambda *args, **kwargs: df)
    rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.3
    assert cache["USD"] == 1.3


def test_fx_to_base_fetch_failure(monkeypatch, caplog):
    def fake_fetch(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    cache = {}
    with caplog.at_level("WARNING"):
        rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "Failed to fetch FX rate" in caplog.text


def test_load_snapshot_local_file(tmp_path, monkeypatch):
    path = tmp_path / "latest_prices.json"
    data = {"ABC": {"price": 123}}
    path.write_text(json.dumps(data))
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)
    monkeypatch.setattr(pu.config, "app_env", "local")
    loaded, ts = pu._load_snapshot()
    assert loaded == data
    assert isinstance(ts, datetime)


def test_load_snapshot_missing_file(tmp_path, monkeypatch, caplog):
    path = tmp_path / "missing.json"
    monkeypatch.setattr(pu.config, "prices_json", path)
    monkeypatch.setattr(pu, "_PRICES_PATH", path)
    monkeypatch.setattr(pu.config, "app_env", "local")
    with caplog.at_level("WARNING"):
        data, ts = pu._load_snapshot()
    assert data == {}
    assert ts is None
    assert str(path) in caplog.text

