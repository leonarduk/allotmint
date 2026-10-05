from __future__ import annotations

import json
from datetime import date
from typing import Dict, List

import defusedxml
import pytest
from fastapi.testclient import TestClient
from requests import HTTPError

from backend import config_module
from backend.app import create_app
from backend.common.url_validator import InvalidExternalURLError
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

    def fake_get(url, params=None, timeout=10, **kwargs):
        captured["url"] = url
        captured["params"] = params
        captured["impersonate"] = kwargs.get("impersonate")

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

    monkeypatch.setattr(news_module.curl_requests, "get", fake_get)

    items = news_module.fetch_news_yahoo("PFE")
    assert items == [
        {"headline": "One stock update", "url": "https://example.com/1"},
        {"headline": "Two shares story", "url": "https://example.com/2"},
    ]
    query = captured["params"]["q"]
    assert query.startswith("PFE")
    assert "stock" in query.lower()
    # Plain ``requests`` gets 429'd by Yahoo; the fetch must impersonate a browser.
    assert captured["impersonate"] == news_module.YAHOO_IMPERSONATE


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

    def fake_get(url, params=None, timeout=10, **kwargs):
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


def test_fetch_news_yahoo_populates_published_at_and_source(monkeypatch):
    def fake_get(url, params=None, timeout=10, **kwargs):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "news": [
                        {
                            "title": "Stock update",
                            "link": "https://example.com/1",
                            "providerPublishTime": 1717245296,
                            "publisher": "Reuters",
                        }
                    ]
                }

        return Response()

    monkeypatch.setattr(news_module.curl_requests, "get", fake_get)

    items = news_module.fetch_news_yahoo("PFE")
    assert items == [
        {
            "headline": "Stock update",
            "url": "https://example.com/1",
            "published_at": "2024-06-01T12:34:56Z",
            "source": "Reuters",
        }
    ]


def test_fetch_news_google_populates_published_at(monkeypatch):
    xml = """
        <rss>
          <channel>
            <item>
              <title>Story stock update</title>
              <link>https://example.com/story</link>
              <pubDate>Sat, 01 Jun 2024 12:34:56 GMT</pubDate>
              <source>Example News</source>
            </item>
          </channel>
        </rss>
    """

    def fake_get(url, params=None, timeout=10, **kwargs):
        class Response:
            text = xml

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    items = news_module.fetch_news_google("MSFT")
    assert items == [
        {
            "headline": "Story stock update",
            "url": "https://example.com/story",
            "published_at": "2024-06-01T12:34:56Z",
            "source": "Example News",
        }
    ]


def test_fetch_news_alpha_populates_published_at(monkeypatch):
    def fake_get(url, params=None, timeout=10, **kwargs):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "feed": [
                        {
                            "title": "Alpha headline",
                            "url": "https://example.com/alpha",
                            "time_published": "20240601T123456",
                            "source": "AlphaWire",
                        }
                    ]
                }

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    items = news_module._fetch_news("AAPL")
    assert items == [
        {
            "headline": "Alpha headline",
            "url": "https://example.com/alpha",
            "published_at": "2024-06-01T12:34:56Z",
            "source": "AlphaWire",
        }
    ]


