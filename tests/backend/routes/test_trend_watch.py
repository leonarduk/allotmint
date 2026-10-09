"""Trend-watch routes: run, latest report, mutes and settings (#10476)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import get_active_user
from backend.routes import trend_watch as routes
from backend.trend_watch import prompt
from backend.trend_watch.service import run_for_owner

from ..trend_watch import test_service as fixtures


@pytest.fixture
def client(monkeypatch):
    checked = []
    calls = []
    monkeypatch.setattr(routes, "ensure_owner_access", lambda identity, owner, root: checked.append((identity, owner)))

    async def fake_run(owner, *, notify, load_portfolio):
        calls.append(notify)
        return await run_for_owner(
            owner,
            notify=notify,
            runner=fixtures._runner,
            load_portfolio=lambda name: fixtures.PORTFOLIO,
            load_prices=lambda ticker, days: fixtures.PRICES.get(ticker, fixtures.pd.Series(dtype=float)),
            load_levels=lambda closes, ticker: (closes, "total"),
            load_meta=lambda ticker: fixtures.META.get(ticker, {}),
            load_issues=lambda: ([fixtures.NOISY_ISSUE], []),
        )

    monkeypatch.setattr(routes, "run_for_owner", fake_run)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_active_user] = lambda: "alex@example.com"
    test_client = TestClient(app)
    test_client.checked = checked
    test_client.notify_calls = calls
    return test_client


def test_latest_is_404_before_the_first_run(client):
    response = client.get("/trend-watch/alex/latest")

    assert response.status_code == 404


def test_run_then_latest_returns_the_stored_report(client):
    run = client.post("/trend-watch/alex/run")
    latest = client.get("/trend-watch/alex/latest")

    assert run.status_code == 200
    assert latest.status_code == 200
    body = latest.json()
    assert body == {**run.json(), "mutes": []}
    assert {item["verdict"] for item in body["items"]} == {
        prompt.VERDICT_IDIOSYNCRATIC,
        prompt.VERDICT_MARKET,
        prompt.VERDICT_DATA,
    }
    assert ("alex@example.com", "alex") in client.checked


def test_mute_toggle_is_stored_and_returned_with_the_report(client):
    client.post("/trend-watch/alex/run")

    muted = client.put("/trend-watch/alex/mutes/turn.l", json={"muted": True})
    latest = client.get("/trend-watch/alex/latest").json()
    unmuted = client.put("/trend-watch/alex/mutes/TURN.L", json={"muted": False})

    assert muted.json() == {"mutes": ["TURN.L"]}
    assert latest["mutes"] == ["TURN.L"]
    assert unmuted.json() == {"mutes": []}


@pytest.mark.parametrize("owner", ["..", "a/b", "x" * 80])
def test_invalid_owner_is_rejected(client, owner):
    response = client.get(f"/trend-watch/{owner}/latest")

    assert response.status_code in (400, 404)


def test_settings_expose_the_detector_thresholds(client):
    body = client.get("/trend-watch/settings").json()

    assert body["min_signals"] >= 2
    assert body["memory_runs"] >= 1
    assert body["max_tool_calls"] > 0


def test_notify_query_reaches_the_run_and_sends_the_alert(client, monkeypatch):
    from backend.agent import trading_agent

    sent = []
    monkeypatch.setattr(trading_agent, "send_trade_alert", lambda text: sent.append(text))

    client.post("/trend-watch/alex/run?notify=true")
    alerted = list(sent)
    client.post("/trend-watch/alex/run")

    assert client.notify_calls == [True, False]
    assert len(alerted) == 1 and "holding(s) to review" in alerted[0]
    assert sent == alerted
