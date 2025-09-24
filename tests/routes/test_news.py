from __future__ import annotations

import json
from datetime import date
from typing import Dict, List

from fastapi.testclient import TestClient
from requests import HTTPError

from backend.app import create_app
from backend import config_module
from backend.routes import news as news_module
from backend.utils import page_cache


class _FakeDate(date):
    """Helper used to override ``date.today`` within tests."""

    _value = date(2023, 1, 1)

    @classmethod
    def today(cls) -> "_FakeDate":  # type: ignore[override]
        return cls(cls._value.year, cls._value.month, cls._value.day)


def test_counter_helpers(monkeypatch, tmp_path):
    counter_path = tmp_path / "news_requests.json"
    monkeypatch.setattr(news_module, "COUNTER_FILE", counter_path)
    monkeypatch.setattr(news_module, "date", _FakeDate)
    monkeypatch.setattr(news_module.cfg, "news_requests_per_day", 2)

    data = news_module._load_counter()
    assert data == {"date": "2023-01-01", "count": 0}

    news_module._save_counter({"date": "2023-01-01", "count": 1})
    assert json.loads(counter_path.read_text()) == {"date": "2023-01-01", "count": 1}

    loaded = news_module._load_counter()
    assert loaded == {"date": "2023-01-01", "count": 1}
    assert news_module._can_request_news() is True

    assert news_module._try_consume_quota() is True
    assert news_module._load_counter()["count"] == 2

    assert news_module._can_request_news() is False
    assert news_module._try_consume_quota() is False

    class _NextDay(_FakeDate):
        _value = date(2023, 1, 2)

    monkeypatch.setattr(news_module, "date", _NextDay)
    assert news_module._load_counter() == {"date": "2023-01-02", "count": 0}


def test_fetch_news_yahoo(monkeypatch):
    captured: Dict[str, object] = {}

    def fake_get(url, params, timeout=10):
        captured["url"] = url
        captured["params"] = params

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "news": [
                        {
                            "title": "One stock update",
                            "link": "https://example.com/1",
                        },
                        {"title": None, "link": "https://example.com/skip"},
                        {
                            "title": "Two shares story",
                            "link": "https://example.com/2",
                        },
                    ]
                }

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    items = news_module.fetch_news_yahoo("PFE")
    assert items == [
        {"headline": "One stock update", "url": "https://example.com/1"},
        {"headline": "Two shares story", "url": "https://example.com/2"},
    ]
    query = captured["params"]["q"]
    assert query.startswith("PFE")
    assert "stock" in query.lower()


def test_fetch_news_google(monkeypatch):
    xml = """
        <rss>
          <channel>
            <item>
                      <title>Story stock update</title>
              <link>https://example.com/story</link>
            </item>
            <item>
              <title>Missing link</title>
              <link></link>
            </item>
          </channel>
        </rss>
    """
    captured: Dict[str, object] = {}

    def fake_get(url, params, timeout=10):
        captured["url"] = url
        captured["params"] = params

        class Response:
            text = xml

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    items = news_module.fetch_news_google("MSFT")
    assert items == [
        {"headline": "Story stock update", "url": "https://example.com/story"},
    ]
    query = captured["params"]["q"]
    assert query.startswith("MSFT")
    assert "stock" in query.lower()


def test_fetch_news_fallback(monkeypatch):
    alpha_calls = {"count": 0}
    yahoo_calls = {"count": 0}
    google_calls = {"count": 0}

    def failing_alpha(url, params, timeout=10):
        alpha_calls["count"] += 1
        raise HTTPError("boom")

    def empty_yahoo(ticker: str) -> List[Dict[str, str]]:
        yahoo_calls["count"] += 1
        return []

    def google_result(ticker: str) -> List[Dict[str, str]]:
        google_calls["count"] += 1
        return [{"headline": f"{ticker} headline", "url": "https://example.com/fallback"}]

    monkeypatch.setattr(news_module.requests, "get", failing_alpha)
    monkeypatch.setattr(news_module, "fetch_news_yahoo", empty_yahoo)
    monkeypatch.setattr(news_module, "fetch_news_google", google_result)

    items = news_module._fetch_news("TSLA")
    assert items == [{"headline": "TSLA headline", "url": "https://example.com/fallback"}]
    assert alpha_calls["count"] == 1
    assert yahoo_calls["count"] == 1
    assert google_calls["count"] == 1


