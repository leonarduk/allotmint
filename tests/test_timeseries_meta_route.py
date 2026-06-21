import pandas as pd
import pytest
from fastapi.testclient import TestClient

from backend.config import config


def _make_client(monkeypatch, tmp_path, df):
    def fake_load(*_args, **_kwargs):
        return df.copy()

    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    monkeypatch.setattr("backend.timeseries.cache.load_meta_timeseries_range", fake_load)
    import backend.routes.timeseries_meta as ts_meta
    monkeypatch.setattr(ts_meta, "load_meta_timeseries_range", fake_load)
    from backend.app import create_app

    app = create_app()
    return TestClient(app)


@pytest.mark.parametrize("fmt", ["json", "csv", "html"])
def test_timeseries_meta_formats(fmt, monkeypatch, tmp_path):
    df = pd.DataFrame(
        [
            {
                "Date": "2024-01-01",
                "Open": 1.0,
                "High": 2.0,
                "Low": 0.5,
                "Close": 1.5,
                "Volume": 100,
            }
        ]
    )
    client = _make_client(monkeypatch, tmp_path, df)
    resp = client.get(f"/timeseries/meta?ticker=ABC&exchange=L&format={fmt}")
    assert resp.status_code == 200
    if fmt == "json":
        data = resp.json()
        assert data["ticker"] == "ABC.L"
        assert data["prices"][0]["Date"] == "2024-01-01T00:00:00"
        assert data["prices"][0]["Close"] == 1.5
    elif fmt == "csv":
        assert "Date,Open,High,Low,Close,Volume" in resp.text
        assert "2024-01-01" in resp.text
    else:  # html
        assert "<table" in resp.text
        assert "2024-01-01" in resp.text


def test_timeseries_meta_not_found(monkeypatch, tmp_path):
    df = pd.DataFrame()
    client = _make_client(monkeypatch, tmp_path, df)
    resp = client.get("/timeseries/meta?ticker=ABC&exchange=L")
    assert resp.status_code == 404


def test_timeseries_meta_bad_request(monkeypatch, tmp_path):
    df = pd.DataFrame(
        [
            {
                "Date": "2024-01-01",
                "Open": 1.0,
                "High": 2.0,
                "Low": 0.5,
                "Close": 1.5,
                "Volume": 100,
            }
        ]
    )
    client = _make_client(monkeypatch, tmp_path, df)
    resp = client.get("/timeseries/meta?ticker=&exchange=L")
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "params",
    [
        # XSS in ticker with explicit exchange (case 1 in _resolve_ticker_exchange)
        {"ticker": "<script>alert(1)</script>", "exchange": "L"},
        # XSS via dot-separated ticker (case 2: both parts validated)
        {"ticker": "<script>alert(1)</script>.L"},
        # XSS attempt in exchange parameter
        {"ticker": "ABC", "exchange": "<script>alert(1)</script>"},
    ],
)
def test_timeseries_meta_xss_payload_rejected(params, monkeypatch, tmp_path):
    """XSS payloads in ticker/exchange are rejected; never reflected verbatim (CodeQL #276)."""
    df = pd.DataFrame(
        [{"Date": "2024-01-01", "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": 1.5, "Volume": 100}]
    )
    client = _make_client(monkeypatch, tmp_path, df)
    resp = client.get("/timeseries/meta", params=params)
    assert resp.status_code == 400
    assert "application/json" in resp.headers.get("content-type", "")
    assert "<script>" not in resp.text.lower()
