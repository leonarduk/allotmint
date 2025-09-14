import pytest
import backend.common.portfolio_utils as portfolio_utils


def test_currency_from_instrument_meta(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC", "units": 1}]}]}

    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: {"currency": "USD"})

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
    rate_usd = 1 / 0.8
    assert rows_usd[0]["market_value_gbp"] == round(100 * rate_usd, 2)
    assert rows_usd[0]["gain_gbp"] == round(10 * rate_usd, 2)
    assert rows_usd[0]["cost_gbp"] == round(90 * rate_usd, 2)
    assert rows_usd[0]["last_price_gbp"] == pytest.approx(100 * rate_usd, rel=1e-4)
    assert rows_usd[0]["market_value_currency"] == "USD"

    rows_eur = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="EUR")
    rate_eur = 1 / 0.9
    assert rows_eur[0]["market_value_gbp"] == round(100 * rate_eur, 2)
    assert rows_eur[0]["gain_gbp"] == round(10 * rate_eur, 2)
    assert rows_eur[0]["cost_gbp"] == round(90 * rate_eur, 2)
    assert rows_eur[0]["last_price_gbp"] == pytest.approx(100 * rate_eur, rel=1e-4)
    assert rows_eur[0]["market_value_currency"] == "EUR"
