from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import quotes


def test_get_quotes_includes_name(monkeypatch):
    app = FastAPI()
    app.include_router(quotes.router)

    def fake_Tickers(symbols):
        assert symbols == "AAA"
        ticker = type("T", (), {"info": {"regularMarketPrice": 100.0, "shortName": "Acme"}})()
        return type("TT", (), {"tickers": {"AAA": ticker}})()

    monkeypatch.setattr(quotes.yf, "Tickers", fake_Tickers)

    with TestClient(app) as client:
        resp = client.get("/api/quotes?symbols=AAA")
    assert resp.status_code == 200
    assert resp.json() == [
        {
            "symbol": "AAA",
            "price": 100.0,
            "open": None,
            "high": None,
            "low": None,
            "previous_close": None,
            "volume": None,
            "timestamp": None,
            "timezone": None,
            "market_state": None,
            "name": "Acme",
        }
    ]
