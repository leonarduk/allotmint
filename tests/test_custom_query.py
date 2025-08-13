import io

import pandas as pd
from fastapi.testclient import TestClient

from backend.app import create_app

client = TestClient(create_app())

BASE_QUERY = {
    "start": "2025-01-01",
    "end": "2025-01-10",
    "tickers": ["HFEL.L"],
    "metrics": ["var", "meta"],
    "columns": ["ticker", "var"],
    "sort_key": "var",
    "sort_asc": False,
}


def test_run_query_json():
    resp = client.post("/custom-query/run", json=BASE_QUERY)
    assert resp.status_code == 200
    data = resp.json()
    assert any(row["ticker"] == "HFEL.L" for row in data["results"])
    assert "var" in data["results"][0]

def test_save_and_load_query(tmp_path):
    slug = "test-query"
    resp = client.post(f"/custom-query/{slug}", json=BASE_QUERY)
    assert resp.status_code == 200

    resp = client.get(f"/custom-query/{slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tickers"] == BASE_QUERY["tickers"]
    assert data["columns"] == BASE_QUERY["columns"]
    assert data["sort_key"] == BASE_QUERY["sort_key"]
    assert data["sort_asc"] == BASE_QUERY["sort_asc"]

    resp = client.get("/custom-query/saved")
    assert slug in resp.json()
