import pandas as pd
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from backend.app import create_app
from backend.config import config


def _make_df():
    return pd.DataFrame(
        {
            "Date": ["2024-01-01", "2024-01-02"],
            "Open": [1.0, 2.0],
            "High": [1.0, 2.0],
            "Low": [1.0, 2.0],
            "Close": [1.0, 2.0],
            "Volume": [100, 200],
            "Ticker": ["ABC", "ABC"],
            "Source": ["Test", "Test"],
        }
    )


@pytest.mark.parametrize("fmt", ["html", "json", "csv"])
def test_meta_timeseries_formats(monkeypatch, fmt):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    df = _make_df()
    with patch(
        "backend.routes.timeseries_meta.load_meta_timeseries_range", return_value=df
    ), patch("backend.routes.timeseries_meta.pd.to_datetime", lambda x: x):
        client = TestClient(app)
        resp = client.get(
            "/timeseries/meta",
            params={"ticker": "ABC", "exchange": "L", "format": fmt, "days": 1},
        )
    assert resp.status_code == 200
    if fmt == "html":
        assert "<table" in resp.text
        assert "ABC.L" in resp.text
    elif fmt == "json":
        data = resp.json()
        assert data["ticker"] == "ABC.L"
        assert len(data["prices"]) == 2
    else:  # csv
        text = resp.text.strip().splitlines()
        assert text[0].startswith("Date,Open,High,Low,Close,Volume,Ticker,Source")
        assert "ABC" in text[1]


def test_meta_timeseries_no_data(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with patch(
        "backend.routes.timeseries_meta.load_meta_timeseries_range",
        return_value=pd.DataFrame(),
    ):
        client = TestClient(app)
        resp = client.get(
            "/timeseries/meta", params={"ticker": "ABC", "exchange": "L", "days": 1}
        )
    assert resp.status_code == 404


def test_meta_timeseries_unresolved_exchange(monkeypatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    app = create_app()
    with patch(
        "backend.routes.timeseries_meta.instrument_api._resolve_full_ticker",
        return_value=None,
    ):
        client = TestClient(app)
        resp = client.get("/timeseries/meta", params={"ticker": "ABC"})
    assert resp.status_code == 400
