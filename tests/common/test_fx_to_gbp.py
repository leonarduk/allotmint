import pandas as pd
import pytest

from backend.common import portfolio_utils as pu


def test_fx_to_gbp_rate_cached(monkeypatch):
    cache = {}
    call_count = {"count": 0}

    def fake_fetch(base, quote, start, end):
        call_count["count"] += 1
        return pd.DataFrame({"Rate": [1.4]})

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)

    first = pu._fx_to_base("USD", "GBP", cache)
    second = pu._fx_to_base("usd", "GBP", cache)

    assert first == second == 1.4
    assert call_count["count"] == 1


def test_fx_to_gbp_fetch_exception(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("fail")

    cache: dict[str, float] = {}
    monkeypatch.setattr(pu, "fetch_fx_rate_range", boom)

    with caplog.at_level("WARNING"):
        rate = pu._fx_to_base("USD", "GBP", cache)

    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "Failed to fetch FX rate" in caplog.text
