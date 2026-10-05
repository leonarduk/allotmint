import pytest
from fastapi.testclient import TestClient

import backend.routes.news as news
from backend.app import create_app
from backend.utils import page_cache


@pytest.fixture(autouse=True)
def _news_provider_defaults(monkeypatch):
    """Configure an AlphaVantage key and a fresh Yahoo cooldown per test.

    With no key, ``fetch_news_alpha`` skips AlphaVantage entirely, so tests
    that mock its response need one set; tests for the no-key path override
    it. A fresh cooldown keeps a 429 tripped in one test from silencing Yahoo
    in the next.
    """
    monkeypatch.setattr(news.cfg, "alpha_vantage_key", "test-key")
    monkeypatch.setattr(
        news,
        "_yahoo_cooldown",
        news._ProviderCooldown(news.YAHOO_COOLDOWN_DEFAULT, news.YAHOO_COOLDOWN_MAX),
    )


def test_news_quota_enforced(monkeypatch, tmp_path):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(news, "COUNTER_FILE", tmp_path / "news_requests.json")
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)

    calls = {"count": 0}

    def fake_get(url, params, timeout=10):
        calls["count"] += 1

        class Resp:
            status_code = 200
            headers = {}

            def raise_for_status(self):
                pass

            def json(self):
                return {"feed": [{"title": "h", "url": "u"}]}

        return Resp()

    monkeypatch.setattr(news.requests, "get", fake_get)

    app = create_app()
    # create_app() reloads config, resetting the key the autouse fixture set.
    monkeypatch.setattr(news.cfg, "alpha_vantage_key", "test-key")
    client = TestClient(app)
    token = client.post("/token", json={"id_token": "good"}).json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})

    limit = news.config.news_requests_per_day

    for i in range(limit):
        resp = client.get(f"/news?ticker=T{i}")
        assert resp.status_code == 200
        assert resp.json()[0]["headline"] == "h"

    assert calls["count"] == limit

    # Cached ticker served without hitting external API
    resp = client.get("/news?ticker=T0")
    assert resp.status_code == 200
    assert calls["count"] == limit

    # New ticker beyond quota returns 429 and no additional call
    resp = client.get("/news?ticker=OVER")
    assert resp.status_code == 429
    assert calls["count"] == limit
