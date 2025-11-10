import pandas as pd
from datetime import datetime, timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.instrument as instrument


def test_intraday_route(monkeypatch):
    class FakeTicker:
        def history(self, period, interval):
            assert period == "2d"
            assert interval == "5m"
            idx = pd.date_range(datetime(2024, 1, 1), periods=3, freq="5min")
            idx.name = "Datetime"
            return pd.DataFrame({"Close": [1.0, 2.0, 3.0]}, index=idx)

    captured = {}
    def fake_ticker(t):
        captured["ticker"] = t
        return FakeTicker()
    monkeypatch.setattr(instrument, "yf", type("YF", (), {"Ticker": fake_ticker}))

    app = FastAPI()
    app.include_router(instrument.router)
    client = TestClient(app)
    resp = client.get("/instrument/intraday?ticker=PFE")
    assert resp.status_code == 200
    assert captured["ticker"] == "PFE"
    data = resp.json()
    assert data["ticker"] == "PFE"
    assert len(data["prices"]) == 3
    assert all("timestamp" in p and "close" in p for p in data["prices"])
