import pandas as pd
import pytest

from backend.common import portfolio_utils as pu


def test_compute_var_positive_value():
    df = pd.DataFrame({"Close": [100, 90, 80]})
    var = pu.compute_var(df)
    assert var is not None and var > 0


@pytest.mark.parametrize(
    "df",
    [
        pd.DataFrame(),
        pd.DataFrame({"Close": []}),
    ],
)
def test_compute_var_missing_or_empty_close(df):
    assert pu.compute_var(df) is None


def test_fx_to_gbp_fetch_exception(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("fail")

    monkeypatch.setattr(pu, "fetch_fx_rate_range", boom)
    cache: dict[str, float] = {}
    rate = pu._fx_to_gbp("USD", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0


def test_fx_to_gbp_rate_cached(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(currency, start, end):
        calls["n"] += 1
        return pd.DataFrame({"Rate": [1.1, 1.2]})

    cache: dict[str, float] = {}
    monkeypatch.setattr(pu, "fetch_fx_rate_range", fake_fetch)
    first = pu._fx_to_gbp("USD", cache)
    second = pu._fx_to_gbp("usd", cache)
    assert first == second == 1.2
    assert calls["n"] == 1
    assert cache["USD"] == 1.2
