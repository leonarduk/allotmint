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
    returns, basis = sc_tester._forward_returns("ABC", "L", event_date)

    assert returns == {k: None for k in sc_tester._HORIZONS}
    assert basis == "price"
    assert called["scaling"] is False


def test_forward_returns_with_data(monkeypatch):
    event_date = dt.date(2024, 1, 1)
    dates = [event_date + dt.timedelta(days=d) for d in [0, 1, 7, 30, 90, 365]]
    prices = [100, 110, 120, 130, 140, 200]
    df = pd.DataFrame({"Date": dates, "Close_gbp": prices}).set_index("Date")

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(sc_tester, "get_scaling_override", lambda *a, **k: 1.0)
    monkeypatch.setattr(sc_tester, "apply_scaling", lambda d, s: d)

    returns, basis = sc_tester._forward_returns("ABC", "L", event_date)

    # No stored corporate actions for ABC.L, so it falls back to price return.
    assert basis == "price"
    assert returns["1d"] == pytest.approx(0.10)
    assert returns["1w"] == pytest.approx(0.20)
    assert returns["1m"] == pytest.approx(0.30)
    assert returns["3m"] == pytest.approx(0.40)
    assert returns["1y"] == pytest.approx(1.00)


def test_forward_returns_nonfinite_prices(monkeypatch):
    event_date = dt.date(2024, 1, 1)
    dates = [event_date + dt.timedelta(days=d) for d in [0, 1, 7, 30, 90, 365]]
    prices = [100, float("nan"), 120, float("inf"), 140, 200]
    df = pd.DataFrame({"Date": dates, "Close_gbp": prices}).set_index("Date")

    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(sc_tester, "get_scaling_override", lambda *a, **k: 1.0)
    monkeypatch.setattr(sc_tester, "apply_scaling", lambda d, s: d)

    returns, _basis = sc_tester._forward_returns("ABC", "L", event_date)

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

    def fake_forward_returns(ticker, exchange, event_date, horizons=sc_tester._HORIZONS):
        return returns_map[(ticker, exchange)], "total"

    monkeypatch.setattr(sc_tester, "_forward_returns", fake_forward_returns)

    result = sc_tester.apply_historical_event_portfolio(portfolio, event)

    assert result["1d"]["total_value_gbp"] == pytest.approx(105.5)
    assert result["1d"]["delta_gbp"] == pytest.approx(5.5)
    assert result["1w"]["total_value_gbp"] == pytest.approx(110.0)
    assert result["1m"]["total_value_gbp"] == pytest.approx(116.5)
    assert result["3m"]["total_value_gbp"] == pytest.approx(120.0)
    assert result["1y"]["total_value_gbp"] == pytest.approx(127.5)


def _single_holding(ticker, mv=100.0):
    return {
        "total_value_estimate_gbp": mv,
        "accounts": [{"holdings": [{"ticker": ticker, "market_value_gbp": mv}]}],
    }


def _no_scaling(monkeypatch, df):
    monkeypatch.setattr(sc_tester, "load_meta_timeseries_range", lambda *a, **k: df)
    monkeypatch.setattr(sc_tester, "get_scaling_override", lambda *a, **k: 1.0)
    monkeypatch.setattr(sc_tester, "apply_scaling", lambda d, s: d)


def test_apply_historical_event_portfolio_requires_dated_event():
    with pytest.raises(ValueError):
        sc_tester.apply_historical_event_portfolio(_single_holding("AAA.L"), None)
    with pytest.raises(ValueError):
        sc_tester.apply_historical_event_portfolio(_single_holding("AAA.L"), {"proxy_index": "SPY.N"})


def test_apply_historical_event_portfolio_no_data_is_none_not_zero(monkeypatch):
    monkeypatch.setattr(
        sc_tester,
        "_forward_returns",
        lambda t, e, d, horizons=sc_tester._HORIZONS: ({k: None for k in horizons}, "total"),
    )
    event = {"date": "2008-09-15", "proxy_index": "SPY.N"}

    result = sc_tester.apply_historical_event_portfolio(_single_holding("AAA.L"), event)

    assert result["1y"] == {
        "total_value_gbp": None,
        "delta_gbp": None,
        "coverage_pct": 0.0,
        "return_basis": "total",
        "price_return_tickers": [],
    }


def test_apply_historical_event_portfolio_holds_cash_flat(monkeypatch):
    calls = []

    def fake_forward_returns(ticker, exchange, event_date, horizons=sc_tester._HORIZONS):
        calls.append(ticker)
        return {k: -0.5 for k in horizons}, "total"

    monkeypatch.setattr(sc_tester, "_forward_returns", fake_forward_returns)
    portfolio = {
        "total_value_estimate_gbp": 200.0,
        "accounts": [
            {
                "holdings": [
                    {"ticker": "CASH.GBP", "market_value_gbp": 100.0},
                    {"ticker": "AAA.L", "market_value_gbp": 100.0},
                ]
            }
        ],
    }
    event = {"date": dt.date(2020, 2, 19), "proxy_index": "SPY.N"}

    result = sc_tester.apply_historical_event_portfolio(portfolio, event, horizons={"1m": 30})

    assert result == {
        "1m": {
            "total_value_gbp": 150.0,
            "delta_gbp": -50.0,
            "coverage_pct": 100.0,
            "return_basis": "total",
            "price_return_tickers": [],
        }
    }
    assert "CASH" not in calls


