from __future__ import annotations

from pathlib import Path

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config as config_module
from backend.common import analytics_store
from backend.routes.analytics import router as analytics_router



@pytest.fixture
def analytics_client(tmp_path: Path):
    cfg = config_module.config
    original_repo_root = cfg.repo_root
    original_accounts_root = cfg.accounts_root
    original_disable_auth = cfg.disable_auth

    cfg.repo_root = tmp_path
    cfg.accounts_root = tmp_path / "data" / "accounts"
    cfg.disable_auth = True
    (tmp_path / "data" / "accounts").mkdir(parents=True, exist_ok=True)

    app = FastAPI()
    app.include_router(analytics_router)
    analytics_store.clear_events()
    client = TestClient(app)

    try:
        yield client, tmp_path
    finally:
        analytics_store.clear_events()
        cfg.repo_root = original_repo_root
        cfg.accounts_root = original_accounts_root
        cfg.disable_auth = original_disable_auth


def test_log_event_persists_and_summarises(analytics_client) -> None:
    client, tmp_path = analytics_client

    payloads = [
        {"source": "trail", "event": "view", "user": "alice"},
        {
            "source": "trail",
            "event": "task_completed",
            "user": "alice",
            "metadata": {"task": "demo"},
        },
        {"source": "virtual_portfolio", "event": "view", "user": "bob"},
        {"source": "virtual_portfolio", "event": "create", "user": "bob"},
    ]

    for payload in payloads:
        res = client.post("/analytics/events", json=payload)
        assert res.status_code == 200
        assert res.json()["status"] == "ok"

    trail_funnel = client.get("/analytics/funnels/trail")
    assert trail_funnel.status_code == 200
    body = trail_funnel.json()
    assert body["total_events"] == 2
    assert body["unique_users"] == 1
    assert body["steps"][0]["event"] == "view"
    assert body["steps"][0]["count"] == 1
    assert body["steps"][2]["event"] == "task_completed"
    assert body["steps"][2]["count"] == 1
    assert body["first_event_at"] is not None
    assert body["last_event_at"] is not None

    virtual_funnel = client.get("/analytics/funnels/virtual_portfolio")
    assert virtual_funnel.status_code == 200
    vf = virtual_funnel.json()
    assert vf["total_events"] == 2
    assert vf["unique_users"] == 1
    steps = {step["event"]: step["count"] for step in vf["steps"]}
    assert steps["view"] == 1
    assert steps["create"] == 1

    events_file = tmp_path / "data" / "analytics" / "events.jsonl"
    assert events_file.exists()
    contents = events_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == len(payloads)


def test_rejects_unknown_events(analytics_client) -> None:
    client, _ = analytics_client

    res = client.post(
        "/analytics/events",
        json={"source": "trail", "event": "unknown"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Unsupported event for source"

    res = client.post(
        "/analytics/events",
        json={"source": "unknown", "event": "view"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Unknown analytics source"
