from fastapi.testclient import TestClient

from backend.app import create_app


def test_quotes_route_returns_data(monkeypatch):
    """Ensure the /api/quotes endpoint returns structured data."""

    class DummyTicker:
        fast_info = {
            "longName": "Apple Inc.",
            "lastPrice": 190.0,
            "open": 189.0,
            "dayHigh": 191.0,
            "dayLow": 188.0,
            "previousClose": 188.5,
            "volume": 100,
            "regularMarketTime": 0,
        }

    class DummyTickers:
        def __init__(self, symbols: str) -> None:
            self.tickers = {"AAPL": DummyTicker()}

    monkeypatch.setattr("yfinance.Tickers", lambda symbols: DummyTickers(symbols))

    app = create_app()
    client = TestClient(app)
    resp = client.get("/api/quotes", params={"symbols": "AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["symbol"] == "AAPL"
    assert data[0]["last"] == 190.0
