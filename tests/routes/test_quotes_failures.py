import pytest
from types import SimpleNamespace
from fastapi.testclient import TestClient

from backend.app import create_app


@pytest.fixture
def client():
    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_quotes_returns_502_on_yfinance_error(monkeypatch, client):
    def mock_tickers(symbols):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", mock_tickers)

    resp = client.get("/api/quotes?symbols=AAPL")
    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("Failed to fetch quotes")


def test_quotes_excludes_missing_regular_market_price(monkeypatch, client):
    class FakeTicker:
        def __init__(self, info):
            self.info = info

    def fake_tickers(symbols):
        return SimpleNamespace(
            tickers={
                "AAPL": FakeTicker({"regularMarketPrice": 100.0}),
                "MSFT": FakeTicker({}),
            }
        )

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", fake_tickers)

    resp = client.get("/api/quotes?symbols=AAPL,MSFT")
    assert resp.status_code == 200
    data = resp.json()
    assert [item["symbol"] for item in data] == ["AAPL"]


def test_quotes_no_symbols_returns_empty_list(client):
    resp = client.get("/api/quotes?symbols=")
    assert resp.status_code == 200
    assert resp.json() == []
