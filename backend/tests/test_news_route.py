import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes import news
from backend.utils import page_cache


def _client():
    app = FastAPI()
    app.include_router(news.router)
    return TestClient(app)


def test_get_news_handles_errors(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda *a, **k: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "save_cache", lambda *a, **k: None)

    def fake_get(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(news.requests, "get", fake_get)

    resp = client.get("/news", params={"ticker": "AAA"})
    assert resp.status_code == 200
    assert resp.json() == []
