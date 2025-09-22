import importlib

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.auth import get_current_user
from backend.config import config


class FakeDate(date):
    today_value = date.today()

    @classmethod
    def today(cls):  # type: ignore[override]
        return cls.today_value


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
    trail_module.date = FakeDate

    if not disable_auth:
        app.dependency_overrides[get_current_user] = lambda: "demo"

    with TestClient(app) as client:
        resp = client.get("/trail")
        assert resp.status_code == 200
        payload = resp.json()
        assert {"tasks", "xp", "streak", "daily_totals"} <= payload.keys()
        assert payload["xp"] == 0
        assert payload["streak"] == 0

        resp = client.post("/trail/unknown/complete")
        assert resp.status_code == 404

        daily_ids = [t["id"] for t in trail_module.DEFAULT_TASKS if t["type"] == "daily"]

        FakeDate.today_value = date(2024, 1, 1)
        first_complete = client.post(f"/trail/{daily_ids[0]}/complete")
        assert first_complete.status_code == 200
        body = first_complete.json()
        assert body["xp"] == trail_module.XP_PER_COMPLETION
        assert body["streak"] == 0
        today_key = FakeDate.today_value.isoformat()
        assert body["daily_totals"][today_key] == 1

        second_complete = client.post(f"/trail/{daily_ids[1]}/complete")
        assert second_complete.status_code == 200
        body = second_complete.json()
        assert body["xp"] == trail_module.XP_PER_COMPLETION * 2
        assert body["streak"] == 1
        assert body["daily_totals"][today_key] == 2

        FakeDate.today_value = FakeDate.today_value + timedelta(days=1)
        third_complete = client.post(f"/trail/{daily_ids[0]}/complete")
        assert third_complete.status_code == 200
        next_body = third_complete.json()
        assert next_body["streak"] == 1

        fourth_complete = client.post(f"/trail/{daily_ids[1]}/complete")
        assert fourth_complete.status_code == 200
        final_body = fourth_complete.json()
        assert final_body["streak"] == 2
