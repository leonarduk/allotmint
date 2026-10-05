import importlib
import json
import logging

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
    fixture.write_text(json.dumps([{"id": "custom", "name": "Custom", "ignored": "value"}]))

    with monkeypatch.context() as patcher:
        patcher.setattr(events_module, "_events_path", fixture, raising=False)
        reload_events_module()
        client = create_client()

        response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == [{"id": "custom", "name": "Custom"}]

    reload_events_module()


def test_list_events_missing_file(monkeypatch, tmp_path, caplog):
    missing = tmp_path / "missing.json"

    with monkeypatch.context() as patcher, caplog.at_level(logging.WARNING):
        patcher.setattr(events_module, "_events_path", missing, raising=False)
        reload_events_module()
        client = create_client()

        response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == []
    assert "Scenario events file not found" in caplog.text

    reload_events_module()


def test_list_events_falls_back_to_bundled_catalogue(monkeypatch, tmp_path):
    # data_root without events.json (e.g. a separate user-data checkout)
    with monkeypatch.context() as patcher:
        patcher.delattr(events_module, "_events_path", raising=False)
        patcher.setattr(events_module.config, "data_root", tmp_path)
        reload_events_module()
        client = create_client()

        response = client.get("/events")

    assert response.status_code == 200
    ids = [e["id"] for e in response.json()]
    assert ids, "expected bundled events when data_root has no events.json"
    assert "covid-2020" in ids

    reload_events_module()


def test_list_events_reads_market_events_layout(monkeypatch, tmp_path):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    (events_dir / "market_events.json").write_text(
        json.dumps(
            {
                "proxy_index": {"ticker": "SPY"},
                "events": [
                    {"date": "2020-03-16", "description": "COVID-19 volatility"},
                ],
            }
        )
    )

    with monkeypatch.context() as patcher:
        patcher.delattr(events_module, "_events_path", raising=False)
        patcher.setattr(events_module.config, "data_root", tmp_path)
        reload_events_module()
        client = create_client()

        response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == [{"id": "2020-03-16", "name": "2020-03-16: COVID-19 volatility"}]

    reload_events_module()


def test_list_events_malformed_file_degrades_to_empty(monkeypatch, tmp_path, caplog):
    bad = tmp_path / "events.json"
    bad.write_text(json.dumps({"events": [{"date": "2020-03-16"}]}))  # no description

    with monkeypatch.context() as patcher, caplog.at_level(logging.ERROR):
        patcher.setattr(events_module, "_events_path", bad, raising=False)
        reload_events_module()
        client = create_client()

        response = client.get("/events")

    assert response.status_code == 200
    assert response.json() == []
    assert "unreadable or malformed" in caplog.text

    reload_events_module()


def test_get_event_returns_bundled_date_and_proxy():
    event = events_module.get_event("covid-2020")
    assert event["date"] and event["proxy_index"]
    assert events_module.get_event("gfc-2008")["date"] != event["date"]
    assert events_module.get_event("missing") is None


def test_event_details_market_layout_qualifies_bare_us_tickers():
    details = events_module._event_details(  # pylint: disable=protected-access
        {
            "proxy_index": {"ticker": "SPY"},
            "events": [
                {"date": "2020-03-16", "description": "COVID"},
                {"date": "2022-09-26", "description": "Gilts", "reference_index": "ISF.L"},
            ],
        }
    )
    assert details["2020-03-16"]["proxy_index"] == "SPY.N"
    assert details["2022-09-26"]["proxy_index"] == "ISF.L"
    assert details["2020-03-16"]["date"] == "2020-03-16"
