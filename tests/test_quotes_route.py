from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routes import quotes as quotes_module


def test_quotes_returns_502_on_yfinance_error(monkeypatch):
    def mock_tickers(symbols):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.routes.quotes.yf.Tickers", mock_tickers)
    monkeypatch.setattr(quotes_module.config, "offline_mode", False)

    app = create_app()
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    resp = client.get("/api/quotes?symbols=PFE")
    assert resp.status_code == 502
    assert resp.json()["detail"] == "Upstream provider failure"
