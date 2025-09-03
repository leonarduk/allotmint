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
    monkeypatch.setattr(ts_meta.pd, "to_datetime", lambda x: x)
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
