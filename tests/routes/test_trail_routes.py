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
        assert payload["xp"] == 0
        assert payload["streak"] == 0
        assert payload["today_completed"] == 0
        assert payload["today_total"] == len(trail_module.DAILY_TASK_IDS)

        daily_ids = [t["id"] for t in payload["tasks"] if t["type"] == "daily"]
        for task_id in daily_ids:
            resp = client.post(f"/trail/{task_id}/complete")
            assert resp.status_code == 200
            payload = resp.json()

        if daily_ids:
            expected_xp = (
                trail_module.DAILY_XP * len(daily_ids)
                + trail_module.DAILY_COMPLETION_BONUS
            )
            assert payload["xp"] == expected_xp
            assert payload["streak"] == 1
            assert payload["today_completed"] == len(daily_ids)

        resp = client.post("/trail/unknown/complete")
        assert resp.status_code == 404
