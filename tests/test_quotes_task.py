from decimal import Decimal

import backend.tasks.quotes as quotes


def test_save_quotes_writes_items(quotes_table):
    item = {"symbol": "AAPL", "price": Decimal("1"), "volume": 10, "time": "t"}
    quotes.save_quotes([item])
    resp = quotes_table.scan()
    assert resp["Count"] == 1
    assert resp["Items"][0]["symbol"] == "AAPL"


def test_lambda_handler_saves_quotes(quotes_table, monkeypatch):
    monkeypatch.setattr(
        quotes,
        "fetch_quote",
        lambda sym: {"symbol": sym, "price": Decimal("1"), "volume": 1, "time": "t"},
    )
    result = quotes.lambda_handler({"symbols": ["AAPL", "MSFT"]}, None)
    assert result == {"count": 2}
    symbols = {item["symbol"] for item in quotes_table.scan()["Items"]}
    assert symbols == {"AAPL", "MSFT"}