def test_apply_historical_event_portfolio_custom_horizons(monkeypatch):
    seen = {}

    def fake_forward_returns(ticker, exchange, event_date, horizons=sc_tester._HORIZONS):
        seen[ticker] = (event_date, dict(horizons))
        return {k: days / 100 for k, days in horizons.items()}, "total"

    monkeypatch.setattr(sc_tester, "_forward_returns", fake_forward_returns)
    event = {"date": "2020-02-19", "proxy_index": "SPY.N"}

    result = sc_tester.apply_historical_event_portfolio(_single_holding("AAA.L"), event, horizons={"10": 10})

    assert result == {
        "10": {
            "total_value_gbp": 110.0,
            "delta_gbp": 10.0,
            "coverage_pct": 100.0,
            "return_basis": "total",
            "price_return_tickers": [],
        }
    }
    assert seen["AAA"] == (dt.date(2020, 2, 19), {"10": 10})
    assert seen["SPY"][0] == dt.date(2020, 2, 19)


def test_forward_returns_ignores_prices_far_from_target(monkeypatch):
    """A fund that only started trading months after the event has no event-date base."""
    event_date = dt.date(2008, 9, 15)
    dates = [event_date + dt.timedelta(days=d) for d in [60, 90, 365]]
    _no_scaling(monkeypatch, pd.DataFrame({"Date": dates, "Close_gbp": [100, 110, 120]}).set_index("Date"))

    returns, _basis = sc_tester._forward_returns("NEW", "L", event_date)

    assert all(v is None for v in returns.values())


def test_forward_returns_tolerates_weekend_gaps(monkeypatch):
    event_date = dt.date(2020, 2, 19)
    # The 1y target is covered by a close three days later.
    dates = [event_date, event_date + dt.timedelta(days=368)]
    _no_scaling(monkeypatch, pd.DataFrame({"Date": dates, "Close_gbp": [100, 90]}).set_index("Date"))

    returns, _basis = sc_tester._forward_returns("ABC", "L", event_date)

    assert returns["1y"] == pytest.approx(-0.1)
    assert returns["1d"] is None


def _two_holdings(covered_mv, uncovered_mv):
    return {
        "total_value_estimate_gbp": covered_mv + uncovered_mv,
        "accounts": [
            {
                "holdings": [
                    {"ticker": "OLD.L", "market_value_gbp": covered_mv},
                    {"ticker": "NEW.L", "market_value_gbp": uncovered_mv},
                ]
            }
        ],
    }


def _old_only_returns(monkeypatch, ret):
    def fake_forward_returns(ticker, exchange, event_date, horizons=sc_tester._HORIZONS):
        return {k: ret if ticker == "OLD" else None for k in horizons}, "total"

    monkeypatch.setattr(sc_tester, "_forward_returns", fake_forward_returns)


def test_uncovered_holdings_follow_covered_return(monkeypatch):
    """A holding with no history (and no proxy data) moves with the rest of the portfolio."""
    _old_only_returns(monkeypatch, -0.2)
    event = {"date": "2020-02-19", "proxy_index": "SPY.N"}

    result = sc_tester.apply_historical_event_portfolio(_two_holdings(800.0, 200.0), event, horizons={"1m": 30})

    assert result == {
        "1m": {
            "total_value_gbp": 800.0,
            "delta_gbp": -200.0,
            "coverage_pct": 80.0,
            "return_basis": "total",
            "price_return_tickers": [],
        }
    }


def test_low_coverage_horizon_is_unavailable(monkeypatch):
    _old_only_returns(monkeypatch, -0.2)
    event = {"date": "2008-09-15", "proxy_index": "SPY.N"}

    result = sc_tester.apply_historical_event_portfolio(_two_holdings(300.0, 700.0), event, horizons={"1m": 30})

    assert result == {
        "1m": {
            "total_value_gbp": None,
            "delta_gbp": None,
            "coverage_pct": 30.0,
            "return_basis": "total",
            "price_return_tickers": [],
        }
    }


def test_empty_portfolio_is_unavailable_not_zero(monkeypatch):
    _old_only_returns(monkeypatch, 0.1)
    portfolio = {"total_value_estimate_gbp": 500.0, "accounts": [{"value_estimate_gbp": 500.0, "holdings": []}]}

    result = sc_tester.apply_historical_event_portfolio(portfolio, {"date": "2020-02-19"}, horizons={"1y": 365})

    assert result["1y"]["total_value_gbp"] is None


def test_value_outside_holdings_is_carried_at_baseline(monkeypatch):
    """delta_gbp reconciles with the account-level baseline (#9461)."""
    _old_only_returns(monkeypatch, -0.1)
    portfolio = {
        "total_value_estimate_gbp": 1000.0,
        "accounts": [
            {
                "value_estimate_gbp": 1000.0,
                "holdings": [{"ticker": "OLD.L", "market_value_gbp": 600.0}],
            }
        ],
    }

    result = sc_tester.apply_historical_event_portfolio(portfolio, {"date": "2020-02-19"}, horizons={"1m": 30})

    assert result == {
        "1m": {
            "total_value_gbp": 940.0,
            "delta_gbp": -60.0,
            "coverage_pct": 100.0,
            "return_basis": "total",
            "price_return_tickers": [],
        }
    }
