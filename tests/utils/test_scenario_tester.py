import datetime as dt

import pandas as pd
import pytest

import backend.utils.scenario_tester as sc_tester



def test_apply_price_shock_falls_back_to_get_price(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "ABC",
                        "units": 10,
                    }
                ]
            }
        ],
        "total_value_estimate_gbp": 0.0,
    }

    calls = {}

    def fake_get_price_gbp(ticker):
        calls["ticker"] = ticker
        return 5.0

    monkeypatch.setattr(sc_tester, "get_price_gbp", fake_get_price_gbp)

    result = sc_tester.apply_price_shock(portfolio, "ABC", 10)
    holding = result["accounts"][0]["holdings"][0]

    assert calls["ticker"] == "ABC"
    assert holding["current_price_gbp"] == pytest.approx(5.5)
    assert holding["market_value_gbp"] == pytest.approx(55.0)
    assert result["accounts"][0]["value_estimate_gbp"] == pytest.approx(55.0)
    assert result["total_value_estimate_gbp"] == pytest.approx(55.0)


def test_forward_returns_empty(monkeypatch):
    def fake_load(*args, **kwargs):
        return pd.DataFrame()

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", fake_load)

    event_date = dt.date(2024, 1, 1)
    returns = sc_tester._forward_returns("ABC", "L", event_date)

    assert returns == {k: None for k in sc_tester._HORIZONS}


@pytest.mark.parametrize(
    "inp, expected",
    [
        ("ABC.L", ("ABC", "L")),
        ("DEF", ("DEF", "L")),
        ({"ticker": "ghi", "exchange": "ny"}, ("GHI", "NY")),
        ({"ticker": "jkl"}, ("JKL", "L")),
    ],
)
def test_parse_full_ticker_variants(inp, expected):
    assert sc_tester._parse_full_ticker(inp) == expected
