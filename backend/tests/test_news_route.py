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
        lambda t: [{"headline": "h1", "url": "u1"}],
    )

    resp = client.get("/news", params={"ticker": "AAA"})
    assert resp.status_code == 200
    assert resp.json() == [{"headline": "h1", "url": "u1"}]


def test_get_news_trims_payload_and_caches(monkeypatch):
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


def test_fallback_helpers_filter_finance_headlines(monkeypatch):
    def fake_yahoo(url, params, timeout=10):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "news": [
                        {
                            "title": "AAPL stock jumps on earnings",
                            "link": "https://example.com/finance",
                        },
                        {
                            "title": "Celebrity gossip unrelated to pop culture",
                            "link": "https://example.com/gossip",
                        },
                    ]
                }

        return Response()

    monkeypatch.setattr(news.requests, "get", fake_yahoo)
    yahoo_items = news.fetch_news_yahoo("AAPL")
    assert yahoo_items == [
        {"headline": "AAPL stock jumps on earnings", "url": "https://example.com/finance"}
    ]

    def fake_google(url, params, timeout=10):
        class Response:
            text = """
                <rss>
                  <channel>
                    <item>
                      <title>MSFT shares slump after outlook</title>
                      <link>https://example.com/outlook</link>
                    </item>
                    <item>
                      <title>Another gadget launch unrelated to lifestyle</title>
                      <link>https://example.com/gadget</link>
                    </item>
                  </channel>
                </rss>
            """

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(news.requests, "get", fake_google)
    google_items = news.fetch_news_google("MSFT")
    assert google_items == [
        {"headline": "MSFT shares slump after outlook", "url": "https://example.com/outlook"}
    ]
