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
                    {"ticker": "ABC", "units": 1, "market_value_gbp": 100, "gain_gbp": 10}
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

        return pd.DataFrame({"Date": [start], "Rate": [0.5]})

    monkeypatch.setattr(portfolio_utils, "fetch_fx_rate_range", fake_fetch)

    rows = portfolio_utils.aggregate_by_ticker(portfolio, base_currency="USD")

    assert rows[0]["market_value_gbp"] == 200.0
    assert rows[0]["market_value_currency"] == "USD"
