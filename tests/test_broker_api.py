import logging
from datetime import datetime

import pytest
import requests

from backend.common.url_validator import InvalidExternalURLError
from backend.integrations.broker_api import AlpacaAPI


def test_recent_trades_parsing_and_headers(monkeypatch):
    api = AlpacaAPI(api_key="key", api_secret="secret")
    since = datetime(2024, 1, 1)
    called = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return [
                {
                    "transaction_time": "2024-03-05T10:00:00Z",
                    "symbol": "ABC",
                    "qty": 2,
                    "price": 42.5,
                }
            ]

    def fake_get(url, params=None, headers=None, timeout=None, **kwargs):
        called["url"] = url
        called["params"] = params
        called["headers"] = headers
        called["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(requests, "get", fake_get)
    trades = api.recent_trades(since)

    assert trades == [
        {"date": "2024-03-05", "ticker": "ABC", "units": "2", "price": "42.5"}
    ]
    assert (
        called["url"]
        == "https://paper-api.alpaca.markets/v2/account/activities/trades"
    )
    assert called["params"] == {"after": since.isoformat()}
    assert called["headers"] == {
        "APCA-API-KEY-ID": "key",
        "APCA-API-SECRET-KEY": "secret",
    }


def test_recent_trades_exception(monkeypatch, caplog):
    api = AlpacaAPI(api_key="key", api_secret="secret")
    since = datetime(2024, 1, 1)

    def fake_get(*args, **kwargs):
        raise RuntimeError("network error")

    monkeypatch.setattr(requests, "get", fake_get)
    with caplog.at_level(logging.WARNING):
        trades = api.recent_trades(since)

    assert trades == []
    assert any("Alpaca trade fetch failed" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    "base_url",
    [
        pytest.param("https://169.254.169.254", id="aws_metadata"),
        pytest.param("https://127.0.0.1", id="loopback"),
        pytest.param("https://10.0.0.1", id="rfc1918"),
        pytest.param("https://192.168.1.1", id="rfc1918_192"),
        pytest.param("https://localhost", id="localhost"),
    ],
)
def test_recent_trades_rejects_private_base_url(base_url: str) -> None:
    api = AlpacaAPI(api_key="key", api_secret="secret", base_url=base_url)
    with pytest.raises(InvalidExternalURLError):
        api.recent_trades(datetime(2024, 1, 1))
