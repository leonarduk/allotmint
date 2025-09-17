import pytest
import backend.common.portfolio_utils as portfolio_utils
from backend.common import instrument_api as ia


def test_currency_from_instrument_meta(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC", "units": 1}]}]}

    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: {"currency": "USD"})
    monkeypatch.setenv("TESTING", "1")

    rows = portfolio_utils.aggregate_by_ticker(portfolio)

    assert len(rows) == 1
    assert rows[0]["currency"] == "USD"


def test_aggregate_by_ticker_fx_conversion(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "ABC", "units": 1, "market_value_gbp": 100, "gain_gbp": 10, "cost_gbp": 90}
                ]
            }
        ]
    }

    monkeypatch.setattr(
        portfolio_utils,
        "get_instrument_meta",
        lambda t: {"currency": "USD"},
    )

    def fake_fetch(base: str, quote: str, start, end):
        import pandas as pd

        rates = {"USD": 0.8, "EUR": 0.9}
        return pd.DataFrame({"Date": [start], "Rate": [rates[base]]})

    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", fake_fetch)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"ABC.L": {"last_price": 100}})

    rows_usd = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="USD")
    assert len(rows_usd) == 1
    rate_usd = 1 / 0.8
    assert rows_usd[0]["market_value_gbp"] == round(100 * rate_usd, 2)
    assert rows_usd[0]["gain_gbp"] == round(10 * rate_usd, 2)
    assert rows_usd[0]["cost_gbp"] == round(90 * rate_usd, 2)
    assert rows_usd[0]["last_price_gbp"] == pytest.approx(100 * rate_usd, rel=1e-4)
    assert rows_usd[0]["market_value_currency"] == "USD"

    rows_eur = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="EUR")
    assert len(rows_eur) == 1
    rate_eur = 1 / 0.9
    assert rows_eur[0]["market_value_gbp"] == round(100 * rate_eur, 2)
    assert rows_eur[0]["gain_gbp"] == round(10 * rate_eur, 2)
    assert rows_eur[0]["cost_gbp"] == round(90 * rate_eur, 2)
    assert rows_eur[0]["last_price_gbp"] == pytest.approx(100 * rate_eur, rel=1e-4)
    assert rows_eur[0]["market_value_currency"] == "EUR"


def test_aggregate_by_ticker_sets_grouping(monkeypatch):
    portfolio = {
        "accounts": [
            {
                "holdings": [
                    {"ticker": "AAA.L", "units": 1.0, "market_value_gbp": 100.0, "gain_gbp": 10.0},
                    {"ticker": "BBB.L", "units": 2.0, "market_value_gbp": 50.0, "gain_gbp": 5.0},
                    {"ticker": "CCC.L", "units": 3.0, "market_value_gbp": 25.0, "gain_gbp": 2.5},
                ]
            }
        ]
    }

    meta = {
        "AAA.L": {"name": "Alpha", "currency": "GBP", "grouping": "Explicit"},
        "BBB.L": {"name": "Beta", "currency": "GBP", "sector": "Sector B"},
        "CCC.L": {"name": "Gamma", "currency": "GBP", "region": "Region C"},
    }

    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {}, raising=False)
    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: meta.get(t, {}))
    monkeypatch.setattr(portfolio_utils, "get_security_meta", lambda t: meta.get(t, {}))
    monkeypatch.setattr(ia, "price_change_pct", lambda ticker, days: None)

    rows = portfolio_utils.aggregate_by_ticker(portfolio)
    assert len(rows) == 3
    by_ticker = {row["ticker"]: row for row in rows}

    assert by_ticker["AAA.L"]["grouping"] == "Explicit"
    assert by_ticker["BBB.L"]["grouping"] == "Sector B"
    assert by_ticker["CCC.L"]["grouping"] == "Region C"
