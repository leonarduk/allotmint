import json
from pathlib import Path

import pytest

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import config


@pytest.fixture
def temp_queries_dir(tmp_path, monkeypatch):
    from backend.routes import query as query_routes

    queries_dir = tmp_path / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(query_routes, "QUERIES_DIR", queries_dir)
    return queries_dir


def test_custom_query_routes_fallback_to_local(monkeypatch):
    monkeypatch.setattr(config, "app_env", "aws")
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    queries_dir = Path(config.data_root) / "queries"
    queries_dir.mkdir(parents=True, exist_ok=True)

    fallback_slug = "fallback-slug"
    fallback_path = queries_dir / f"{fallback_slug}.json"
    if fallback_path.exists():
        fallback_path.unlink()

    app = create_app()

    try:
        with TestClient(app) as client:
            resp = client.get("/custom-query/demo-slug")
            assert resp.status_code == 200
            assert resp.json()["tickers"] == ["PFE"]

            payload = {
                "start": "2020-01-01",
                "end": "2020-01-02",
                "tickers": ["MSFT"],
                "metrics": [],
            }

            save_resp = client.post(f"/custom-query/{fallback_slug}", json=payload)
            assert save_resp.status_code == 200
            assert save_resp.json() == {"saved": fallback_slug}
            assert json.loads(fallback_path.read_text())["tickers"] == ["MSFT"]

            get_resp = client.get(f"/custom-query/{fallback_slug}")
            assert get_resp.status_code == 200
            assert get_resp.json()["tickers"] == ["MSFT"]
    finally:
        if fallback_path.exists():
            fallback_path.unlink()


def test_list_saved_queries_returns_slugs_by_default(monkeypatch, temp_queries_dir):
    monkeypatch.setattr(config, "app_env", None)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)

    (temp_queries_dir / "beta.json").write_text(json.dumps({"name": "Beta"}))
    (temp_queries_dir / "alpha.json").write_text(json.dumps({"name": "Alpha"}))

    app = create_app()

    with TestClient(app) as client:
        resp = client.get("/custom-query/saved")
        assert resp.status_code == 200
        assert resp.json() == ["alpha", "beta"]

        detailed_resp = client.get("/custom-query/saved?detailed=1")
        assert detailed_resp.status_code == 200
        assert detailed_resp.json() == [
            {"id": "alpha", "name": "Alpha", "params": {}},
            {"id": "beta", "name": "Beta", "params": {}},
        ]
