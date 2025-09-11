import pandas as pd
from backend.common import portfolio_utils as pu


def test_fx_to_gbp_cache_hit(monkeypatch):
    cache = {"USD": 1.25}

    def fake_fetch(*args, **kwargs):  # pragma: no cover - should not be called
        raise AssertionError("fetch_fx_rate_range should not be called for cache hit")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    assert pu._fx_to_gbp("usd", cache) == 1.25


def test_fx_to_gbp_fetch_success(monkeypatch):
    cache = {}
    df = pd.DataFrame({"Rate": [1.3]})
    monkeypatch.setattr(pu, "fetch_fx_rate_range", lambda *args, **kwargs: df)
    rate = pu._fx_to_gbp("USD", cache)
    assert rate == 1.3
    assert cache["USD"] == 1.3


def test_fx_to_gbp_fetch_failure(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", boom)
    cache: dict[str, float] = {}
    with caplog.at_level("WARNING"):
        rate = pu._fx_to_gbp("USD", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "Failed to fetch FX rate" in caplog.text

