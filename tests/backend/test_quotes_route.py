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
            "quote_type": None,
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


def test_get_quotes_includes_currency_and_quote_type(monkeypatch):
    app = FastAPI()
    app.include_router(quotes.router)

    def fake_Tickers(symbols):
        assert symbols == "^FTSE"
        ticker = type(
            "T",
            (),
            {
                "info": {
                    "regularMarketPrice": 10878.0,
                    "shortName": "FTSE 100",
                    "currency": "GBP",
                    "quoteType": "INDEX",
                }
            },
        )()
        return type("TT", (), {"tickers": {"^FTSE": ticker}})()

    monkeypatch.setattr(quotes.yf, "Tickers", fake_Tickers)

    with TestClient(app) as client:
        resp = client.get("/api/quotes?symbols=%5EFTSE")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["currency"] == "GBP"
    assert data[0]["quote_type"] == "INDEX"


def test_get_quotes_prefers_long_name_over_truncated_short_name(monkeypatch):
    """Yahoo hard-truncates shortName at 31 chars (see #7232) -- e.g. this is
    the exact string yfinance returns for VUSA.L, cut mid-word. longName is
    the untruncated field and must win when both are present."""
    app = FastAPI()
    app.include_router(quotes.router)

    def fake_Tickers(symbols):
        assert symbols == "VUSA.L"
        ticker = type(
            "T",
            (),
            {
                "info": {
                    "regularMarketPrice": 107.02,
                    "shortName": "VANGUARD FUNDS PLC VANGUARD S&P",
                    "longName": "Vanguard S&P 500 UCITS ETF",
                    "currency": "GBp",
                }
            },
        )()
        return type("TT", (), {"tickers": {"VUSA.L": ticker}})()

    monkeypatch.setattr(quotes.yf, "Tickers", fake_Tickers)

    with TestClient(app) as client:
        resp = client.get("/api/quotes?symbols=VUSA.L")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["name"] == "Vanguard S&P 500 UCITS ETF"
    assert data[0]["name"] != "VANGUARD FUNDS PLC VANGUARD S&P"


def test_get_quotes_falls_back_to_short_name_when_long_name_missing(monkeypatch):
    """Some instruments (e.g. GC=F futures) have no longName at all."""
    app = FastAPI()
    app.include_router(quotes.router)

    def fake_Tickers(symbols):
        assert symbols == "GC=F"
        ticker = type(
            "T",
            (),
            {
                "info": {
                    "regularMarketPrice": 4647.10,
                    "shortName": "Gold Dec 26",
                    "longName": None,
                    "currency": "USD",
                }
            },
        )()
        return type("TT", (), {"tickers": {"GC=F": ticker}})()

    monkeypatch.setattr(quotes.yf, "Tickers", fake_Tickers)

    with TestClient(app) as client:
        resp = client.get("/api/quotes?symbols=GC%3DF")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["name"] == "Gold Dec 26"


def test_get_quotes_labels_pence_as_gbx_without_scaling_price(monkeypatch):
    """LSE pence quotes come back from yfinance as the exact-case currency
    "GBp", which is easy to misread as GBP -- a 100x magnitude error (#7219).
    The route must relabel it to the visually distinct "GBX" and must NOT
    scale the price itself."""
    app = FastAPI()
    app.include_router(quotes.router)

    def fake_Tickers(symbols):
        assert symbols == "BP.L"
        ticker = type(
            "T",
            (),
            {
                "info": {
                    "regularMarketPrice": 517.05,
                    "shortName": "BP p.l.c.",
                    "currency": "GBp",
                    "quoteType": "EQUITY",
                }
            },
        )()
        return type("TT", (), {"tickers": {"BP.L": ticker}})()

    monkeypatch.setattr(quotes.yf, "Tickers", fake_Tickers)

    with TestClient(app) as client:
        resp = client.get("/api/quotes?symbols=BP.L")
    assert resp.status_code == 200
    data = resp.json()
    assert data[0]["currency"] == "GBX"
    assert data[0]["price"] == 517.05
