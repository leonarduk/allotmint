from fastapi.testclient import TestClient

from backend.app import create_app


def test_quotes_returns_502_on_yfinance_error(monkeypatch):
    def mock_tickers(symbols):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", mock_tickers)

    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    resp = client.get("/api/quotes?symbols=AAPL")
    assert resp.status_code == 502
    assert resp.json()["detail"].startswith("Failed to fetch quotes")
