from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routes.query import Metric

client = TestClient(create_app())

BASE_QUERY = {
    "start": "2025-01-01",
    "end": "2025-01-10",
    "tickers": ["HFEL.L"],
    "metrics": [Metric.VAR, Metric.META],
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

    resp = client.get("/custom-query/saved")
    assert slug in resp.json()


def test_unknown_metric_rejected():
    resp = client.post(
        "/custom-query/run",
        json={**BASE_QUERY, "metrics": ["bogus"]},
    )
    assert resp.status_code == 422
