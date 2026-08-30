from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import quotes


def test_get_quotes_includes_name(monkeypatch):
    app = FastAPI()
    app.include_router(quotes.router)

    def fake_Tickers(symbols):
        assert symbols == "AAA"
        ticker = type(
            "T",
            (),
            {
                "info": {
                    "regularMarketPrice": 100.0,
                    "shortName": "Acme",
                    "currency": "USD",
                }
            },
        )()
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
            # shortName is used here only because longName is absent --
            # longName is preferred when both are present (#7218).
            "name": "Acme",
            "currency": "USD",
        }
    ]


def test_get_quotes_prefers_long_name_over_short_name(monkeypatch):
    app = FastAPI()
    app.include_router(quotes.router)

    def fake_Tickers(symbols):
        ticker = type(
            "T",
            (),
            {
                "info": {
                    "regularMarketPrice": 126.67,
                    "shortName": "iShares Core MSCI World UCITS E",
                    "longName": "iShares Core MSCI World UCITS ETF USD Acc",
                }
            },
        )()
        return type("TT", (), {"tickers": {"IWDA.AS": ticker}})()

    monkeypatch.setattr(quotes.yf, "Tickers", fake_Tickers)

    with TestClient(app) as client:
        resp = client.get("/api/quotes?symbols=IWDA.AS")
    assert resp.status_code == 200
    assert resp.json()[0]["name"] == "iShares Core MSCI World UCITS ETF USD Acc"
