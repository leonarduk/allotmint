from decimal import Decimal
from unittest.mock import MagicMock

import pytest
import requests

from backend.tasks import quotes


class DummyResponse:
    """Simple stand-in for ``requests.Response``."""

    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError("boom")


def test_fetch_quote_success(monkeypatch):
    monkeypatch.setattr(quotes.config, "alpha_vantage_enabled", True)

    def fake_get(url, params=None, timeout=0):
        assert url == quotes.BASE_URL
        assert params["symbol"] == "ibm"
        payload = {"Global Quote": {"05. price": "123.45", "06. volume": "100"}}
        return DummyResponse(payload)

    monkeypatch.setattr(quotes.requests, "get", fake_get)
    result = quotes.fetch_quote("ibm")
    assert result["symbol"] == "IBM"
    assert result["price"] == Decimal("123.45")
    assert result["volume"] == 100
    assert isinstance(result["time"], str)


def test_fetch_quote_http_error(monkeypatch):
    monkeypatch.setattr(quotes.config, "alpha_vantage_enabled", True)

    def fake_get(*_args, **_kwargs):
        return DummyResponse({}, status_code=500)

    monkeypatch.setattr(quotes.requests, "get", fake_get)
    with pytest.raises(requests.HTTPError):
        quotes.fetch_quote("IBM")


def test_save_quotes_filters_none(monkeypatch):
    table = MagicMock()
    resource = MagicMock()
    resource.Table.return_value = table
    monkeypatch.setattr(quotes.boto3, "resource", lambda _service: resource)

    item = {"symbol": "AAPL", "price": Decimal("1"), "volume": None, "time": "t"}
    quotes.save_quotes([item], table_name="T")

    resource.Table.assert_called_once_with("T")
    table.put_item.assert_called_once_with(Item={"symbol": "AAPL", "price": Decimal("1"), "time": "t"})


def test_lambda_handler_uses_event_symbols(monkeypatch):
    monkeypatch.setenv("SYMBOLS", "")
    fetched = []

    def fake_fetch(sym):
        fetched.append(sym)
        return {"symbol": sym}

    saved = []

    def fake_save(items):
        saved.extend(items)

    monkeypatch.setattr(quotes, "fetch_quote", fake_fetch)
    monkeypatch.setattr(quotes, "save_quotes", fake_save)

    result = quotes.lambda_handler({"symbols": ["AAPL", "MSFT"]}, None)
    assert result == {"count": 2}
    assert fetched == ["AAPL", "MSFT"]
    assert saved == [{"symbol": "AAPL"}, {"symbol": "MSFT"}]


def test_lambda_handler_reads_env_symbols(monkeypatch):
    monkeypatch.setenv("SYMBOLS", "GOOG, AMZN")

    fetched = []

    def fake_fetch(sym):
        fetched.append(sym)
        return {"symbol": sym}

    saved = []

    def fake_save(items):
        saved.extend(items)

    monkeypatch.setattr(quotes, "fetch_quote", fake_fetch)
    monkeypatch.setattr(quotes, "save_quotes", fake_save)

    result = quotes.lambda_handler({}, None)
    assert result == {"count": 2}
    assert fetched == ["GOOG", "AMZN"]
    assert saved == [{"symbol": "GOOG"}, {"symbol": "AMZN"}]
