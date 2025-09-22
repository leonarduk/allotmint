import requests
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import Dict, List, Tuple

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


def test_get_news_falls_back(monkeypatch):
    client = _client()
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda *a, **k: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "save_cache", lambda *a, **k: None)

    def fake_get(*args, **kwargs):
        raise requests.RequestException("boom")

    monkeypatch.setattr(news.requests, "get", fake_get)
    monkeypatch.setattr(
        news,
        "fetch_news_yahoo",
        lambda t: [
            {
                "headline": "h1",
                "url": "u1",
                "source": "Yahoo",
                "published_at": "2023-01-01T00:00:00Z",
            }
        ],
    )

    resp = client.get("/news", params={"ticker": "AAA"})
    assert resp.status_code == 200
    assert resp.json() == [{"headline": "h1", "url": "u1"}]


def test_get_news_includes_metadata_and_caches(monkeypatch):
    client = _client()

    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(page_cache, "is_stale", lambda *a, **k: True)
    monkeypatch.setattr(page_cache, "load_cache", lambda *a, **k: None)

    saved: List[Tuple[str, List[Dict[str, str]]]] = []

    def fake_save_cache(page: str, payload):
        saved.append((page, payload))

    monkeypatch.setattr(page_cache, "save_cache", fake_save_cache)

    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "feed": [
                    {
                        "title": "Alpha headline",
                        "url": "https://example.com/article",
                        "source": "AlphaVantage",
                        "time_published": "2023-08-25T12:00:00-04:00",
                    }
                ]
            }

    monkeypatch.setattr(news.requests, "get", lambda *a, **k: DummyResponse())

    resp = client.get("/news", params={"ticker": "AAA"})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload == [
        {
            "headline": "Alpha headline",
            "url": "https://example.com/article",
        }
    ]
    assert saved == [
        (
            "news_AAA",
            [
                {
                    "headline": "Alpha headline",
                    "url": "https://example.com/article",
                }
            ],
        )
    ]


def test_parse_alpha_time_legacy_format():
    assert (
        news._parse_alpha_time("20230825T160000")
        == "2023-08-25T16:00:00Z"
    )
