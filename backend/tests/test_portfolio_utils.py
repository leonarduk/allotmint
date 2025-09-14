import pandas as pd

import backend.common.portfolio_utils as pu

def test_fx_to_base_logs_warning_on_failure(monkeypatch, caplog):
    def fake_fetch(currency, quote, start, end):
        raise RuntimeError("boom")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    cache: dict[str, float] = {}
    with caplog.at_level("WARNING"):
        rate = pu._fx_to_base("USD", "GBP", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "USD" in caplog.text
    assert "boom" in caplog.text


def test_fx_to_base_uses_cache(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(base, quote, start, end):
        calls["n"] += 1
        return pd.DataFrame({"Rate": [0.5]})

    cache: dict[str, float] = {}
    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    first = pu._fx_to_base("USD", "GBP", cache)
    second = pu._fx_to_base("usd", "GBP", cache)
    assert first == second == 0.5
    assert calls["n"] == 1
