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


def test_apply_price_shock_updates_all_totals_without_mutating_original():
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {
                        "ticker": "AAA",
                        "units": 10,
                        "current_price_gbp": 2.0,
                        "market_value_gbp": 20.0,
                        "cost_basis_gbp": 10.0,
                    }
                ],
                "value_estimate_gbp": 20.0,
            },
            {
                "holdings": [
                    {
                        "ticker": "BBB",
                        "units": 5,
                        "current_price_gbp": 4.0,
                        "market_value_gbp": 20.0,
                        "cost_basis_gbp": 15.0,
                    }
                ],
                "value_estimate_gbp": 20.0,
            },
        ],
        "total_value_estimate_gbp": 40.0,
    }

    shocked = sc_tester.apply_price_shock(portfolio, "AAA", 50)

    a1 = shocked["accounts"][0]["holdings"][0]
    assert a1["current_price_gbp"] == pytest.approx(3.0)
    assert a1["market_value_gbp"] == pytest.approx(30.0)
    assert shocked["accounts"][0]["value_estimate_gbp"] == pytest.approx(30.0)

    a2 = shocked["accounts"][1]["holdings"][0]
    assert a2["current_price_gbp"] == 4.0
    assert a2["market_value_gbp"] == 20.0
    assert shocked["accounts"][1]["value_estimate_gbp"] == pytest.approx(20.0)

    assert shocked["total_value_estimate_gbp"] == pytest.approx(50.0)

    # Original portfolio must remain unchanged
    assert portfolio["accounts"][0]["holdings"][0]["current_price_gbp"] == 2.0
    assert portfolio["total_value_estimate_gbp"] == 40.0


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

    called = {"scaling": False}

    def fake_scale(df, scale):
        called["scaling"] = True
        return df

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", fake_load)
    monkeypatch.setattr(sc_tester, "apply_scaling", fake_scale)

    event_date = dt.date(2024, 1, 1)
    returns = sc_tester._forward_returns("ABC", "L", event_date)

    assert returns == {k: None for k in sc_tester._HORIZONS}
    assert called["scaling"] is False


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


def test_forward_returns_nonfinite_prices(monkeypatch):
    event_date = dt.date(2024, 1, 1)
    dates = [
        event_date + dt.timedelta(days=d)
        for d in [0, 1, 7, 30, 90, 365]
    ]
    prices = [100, float("nan"), 120, float("inf"), 140, 200]
    df = pd.DataFrame({"Date": dates, "Close_gbp": prices}).set_index("Date")

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(sc_tester, "get_scaling_override", lambda *a, **k: 1.0)
    monkeypatch.setattr(sc_tester, "apply_scaling", lambda d, s: d)

    returns = sc_tester._forward_returns("ABC", "L", event_date)

    assert returns["1d"] is None
    assert returns["1w"] == pytest.approx(0.20)
    assert returns["1m"] is None
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


def test_apply_historical_event_portfolio_aggregates_returns(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "AAA.L", "market_value_gbp": 50.0},
                    {"ticker": "BBB.L", "market_value_gbp": 50.0},
                ]
            }
        ],
        "total_value_estimate_gbp": 100.0,
    }

    event = {"date": dt.date(2024, 1, 1), "proxy_index": "PRX.L"}

    returns_map = {
        ("AAA", "L"): {
            "1d": 0.1,
            "1w": 0.2,
            "1m": 0.3,
            "3m": 0.4,
            "1y": 0.5,
        },
        ("BBB", "L"): {
            "1d": None,
            "1w": 0.0,
            "1m": None,
            "3m": 0.0,
            "1y": None,
        },
        ("PRX", "L"): {
            "1d": 0.01,
            "1w": 0.02,
            "1m": 0.03,
            "3m": 0.04,
            "1y": 0.05,
        },
    }

    def fake_forward_returns(ticker, exchange, event_date):
        return returns_map[(ticker, exchange)]

    monkeypatch.setattr(sc_tester, "_forward_returns", fake_forward_returns)

    result = sc_tester.apply_historical_event_portfolio(portfolio, event)

    assert result["1d"]["total_value_gbp"] == pytest.approx(105.5)
    assert result["1d"]["delta_gbp"] == pytest.approx(5.5)
    assert result["1w"]["total_value_gbp"] == pytest.approx(110.0)
    assert result["1m"]["total_value_gbp"] == pytest.approx(116.5)
    assert result["3m"]["total_value_gbp"] == pytest.approx(120.0)
    assert result["1y"]["total_value_gbp"] == pytest.approx(127.5)
