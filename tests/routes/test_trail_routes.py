import importlib

import pytest
from fastapi.testclient import TestClient

from backend.auth import get_current_user
from backend.config import config


@pytest.mark.parametrize("disable_auth", [True, False])
def test_trail_routes(tmp_path, monkeypatch, disable_auth):
    monkeypatch.setenv("TRAIL_URI", f"file://{tmp_path/'trail.json'}")
    monkeypatch.setattr(config, "disable_auth", disable_auth)

    import backend.quests.trail as trail_module
    import backend.routes.trail as trail_route_module
    import backend.app as app_mod
    importlib.reload(trail_module)
    importlib.reload(trail_route_module)
    importlib.reload(app_mod)
    app = app_mod.create_app()
    if not disable_auth:
        app.dependency_overrides[get_current_user] = lambda: "demo"

    with TestClient(app) as client:
        resp = client.get("/trail")
        assert resp.status_code == 200
        payload = resp.json()
        assert set(payload) >= {"tasks", "xp", "streak", "daily_totals", "today"}
        assert payload["xp"] == 0
        assert payload["streak"] == 0

        resp = client.post("/trail/unknown/complete")
        assert resp.status_code == 404

        for index, task_id in enumerate(trail_module.DAILY_TASK_IDS):
            resp = client.post(f"/trail/{task_id}/complete")
            assert resp.status_code == 200
            payload = resp.json()
            expected_xp = (index + 1) * trail_module.DAILY_XP_REWARD
            assert payload["xp"] == expected_xp

        final_payload = payload
        assert final_payload["streak"] == 1
        today = final_payload["today"]
        assert final_payload["daily_totals"][today]["completed"] == trail_module.DAILY_TASK_COUNT
        assert final_payload["xp"] == len(trail_module.DAILY_TASK_IDS) * trail_module.DAILY_XP_REWARD

        # Ensure a subsequent fetch sees the persisted summary information.
        resp = client.get("/trail")
        assert resp.status_code == 200
        refreshed = resp.json()
        assert refreshed["xp"] == final_payload["xp"]
        assert refreshed["streak"] == final_payload["streak"]
        assert refreshed["daily_totals"][today] == final_payload["daily_totals"][today]
