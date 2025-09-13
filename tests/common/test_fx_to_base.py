import pandas as pd
import pytest
from backend.common import portfolio_utils as pu


def test_fx_to_base_cache_hit(monkeypatch):
    cache = {"USD": 1.25}

    def fake_fetch(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("fetch_fx_rate_range should not be called for cache hit")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    assert pu._fx_to_base("usd", "GBP", cache) == 1.25


def test_fx_to_base_fetch_success(monkeypatch):
    cache = {}
    df = pd.DataFrame({"Rate": [1.3]})
    monkeypatch.setattr(pu, "fetch_fx_rate_range", lambda *args, **kwargs: df)
    rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.3
    assert cache["USD"] == 1.3


def test_fx_to_base_fetch_failure(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", boom)
    cache: dict[str, float] = {}
    with caplog.at_level("WARNING"):
        rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "Failed to fetch FX rate" in caplog.text


def test_fx_to_base_cross_rate(monkeypatch):
    cache: dict[str, float] = {}

    def fake_fetch(base, quote, start, end):
        rates = {"USD": 0.8, "EUR": 0.9}
        return pd.DataFrame({"Rate": [rates[base]]})

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    rate = pu._fx_to_base("USD", "EUR", cache)
    assert rate == pytest.approx(0.8 / 0.9)
    assert cache["USD"] == 0.8
    assert cache["EUR"] == 0.9
