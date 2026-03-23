from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_quotes_returns_502_on_yfinance_error(monkeypatch, client, caplog):
    def mock_tickers(symbols):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", mock_tickers)

    with caplog.at_level("ERROR", logger="backend.errors"):
        resp = client.get("/api/quotes?symbols=PFE")

    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("Failed to fetch quotes")
    record = caplog.records[-1]
    assert record.error_code == "provider_failure"
    assert record.provider == "yfinance"
    assert record.symbols == ["PFE"]
    assert record.path == "/api/quotes"


def test_quotes_excludes_missing_regular_market_price(monkeypatch, client):
    class FakeTicker:
        def __init__(self, info):
            self.info = info

    def fake_tickers(symbols):
        return SimpleNamespace(
            tickers={
                "PFE": FakeTicker({"regularMarketPrice": 100.0}),
                "MSFT": FakeTicker({}),
            }
        )

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)

    resp = client.get("/api/quotes?symbols=PFE,MSFT")
    assert resp.status_code == 200
    data = resp.json()
    assert [item["symbol"] for item in data] == ["PFE"]


def test_quotes_no_symbols_returns_empty_list(client):
    resp = client.get("/api/quotes?symbols=")
    assert resp.status_code == 200
    assert resp.json() == []
