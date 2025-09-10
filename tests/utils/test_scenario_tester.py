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


def test_apply_price_shock_updates_totals_without_fetch(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "XYZ",
                        "units": 5,
                        "current_price_gbp": 10.0,
                        "market_value_gbp": 50.0,
                        "cost_basis_gbp": 45.0,
                    }
                ],
                "value_estimate_gbp": 50.0,
            }
        ],
        "total_value_estimate_gbp": 50.0,
    }

    shocked = sc_tester.apply_price_shock(portfolio, "XYZ", -20)
    holding = shocked["accounts"][0]["holdings"][0]

    assert holding["current_price_gbp"] == pytest.approx(8.0)
    assert holding["market_value_gbp"] == pytest.approx(40.0)
    assert holding["gain_gbp"] == pytest.approx(-5.0)
    assert holding["day_change_gbp"] == pytest.approx(-10.0)
    assert shocked["accounts"][0]["value_estimate_gbp"] == pytest.approx(40.0)
    assert shocked["total_value_estimate_gbp"] == pytest.approx(40.0)

    # Original portfolio should remain unchanged
    orig = portfolio["accounts"][0]["holdings"][0]
    assert orig["current_price_gbp"] == 10.0
    assert portfolio["total_value_estimate_gbp"] == 50.0


def test_scale_portfolio_scales_each_horizon():
    portfolio = {
        "accounts": [{"value_estimate_gbp": 100.0}],
        "total_value_estimate_gbp": 100.0,
    }

    scaled = sc_tester._scale_portfolio(portfolio, horizons=[10, 50])

    assert scaled[10]["accounts"][0]["value_estimate_gbp"] == pytest.approx(90.0)
    assert scaled[10]["total_value_estimate_gbp"] == pytest.approx(90.0)
    assert scaled[50]["accounts"][0]["value_estimate_gbp"] == pytest.approx(50.0)
    assert scaled[50]["total_value_estimate_gbp"] == pytest.approx(50.0)


def test_forward_returns_empty(monkeypatch):
    def fake_load(*args, **kwargs):
        return pd.DataFrame()

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", fake_load)

    event_date = dt.date(2024, 1, 1)
    returns = sc_tester._forward_returns("ABC", "L", event_date)

    assert returns == {k: None for k in sc_tester._HORIZONS}


def test_forward_returns_with_data(monkeypatch):
    event_date = dt.date(2024, 1, 1)
    dates = [
        event_date + dt.timedelta(days=d)
        for d in [0, 1, 7, 30, 90, 365]
    ]
    prices = [100, 110, 120, 130, 140, 200]
    df = pd.DataFrame({"Date": dates, "Close_gbp": prices}).set_index("Date")

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(sc_tester, "get_scaling_override", lambda *a, **k: 1.0)
    monkeypatch.setattr(sc_tester, "apply_scaling", lambda d, s: d)

    returns = sc_tester._forward_returns("ABC", "L", event_date)

    assert returns["1d"] == pytest.approx(0.10)
    assert returns["1w"] == pytest.approx(0.20)
    assert returns["1m"] == pytest.approx(0.30)
    assert returns["3m"] == pytest.approx(0.40)
    assert returns["1y"] == pytest.approx(1.00)


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
