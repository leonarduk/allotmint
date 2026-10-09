"""Bots page API (#10477): list, detail, history, Run now, settings and permissions."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.bots as bots_route
from backend.agent import trading_agent
from backend.auth import get_active_user
from backend.bots import registry, runs
from backend.bots.registry import BotRunContext, BotSettings, RunResult, Schedule
from backend.common.errors import PermissionDeniedError

ADMIN = "admin@example.com"
USER = "viewer@example.com"


class _Bot:
    id = "trading-agent"
    name = "Trading agent signals"
    description = "test"
    kind = "rules"
    scope = "system"
    default_schedule = Schedule(hour=1)
    timeout_minutes = 10

    def __init__(self):
        real = registry.get_bot("trading-agent")
        self._real = real
        self.settings_model = real.settings_model
        self.calls = 0

    def default_settings(self):
        return self._real.default_settings()

    def run(self, context: BotRunContext, settings: BotSettings) -> RunResult:
        self.calls += 1
        cfg = trading_agent.load_strategy_config()
        return RunResult(status="ok", summary=f"rsi_buy={cfg.rsi_buy}")


@pytest.fixture
def fake_trading_bot():
    real = registry.get_bot("trading-agent")
    bot = _Bot()
    registry.register_bot(bot, replace=True)
    yield bot
    registry.register_bot(real, replace=True)


def _client(monkeypatch, *, identity=None, disable_auth=True, app_env="local") -> TestClient:
    monkeypatch.setattr(bots_route.config, "disable_auth", disable_auth)
    monkeypatch.setattr(bots_route.config, "allowed_emails", [ADMIN])
    monkeypatch.setattr(bots_route.config, "app_env", app_env)
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    app = FastAPI()
    app.include_router(bots_route.router)
    app.dependency_overrides[get_active_user] = lambda: identity
    return TestClient(app)


def test_list_shows_existing_jobs_with_never_run(monkeypatch):
    resp = _client(monkeypatch).get("/bots")
    assert resp.status_code == 200
    by_id = {b["id"]: b for b in resp.json()}
    assert {"trading-agent", "price-refresh", "dividend-refresh", "pension-report"} <= set(by_id)
    assert by_id["price-refresh"]["last_run"] is None
    assert by_id["price-refresh"]["schedule"] == "Daily at 00:00 UTC"
    assert by_id["price-refresh"]["next_run"] is not None


def test_detail_includes_settings_and_schema(monkeypatch):
    body = _client(monkeypatch).get("/bots/trading-agent").json()
    assert body["settings"]["rsi_window"] == 14
    assert "rsi_buy" in body["settings_schema"]["properties"]
    assert "require_pro_checks" not in body["settings"]
    assert body["can_manage"] is True


def test_unknown_bot_404(monkeypatch):
    assert _client(monkeypatch).get("/bots/nope").status_code == 404


def test_run_now_records_run(monkeypatch, fake_trading_bot):
    client = _client(monkeypatch)
    resp = client.post("/bots/trading-agent/run")
    assert resp.status_code == 202
    run_id = resp.json()["id"]
    # TestClient runs background tasks before returning.
    history = client.get("/bots/trading-agent/runs").json()
    assert history[0]["id"] == run_id
    assert history[0]["status"] == "ok"
    assert history[0]["trigger"] == "manual"
    assert client.get(f"/bots/trading-agent/runs/{run_id}").json()["status"] == "ok"
    assert fake_trading_bot.calls == 1


def test_second_run_rejected_while_running(monkeypatch, fake_trading_bot):
    client = _client(monkeypatch)
    # Hold the first run in "running" by not executing its background task.
    monkeypatch.setattr(bots_route.runner, "dispatch_run", lambda record, tasks: record)
    assert client.post("/bots/trading-agent/run").status_code == 202
    second = client.post("/bots/trading-agent/run")
    assert second.status_code == 409
    assert fake_trading_bot.calls == 0


def test_out_of_range_setting_returns_422(monkeypatch):
    resp = _client(monkeypatch).put("/bots/trading-agent/settings", json={"rsi_buy": 150})
    assert resp.status_code == 422


def test_unknown_setting_key_returns_422(monkeypatch):
    resp = _client(monkeypatch).put("/bots/trading-agent/settings", json={"telegram_bot_token": "x"})
    assert resp.status_code == 422


def test_valid_setting_saved_audited_and_used_by_next_run(monkeypatch, fake_trading_bot):
    audited = []
    monkeypatch.setattr("backend.data_quality.audit.append_audit", lambda **kw: audited.append(kw))
    client = _client(monkeypatch)
    resp = client.put("/bots/trading-agent/settings", json={"rsi_buy": 22})
    assert resp.status_code == 200
    assert resp.json()["settings"]["rsi_buy"] == 22
    assert audited and audited[0]["entity"] == {"bot_id": "trading-agent"}

    client.post("/bots/trading-agent/run")
    assert client.get("/bots/trading-agent/runs").json()[0]["summary"] == "rsi_buy=22.0"


def test_non_admin_gets_403_on_run_and_settings(monkeypatch):
    client = _client(monkeypatch, identity=USER, disable_auth=False)
    assert client.post("/bots/trading-agent/run").status_code == 403
    assert client.put("/bots/trading-agent/settings", json={"enabled": False}).status_code == 403
    assert client.get("/bots/trading-agent").json()["can_manage"] is False


def test_admin_allowed_when_auth_enabled(monkeypatch, fake_trading_bot):
    client = _client(monkeypatch, identity=ADMIN, disable_auth=False)
    assert client.post("/bots/trading-agent/run").status_code == 202


def test_aws_with_auth_disabled_still_requires_admin(monkeypatch):
    """The Lambda runs with disable_auth (API Gateway authenticates); that must not open the gate."""
    client = _client(monkeypatch, identity=USER, disable_auth=True, app_env="aws")
    assert client.post("/bots/trading-agent/run").status_code == 403
    assert client.put("/bots/trading-agent/settings", json={"enabled": False}).status_code == 403
    assert client.get("/bots/trading-agent").json()["can_manage"] is False


def test_aws_admin_on_allowlist_can_manage(monkeypatch, fake_trading_bot):
    monkeypatch.setattr(bots_route.runner, "dispatch_run", lambda record, tasks: record)
    client = _client(monkeypatch, identity=ADMIN, disable_auth=True, app_env="aws")
    assert client.post("/bots/trading-agent/run").status_code == 202


def test_admin_emails_takes_precedence_over_allowed_emails(monkeypatch):
    client = _client(monkeypatch, identity=ADMIN, disable_auth=True, app_env="aws")
    monkeypatch.setenv("ADMIN_EMAILS", "someone-else@example.com")
    assert client.post("/bots/trading-agent/run").status_code == 403


def test_no_allowlist_denies_everyone_off_local(monkeypatch):
    client = _client(monkeypatch, identity=ADMIN, disable_auth=True, app_env="aws")
    monkeypatch.setattr(bots_route.config, "allowed_emails", [])
    assert client.post("/bots/trading-agent/run").status_code == 403


def test_demo_request_cannot_manage(monkeypatch):
    monkeypatch.setattr(bots_route, "is_demo_request", lambda: True)
    client = _client(monkeypatch)
    assert client.post("/bots/trading-agent/run").status_code == 403


def test_owner_scoped_runs_filtered_by_owner_access(monkeypatch):
    now = datetime.now(timezone.utc)
    for rid, owner in (("mine", "viewer"), ("theirs", "other"), ("system", None)):
        runs.save_run(
            runs.RunRecord(id=rid, bot_id="price-refresh", trigger="manual", status="ok", started_at=now, owner=owner)
        )

    def fake_access(identity, owner, accounts_root=None):
        if owner != "viewer":
            raise PermissionDeniedError("no")

    monkeypatch.setattr(bots_route, "ensure_owner_access", fake_access)
    client = _client(monkeypatch, identity=USER, disable_auth=False)
    ids = {r["id"] for r in client.get("/bots/price-refresh/runs").json()}
    assert ids == {"mine", "system"}
    assert client.get("/bots/price-refresh/runs/theirs").status_code == 404
