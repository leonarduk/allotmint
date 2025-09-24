import importlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.events as events_module


def reload_events_module():
    global events_module
    events_module = importlib.reload(events_module)
    return events_module


def create_client() -> TestClient:
    app = FastAPI()
    app.include_router(events_module.router)
    return TestClient(app)


def test_list_events_filters_extra_fields(monkeypatch, tmp_path):
    fixture = tmp_path / "custom.json"
    fixture.write_text(
        json.dumps([{"id": "custom", "name": "Custom", "ignored": "value"}])
    )

    with monkeypatch.context() as patcher:
        patcher.setattr(events_module, "_events_path", fixture, raising=False)
        reload_events_module()
        client = create_client()

        response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == [{"id": "custom", "name": "Custom"}]

    reload_events_module()


def test_list_events_missing_file(monkeypatch, tmp_path):
    missing = tmp_path / "missing.json"

    with monkeypatch.context() as patcher:
        patcher.setattr(events_module, "_events_path", missing, raising=False)
        reload_events_module()
        client = create_client()

        response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == []

    reload_events_module()