def test_get_news_quota_and_cache(monkeypatch, tmp_path):
    cache: Dict[str, List[Dict[str, str]]] = {}

    def load_cache(page: str):
        return cache.get(page)

    def save_cache(page: str, data: List[Dict[str, str]]):
        cache[page] = data

    def is_stale(page: str, ttl: int) -> bool:
        return page not in cache

    monkeypatch.setattr(page_cache, "load_cache", load_cache)
    monkeypatch.setattr(page_cache, "save_cache", save_cache)
    monkeypatch.setattr(page_cache, "is_stale", is_stale)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)

    counter_path = tmp_path / "news_requests.json"
    monkeypatch.setattr(news_module, "COUNTER_FILE", counter_path)
    monkeypatch.setattr(config_module.config, "disable_auth", True, raising=False)
    monkeypatch.setattr(config_module.config, "skip_snapshot_warm", True, raising=False)
    monkeypatch.setattr(
        "backend.common.portfolio_utils.refresh_snapshot_async", lambda days=0: None
    )

    calls = {"alpha": 0}

    def fake_get(url, params, timeout=10):
        calls["alpha"] += 1

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                ticker = params["tickers"]
                return {
                    "feed": [
                        {
                            "title": f"{ticker} headline",
                            "url": f"https://example.com/{ticker.lower()}",
                        }
                    ]
                }

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    app = create_app()
    monkeypatch.setattr(news_module.cfg, "news_requests_per_day", 2)

    with TestClient(app) as client:
        first = client.get("/news", params={"ticker": "ABC"})
        assert first.status_code == 200
        assert first.json() == [
            {"headline": "ABC headline", "url": "https://example.com/abc"}
        ]
        assert calls["alpha"] == 1
        assert json.loads(counter_path.read_text())["count"] == 1

        cached = client.get("/news", params={"ticker": "ABC"})
        assert cached.status_code == 200
        assert cached.json() == [
            {"headline": "ABC headline", "url": "https://example.com/abc"}
        ]
        assert calls["alpha"] == 1
        assert json.loads(counter_path.read_text())["count"] == 1

        second = client.get("/news", params={"ticker": "XYZ"})
        assert second.status_code == 200
        assert second.json() == [
            {"headline": "XYZ headline", "url": "https://example.com/xyz"}
        ]
        assert calls["alpha"] == 2
        assert json.loads(counter_path.read_text())["count"] == 2

        limited = client.get("/news", params={"ticker": "OVER"})
        assert limited.status_code == 429
        assert calls["alpha"] == 2
        assert json.loads(counter_path.read_text())["count"] == 2

        cached_after_limit = client.get("/news", params={"ticker": "ABC"})
        assert cached_after_limit.status_code == 200
        assert cached_after_limit.json() == [
            {"headline": "ABC headline", "url": "https://example.com/abc"}
        ]
        assert calls["alpha"] == 2


def test_get_cached_news_cold_cache_fetches_once(monkeypatch):
    cache: Dict[str, List[Dict[str, str]]] = {}

    def load_cache(page: str):
        return cache.get(page)

    def save_cache(page: str, data: List[Dict[str, str]]):
        cache[page] = data

    def is_stale(page: str, ttl: int) -> bool:
        return page not in cache

    monkeypatch.setattr(page_cache, "load_cache", load_cache)
    monkeypatch.setattr(page_cache, "save_cache", save_cache)
    monkeypatch.setattr(page_cache, "is_stale", is_stale)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)

    fetch_calls = {"count": 0}
    quota_calls = {"count": 0}

    def fake_fetch(ticker: str) -> List[Dict[str, str]]:
        fetch_calls["count"] += 1
        return [{"headline": f"{ticker} headline", "url": "https://example.com"}]

    def fake_quota() -> bool:
        quota_calls["count"] += 1
        return True

    monkeypatch.setattr(news_module, "_fetch_news", fake_fetch)
    monkeypatch.setattr(news_module, "_try_consume_quota", fake_quota)

    first = news_module.get_cached_news("cold")
    assert first == [{"headline": "COLD headline", "url": "https://example.com"}]
    assert fetch_calls["count"] == 1
    assert quota_calls["count"] == 1

    second = news_module.get_cached_news("cold")
    assert second == first
    assert fetch_calls["count"] == 1
    assert quota_calls["count"] == 1
