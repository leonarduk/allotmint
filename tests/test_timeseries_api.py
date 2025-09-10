import pandas as pd
import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

import yfinance as yf
from backend.app import create_app
from backend.config import config


def _client(monkeypatch, history_result):
    """Create TestClient with patched yfinance history."""
    # Avoid startup side effects
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)
    monkeypatch.setattr(config, "disable_auth", True)

    def fake_ticker(_ticker):
        def history(*_args, **_kwargs):
            if isinstance(history_result, Exception):
                raise history_result
            return history_result.copy()

        return SimpleNamespace(history=history)

    monkeypatch.setattr(yf, "Ticker", fake_ticker)

    app = create_app()
    # Ensure timeseries API router is available
    from backend.timeseries.timeseries_api import router as ts_router
    app.include_router(ts_router)
    return TestClient(app)


def sample_df():
    df = pd.DataFrame(
        {
            "Open": [1.0],
            "High": [1.5],
            "Low": [0.5],
            "Close": [1.2],
            "Volume": [100],
        },
        index=pd.to_datetime(["2024-01-01"]),
    )
    df.index.name = "Date"
    return df


def test_timeseries_json(monkeypatch):
    client = _client(monkeypatch, sample_df())
    resp = client.get("/timeseries/TEST?fmt=json")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert data[0]["Ticker"] == "TEST"
    assert "Date" in data[0]


def test_timeseries_html(monkeypatch):
    client = _client(monkeypatch, sample_df())
    resp = client.get("/timeseries/TEST?fmt=html")
    assert resp.status_code == 200
    assert "<table" in resp.text
    assert "TEST" in resp.text


def test_timeseries_csv(monkeypatch):
    client = _client(monkeypatch, sample_df())
    resp = client.get("/timeseries/TEST")
    assert resp.status_code == 200
    assert "attachment; filename=" in resp.headers.get("Content-Disposition", "")
    body = resp.text
    assert "Ticker,Date,Open,High,Low,Close,Volume" in body
    assert "TEST" in body


def test_timeseries_not_found(monkeypatch):
    empty_df = pd.DataFrame()
    client = _client(monkeypatch, empty_df)
    resp = client.get("/timeseries/TEST")
    assert resp.status_code == 404
