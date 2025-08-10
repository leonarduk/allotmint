import pytest
from fastapi.testclient import TestClient

from backend.app import create_app


def test_timeseries_edit_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOTMINT_SKIP_SNAPSHOT_WARM", "true")
    monkeypatch.setenv("TIMESERIES_CACHE_BASE", str(tmp_path))
    app = create_app()
    client = TestClient(app)

    data = [
        {
            "Date": "2024-01-01",
            "Open": 1.0,
            "High": 2.0,
            "Low": 0.5,
            "Close": 1.5,
            "Volume": 100,
        },
        {
            "Date": "2024-01-02",
            "Open": 1.1,
            "High": 2.1,
            "Low": 0.6,
            "Close": 1.6,
            "Volume": 110,
        },
    ]
    resp = client.post("/timeseries/edit?ticker=ABC&exchange=L", json=data)
    assert resp.status_code == 200
    assert resp.json()["rows"] == 2

    resp = client.get("/timeseries/edit?ticker=ABC&exchange=L")
    assert resp.status_code == 200
    returned = resp.json()
    assert len(returned) == 2
    assert returned[0]["Open"] == 1.0
