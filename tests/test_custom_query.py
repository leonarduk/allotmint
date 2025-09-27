from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.config import config
import backend.timeseries.cache as ts_cache
from backend.routes.query import Metric


@pytest.fixture
def client():
    orig_root = config.data_root
    orig_cache_base = ts_cache._CACHE_BASE
    test_data_root = Path(__file__).resolve().parent / "data"
    config.data_root = test_data_root
    ts_cache._CACHE_BASE = str(test_data_root / "timeseries")
    from backend.app import create_app

    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    try:
        yield client
    finally:
        config.data_root = orig_root
        ts_cache._CACHE_BASE = orig_cache_base

BASE_QUERY = {
    "start": "2025-01-01",
    "end": "2025-01-10",
    "tickers": ["HFEL.L"],
    "metrics": [Metric.VAR, Metric.META],
}


def test_run_query_json(client):
    resp = client.post("/custom-query/run", json=BASE_QUERY)
    assert resp.status_code == 200
    data = resp.json()
    assert any(row["ticker"] == "HFEL.L" for row in data["results"])
    assert "var" in data["results"][0]


def test_save_and_load_query(client, tmp_path):
    slug = "test-query"
    resp = client.post(f"/custom-query/{slug}", json=BASE_QUERY)
    assert resp.status_code == 200

    resp = client.get(f"/custom-query/{slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tickers"] == BASE_QUERY["tickers"]

    expected_params = dict(data)
    expected_params.pop("name", None)

    resp = client.get("/custom-query/saved", params={"detailed": "true"})
    saved_entries = resp.json()
    matching_entry = next((entry for entry in saved_entries if entry["id"] == slug), None)
    assert matching_entry is not None
    assert matching_entry["name"] == slug
    assert matching_entry["params"] == expected_params


def test_unknown_metric_rejected(client):
    resp = client.post(
        "/custom-query/run",
        json={**BASE_QUERY, "metrics": ["bogus"]},
    )
    assert resp.status_code == 422
