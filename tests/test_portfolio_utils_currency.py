import backend.common.portfolio_utils as portfolio_utils


def test_currency_from_instrument_meta(monkeypatch):
    portfolio = {"accounts": [{"holdings": [{"ticker": "ABC", "units": 1}]}]}

    monkeypatch.setattr(portfolio_utils, "get_instrument_meta", lambda t: {"currency": "USD"})

    rows = portfolio_utils.aggregate_by_ticker(portfolio)

    assert len(rows) == 1
    assert rows[0]["currency"] == "USD"