def test_fetch_news_alpha_omits_published_at_when_missing(monkeypatch):
    def fake_get(url, params=None, timeout=10, **kwargs):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "feed": [
                        {
                            "title": "Undated headline",
                            "url": "https://example.com/undated",
                        }
                    ]
                }

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    items = news_module._fetch_news("AAPL")
    assert items == [{"headline": "Undated headline", "url": "https://example.com/undated"}]


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
    monkeypatch.setattr("backend.common.portfolio_utils.refresh_snapshot_async", lambda days=0: None)

    calls = {"alpha": 0}

    def fake_get(url, params=None, timeout=10, **kwargs):
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
        assert first.json() == [{"headline": "ABC headline", "url": "https://example.com/abc", "stale": False}]
        assert calls["alpha"] == 1
        assert json.loads(counter_path.read_text())["count"] == 1

        cached = client.get("/news", params={"ticker": "ABC"})
        assert cached.status_code == 200
        assert cached.json() == [{"headline": "ABC headline", "url": "https://example.com/abc", "stale": False}]
        assert calls["alpha"] == 1
        assert json.loads(counter_path.read_text())["count"] == 1

        second = client.get("/news", params={"ticker": "XYZ"})
        assert second.status_code == 200
        assert second.json() == [{"headline": "XYZ headline", "url": "https://example.com/xyz", "stale": False}]
        assert calls["alpha"] == 2
        assert json.loads(counter_path.read_text())["count"] == 2

        limited = client.get("/news", params={"ticker": "OVER"})
        assert limited.status_code == 429
        assert calls["alpha"] == 2
        assert json.loads(counter_path.read_text())["count"] == 2

        cached_after_limit = client.get("/news", params={"ticker": "ABC"})
        assert cached_after_limit.status_code == 200
        assert cached_after_limit.json() == [
            {"headline": "ABC headline", "url": "https://example.com/abc", "stale": False}
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
    assert first == [{"headline": "COLD headline", "url": "https://example.com", "stale": False}]
    assert fetch_calls["count"] == 1
    assert quota_calls["count"] == 1

    second = news_module.get_cached_news("cold")
    assert second == first
    assert fetch_calls["count"] == 1
    assert quota_calls["count"] == 1


def test_get_cached_news_flags_stale_cache_on_quota_exhaustion(monkeypatch):
    cache: Dict[str, List[Dict[str, str]]] = {
        "news_STALE": [{"headline": "Old headline", "url": "https://example.com/old"}]
    }

    monkeypatch.setattr(page_cache, "load_cache", lambda page: cache.get(page))
    monkeypatch.setattr(page_cache, "is_stale", lambda page, ttl: True)
    monkeypatch.setattr(page_cache, "cache_age", lambda page: news_module.NEWS_MAX_STALENESS + 1)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(news_module, "_try_consume_quota", lambda: False)

    items = news_module.get_cached_news("stale")
    assert items == [
        {
            "headline": "Old headline",
            "url": "https://example.com/old",
            "stale": True,
        }
    ]


def test_get_cached_news_does_not_flag_recent_cache_on_quota_exhaustion(monkeypatch):
    cache: Dict[str, List[Dict[str, str]]] = {
        "news_RECENT": [{"headline": "Recent headline", "url": "https://example.com/recent"}]
    }

    monkeypatch.setattr(page_cache, "load_cache", lambda page: cache.get(page))
    monkeypatch.setattr(page_cache, "is_stale", lambda page, ttl: True)
    monkeypatch.setattr(page_cache, "cache_age", lambda page: news_module.NEWS_MAX_STALENESS - 1)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(news_module, "_try_consume_quota", lambda: False)

    items = news_module.get_cached_news("recent")
    assert items == [
        {
            "headline": "Recent headline",
            "url": "https://example.com/recent",
            "stale": False,
        }
    ]


# ── SSRF guard wiring ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "bad_endpoint",
    [
        pytest.param("https://169.254.169.254/latest/meta-data/", id="aws_metadata"),
        pytest.param("https://127.0.0.1/search", id="loopback"),
        pytest.param("https://10.0.0.1/search", id="rfc1918"),
        pytest.param("https://localhost/search", id="localhost"),
    ],
)
def test_fetch_news_yahoo_rejects_private_endpoint(monkeypatch, bad_endpoint: str) -> None:
    monkeypatch.setattr(news_module.cfg, "yahoo_news_endpoint", bad_endpoint)
    with pytest.raises(InvalidExternalURLError):
        news_module.fetch_news_yahoo("AAPL")


@pytest.mark.parametrize(
    "bad_endpoint",
    [
        pytest.param("https://169.254.169.254/rss", id="aws_metadata"),
        pytest.param("https://127.0.0.1/rss", id="loopback"),
        pytest.param("https://192.168.1.1/rss", id="rfc1918"),
        pytest.param("https://localhost/rss", id="localhost"),
    ],
)
def test_fetch_news_google_rejects_private_endpoint(monkeypatch, bad_endpoint: str) -> None:
    monkeypatch.setattr(news_module.cfg, "google_news_endpoint", bad_endpoint)
    with pytest.raises(InvalidExternalURLError):
        news_module.fetch_news_google("AAPL")


def test_fetch_news_google_billion_laughs_rejected(monkeypatch):
    bomb = (
        '<?xml version="1.0"?>'
        "<!DOCTYPE lolz ["
        '  <!ENTITY lol "lol">'
        '  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">'
        '  <!ENTITY lol3 "&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;&lol2;">'
        "]>"
        "<lolz>&lol3;</lolz>"
    )

    def fake_get(url, params=None, timeout=10, **kwargs):
        class Response:
            text = bomb

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    with pytest.raises(defusedxml.EntitiesForbidden):
        news_module.fetch_news_google("MSFT")


def test_get_news_serves_fresh_cache_from_sync_route(monkeypatch, tmp_path):
    """Regression: ``/news`` is a sync route, so FastAPI runs it on a worker
    thread with no event loop. Scheduling the background refresh there used
    to raise ``RuntimeError``, which the route reported as a 429 even with
    quota to spare. ``schedule_refresh`` is deliberately not stubbed."""

    from fastapi import FastAPI

    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    payload = [{"headline": "Cached", "url": "https://example.test/cached"}]
    page_cache.save_cache("news_ONE", payload)

    app = FastAPI()
    app.include_router(news_module.router)
    resp = TestClient(app).get("/news", params={"ticker": "ONE"})

    assert resp.status_code == 200
    assert resp.json() == [{**payload[0], "stale": False}]
    assert "news_ONE" not in page_cache._refresh_tasks


