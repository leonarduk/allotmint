import importlib

import pytest
from fastapi.testclient import TestClient

from backend.auth import get_current_user
from backend.config import config


@pytest.mark.parametrize("disable_auth", [True, False])
def test_trail_routes(tmp_path, monkeypatch, disable_auth):
    monkeypatch.setenv("TRAIL_URI", f"file://{tmp_path/'trail.json'}")
    monkeypatch.setattr(config, "disable_auth", disable_auth)

    import backend.app as app_mod
    import backend.quests.trail as trail_module
    import backend.routes.trail as trail_route_module
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
        daily_task_ids = [t["id"] for t in payload["tasks"] if t["type"] == "daily"]

        resp = client.post("/trail/unknown/complete")
        assert resp.status_code == 404

        for index, task_id in enumerate(daily_task_ids):
            resp = client.post(f"/trail/{task_id}/complete")
            assert resp.status_code == 200
            payload = resp.json()
            expected_xp = (index + 1) * trail_module.DAILY_XP_REWARD
            assert payload["xp"] == expected_xp

        final_payload = payload
        assert final_payload["streak"] == 1
        assert final_payload["xp"] == len(daily_task_ids) * trail_module.DAILY_XP_REWARD
        today = final_payload["today"]
        assert final_payload["daily_totals"][today]["completed"] == len(daily_task_ids)
        assert final_payload["daily_totals"][today]["total"] == len(daily_task_ids)

        # Ensure a follow-up read reflects the persisted streak/XP totals
        resp = client.get("/trail")
        assert resp.status_code == 200
        persisted_payload = resp.json()
        assert persisted_payload["xp"] == final_payload["xp"]
        assert persisted_payload["streak"] == final_payload["streak"]
        assert (
            persisted_payload["daily_totals"][today]["completed"]
            == len(daily_task_ids)
        )
