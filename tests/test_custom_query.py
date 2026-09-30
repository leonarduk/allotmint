import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.timeseries.cache as ts_cache
from backend.config import config
from backend.routes.query import Metric


@pytest.fixture
def client(monkeypatch, tmp_path):
    # Work on a copy of the checked-in fixtures: a query run caches the
    # tickers it fetches, and saving a query writes a file, which used to
    # land in tests/data and the real data/queries respectively.
    test_data_root = tmp_path / "data"
    shutil.copytree(Path(__file__).resolve().parent / "data", test_data_root)
    monkeypatch.setattr(config, "data_root", test_data_root)
    monkeypatch.setattr(ts_cache, "_CACHE_BASE", str(test_data_root / "timeseries"))
    from backend.routes import query as query_module

    monkeypatch.setattr(query_module, "QUERIES_DIR", test_data_root / "queries")
    # With no owners filter a query also prices every ticker held in every
    # portfolio (_resolve_tickers). These tests only assert on the tickers
    # they name, which the fixture cache holds; the demo holdings are not in
    # it, so they used to be fetched live - and only when an earlier test had
    # already turned the cache module's OFFLINE_MODE off.
    monkeypatch.setattr(query_module, "list_portfolios", lambda: [])
    from backend.app import create_app

    client = TestClient(create_app())
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    yield client


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

    resp = client.get("/custom-query/saved")
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