def test_get_cached_news_rebuilds_stale_cache_off_event_loop(monkeypatch, tmp_path):
    """Off the event loop no background refresh is scheduled, so a stale cache
    must be rebuilt synchronously on the request instead of served forever."""

    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    page_cache.save_cache("news_ONE", [{"headline": "Old", "url": "https://example.test/old"}])
    monkeypatch.setattr(page_cache, "is_stale", lambda page, ttl: True)
    monkeypatch.setattr(news_module, "_try_consume_quota", lambda: True)
    fresh = [{"headline": "Fresh", "url": "https://example.test/fresh"}]
    monkeypatch.setattr(news_module, "_fetch_news", lambda ticker: fresh)

    with ThreadPoolExecutor(max_workers=1) as pool:
        items = pool.submit(news_module.get_cached_news, "ONE").result()

    assert items == [{**fresh[0], "stale": False}]
    assert page_cache.load_cache("news_ONE") == fresh
    assert "news_ONE" not in page_cache._refresh_tasks


def test_get_cached_news_shares_concurrent_fetch(monkeypatch, tmp_path):
    """Concurrent callers for the same ticker must share one upstream fetch.

    Without single-flighting, each request that misses the cache fetches on
    its own, multiplying calls to Yahoo (and its 429s) and burning one quota
    unit per caller.
    """

    import threading
    from concurrent.futures import Future

    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(news_module, "COUNTER_FILE", tmp_path / "news_requests.json")
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)

    callers = 4
    started = threading.Event()
    release = threading.Event()
    fetch_calls = {"count": 0}

    def slow_fetch(ticker: str) -> List[Dict[str, str]]:
        fetch_calls["count"] += 1
        started.set()
        assert release.wait(timeout=5)
        return [{"headline": f"{ticker} stock news", "url": "https://example.com/n"}]

    monkeypatch.setattr(news_module, "_fetch_news", slow_fetch)

    waiting = threading.Semaphore(0)

    class SignallingFuture(Future):
        """Signals when a follower starts blocking on the leader's result."""

        def result(self, timeout=None):
            waiting.release()
            return super().result(timeout)

    monkeypatch.setattr(news_module, "Future", SignallingFuture)

    results: List[List[Dict[str, object]]] = []

    def worker() -> None:
        results.append(news_module.get_cached_news("ftse", cache_writer=lambda page, data: None))

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(callers)]
    threads[0].start()
    assert started.wait(timeout=5)
    for thread in threads[1:]:
        thread.start()
    # Hold the leader's fetch open until every follower is blocked on it.
    for _ in range(callers - 1):
        assert waiting.acquire(timeout=5)

    release.set()
    for thread in threads:
        thread.join(timeout=5)

    assert fetch_calls["count"] == 1
    assert len(results) == callers
    assert all(r == results[0] for r in results)
    assert news_module._load_counter()["count"] == 1
    assert news_module._inflight == {}


def test_single_flight_propagates_errors_and_clears_entry():
    def boom() -> List[Dict[str, str]]:
        raise news_module.NewsQuotaExceeded("news quota exceeded")

    with pytest.raises(news_module.NewsQuotaExceeded):
        news_module._single_flight("news_X", boom)
    assert "news_X" not in news_module._inflight
    assert news_module._single_flight("news_X", lambda: []) == []


def test_single_flight_follower_receives_leader_exception(monkeypatch):
    """A follower blocked on the leader must see the leader's exception."""

    import threading
    from concurrent.futures import Future

    started = threading.Event()
    release = threading.Event()
    follower_waiting = threading.Event()

    class SignallingFuture(Future):
        def result(self, timeout=None):
            follower_waiting.set()
            return super().result(timeout)

    monkeypatch.setattr(news_module, "Future", SignallingFuture)

    def failing_fetch() -> List[Dict[str, str]]:
        started.set()
        assert release.wait(timeout=5)
        raise news_module.NewsQuotaExceeded("news quota exceeded")

    errors: List[BaseException] = []

    def run() -> None:
        try:
            news_module._single_flight("news_ERR", failing_fetch)
        except BaseException as exc:
            errors.append(exc)

    leader = threading.Thread(target=run, daemon=True)
    follower = threading.Thread(target=run, daemon=True)
    leader.start()
    assert started.wait(timeout=5)
    follower.start()
    assert follower_waiting.wait(timeout=5)
    release.set()
    leader.join(timeout=5)
    follower.join(timeout=5)

    assert len(errors) == 2
    assert all(isinstance(exc, news_module.NewsQuotaExceeded) for exc in errors)
    assert "news_ERR" not in news_module._inflight
