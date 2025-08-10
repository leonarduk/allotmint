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
}


def test_run_query_json():
    resp = client.post("/query/run", json=BASE_QUERY)
    assert resp.status_code == 200
    data = resp.json()
    assert any(row["ticker"] == "HFEL.L" for row in data["results"])
    assert "var" in data["results"][0]


def test_export_csv_and_xlsx():
    resp = client.post("/query/run", json={**BASE_QUERY, "format": "csv"})
    assert resp.status_code == 200
    assert "HFEL.L" in resp.text

    resp = client.post("/query/run", json={**BASE_QUERY, "format": "xlsx"})
    assert resp.status_code == 200
    df = pd.read_excel(io.BytesIO(resp.content))
    assert "ticker" in df.columns


def test_save_and_load_query(tmp_path):
    slug = "test-query"
    resp = client.post(f"/query/{slug}", json=BASE_QUERY)
    assert resp.status_code == 200

    resp = client.get(f"/query/{slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tickers"] == BASE_QUERY["tickers"]

    resp = client.get("/query/saved")
    assert slug in resp.json()
