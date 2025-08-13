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
    resp = client.post("/custom-query/run", json=BASE_QUERY)
    assert resp.status_code == 200
    data = resp.json()
    assert any(row["ticker"] == "HFEL.L" for row in data["results"])
    assert "var" in data["results"][0]


def test_run_query_price_position(monkeypatch):
    from backend.routes import query as query_mod

    df = pd.DataFrame(
        {"Close": [1.0, 2.0]}, index=pd.date_range("2025-01-01", periods=2)
    )

    monkeypatch.setattr(
        query_mod,
        "load_meta_timeseries_range",
        lambda *a, **k: df,
    )

    monkeypatch.setattr(
        query_mod,
        "list_portfolios",
        lambda: [
            {
                "owner": "alice",
                "accounts": [
                    {"holdings": [{"ticker": "ABC.L", "units": 5}]}
                ],
            }
        ],
    )

    q = {
        "start": "2025-01-01",
        "end": "2025-01-02",
        "tickers": ["ABC.L"],
        "metrics": ["price", "position"],
        "granularity": "daily",
    }

    resp = client.post("/custom-query/run", json=q)
    assert resp.status_code == 200
    data = resp.json()["results"][0]
    assert data["price"][0]["close"] == 1.0
    assert data["position"][0]["units"] == 5

def test_save_and_load_query(tmp_path):
    slug = "test-query"
    resp = client.post(f"/custom-query/{slug}", json=BASE_QUERY)
    assert resp.status_code == 200

    resp = client.get(f"/custom-query/{slug}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["tickers"] == BASE_QUERY["tickers"]

    resp = client.get("/custom-query/saved")
    assert slug in resp.json()
