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


@pytest.fixture(autouse=True)
def _news_provider_defaults(monkeypatch, tmp_path):
    """Configure an AlphaVantage key, a fresh Yahoo cooldown and throwaway
    per-provider quota counters per test.

    With no key, ``fetch_news_alpha`` skips AlphaVantage entirely, so tests
    that mock its response need one set; tests for the no-key path override
    it. A fresh cooldown keeps a 429 tripped in one test from silencing Yahoo
    in the next.
    """
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", "test-key")
    # Providers spend their own quota as they make requests; keep the counters
    # (derived from COUNTER_FILE) out of the real data/cache directory.
    monkeypatch.setattr(news_module, "COUNTER_FILE", tmp_path / "news_requests.json")
    monkeypatch.setattr(
        news_module,
        "_yahoo_cooldown",
        news_module._ProviderCooldown(news_module.YAHOO_COOLDOWN_DEFAULT, news_module.YAHOO_COOLDOWN_MAX),
    )


class _FakeDate(date):
    """Helper used to override ``date.today`` within tests."""

    _value = date(2023, 1, 1)

    @classmethod
    def today(cls) -> "_FakeDate":  # type: ignore[override]
        return cls(cls._value.year, cls._value.month, cls._value.day)


def test_provider_quota_counts_per_day(monkeypatch, tmp_path):
    counter_path = tmp_path / "news_requests.json"
    monkeypatch.setattr(news_module, "COUNTER_FILE", counter_path)
    monkeypatch.setattr(news_module, "date", _FakeDate)
    monkeypatch.setattr(news_module.cfg, "news_requests_per_day", 2)
    quota = news_module._ALPHA_QUOTA

    assert quota.path == counter_path
    assert quota.load() == {"date": "2023-01-01", "count": 0}

    quota.save({"date": "2023-01-01", "count": 1})
    assert json.loads(counter_path.read_text()) == {"date": "2023-01-01", "count": 1}
    assert quota.available() is True

    assert quota.try_consume() is True
    assert quota.load()["count"] == 2
    assert quota.available() is False
    assert quota.try_consume() is False

    class _NextDay(_FakeDate):
        _value = date(2023, 1, 2)

    monkeypatch.setattr(news_module, "date", _NextDay)
    assert quota.load() == {"date": "2023-01-02", "count": 0}


def test_provider_quotas_use_separate_counters_and_limits(monkeypatch, tmp_path):
    monkeypatch.setattr(news_module, "COUNTER_FILE", tmp_path / "news_requests.json")
    monkeypatch.setattr(news_module.cfg, "news_requests_per_day", 1)
    monkeypatch.setattr(news_module.cfg, "yahoo_news_requests_per_day", 3)

    assert news_module._ALPHA_QUOTA.try_consume() is True
    assert news_module._ALPHA_QUOTA.try_consume() is False
    # Exhausting AlphaVantage leaves Yahoo's own budget untouched.
    assert news_module._YAHOO_QUOTA.try_consume() is True
    assert news_module._YAHOO_QUOTA.path == tmp_path / "news_requests_yahoo.json"
    assert news_module._GOOGLE_QUOTA.path == tmp_path / "news_requests_google.json"
    assert json.loads((tmp_path / "news_requests.json").read_text())["count"] == 1
    assert json.loads((tmp_path / "news_requests_yahoo.json").read_text())["count"] == 1


def test_provider_quota_resets_unreadable_counter(monkeypatch, tmp_path, caplog):
    counter_path = tmp_path / "news_requests.json"
    counter_path.write_text("{not json")
    monkeypatch.setattr(news_module, "COUNTER_FILE", counter_path)

    with caplog.at_level("WARNING", logger=news_module.__name__):
        assert news_module._ALPHA_QUOTA.load()["count"] == 0
    assert any("unreadable AlphaVantage news quota" in r.getMessage() for r in caplog.records)


def test_fetch_news_yahoo(monkeypatch):
    captured: Dict[str, object] = {}

    def fake_get(url, params=None, timeout=10, **kwargs):
        captured["url"] = url
        captured["params"] = params
        captured["impersonate"] = kwargs.get("impersonate")

        class Response:
            status_code = 200
            headers: Dict[str, str] = {}

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
    # Yahoo's search resolves its own symbols best, so the query is the symbol.
    assert captured["params"]["q"] == "PFE"
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
            status_code = 200
            headers: Dict[str, str] = {}

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
    # Quotas are per provider; leave AlphaVantage as the only one with budget
    # so exhausting it exhausts news as a whole.
    monkeypatch.setattr(news_module.cfg, "yahoo_news_requests_per_day", 0)
    monkeypatch.setattr(news_module.cfg, "google_news_requests_per_day", 0)
    # create_app() reloads config, resetting the key the autouse fixture set.
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", "test-key")

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
    monkeypatch.setattr(news_module, "_can_request_news", fake_quota)

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
    monkeypatch.setattr(news_module, "_can_request_news", lambda: False)

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
    monkeypatch.setattr(news_module, "_can_request_news", lambda: False)

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
    monkeypatch.setattr(news_module, "_can_request_news", lambda: True)
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
    gate_calls = {"count": 0}

    def counting_gate() -> bool:
        gate_calls["count"] += 1
        return True

    monkeypatch.setattr(news_module, "_can_request_news", counting_gate)

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
    # One fetch means one pass through the quota gate, not one per caller.
    assert gate_calls["count"] == 1
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


def test_yahoo_client_is_curl_cffi():
    """``curl_requests`` must resolve to ``curl_cffi.requests``, not ``requests``.

    The lazy proxy defers the import, so assert what it loads rather than
    trusting the name.
    """

    import curl_cffi.requests

    assert news_module.curl_requests.get is curl_cffi.requests.get
    assert news_module.curl_requests.get is not news_module.requests.get


def test_single_flight_caller_after_resolve_reuses_result(monkeypatch):
    """A caller arriving after the leader resolves its future, but before the
    entry is dropped, must reuse the result rather than fetch again.

    Pins the ordering in ``_single_flight``: the future is resolved before the
    in-flight entry is removed, so there is no window in which a new caller
    finds no entry while the leader's result is still pending publication.
    """

    from concurrent.futures import Future

    late_calls = {"fetch": 0}
    late_results: List[List[Dict[str, str]]] = []
    injected: List[bool] = []

    def late_fetch() -> List[Dict[str, str]]:
        late_calls["fetch"] += 1
        return [{"headline": "late", "url": "https://example.com/late"}]

    class LateCallerFuture(Future):
        def set_result(self, result):
            super().set_result(result)
            # Runs after the leader resolves and before its ``finally`` pops.
            # Only the leader's future injects the late caller.
            if not injected:
                injected.append(True)
                late_results.append(news_module._single_flight("news_LATE", late_fetch))

    monkeypatch.setattr(news_module, "Future", LateCallerFuture)

    leader_result = [{"headline": "leader", "url": "https://example.com/leader"}]
    assert news_module._single_flight("news_LATE", lambda: leader_result) == leader_result

    assert late_calls["fetch"] == 0
    assert late_results == [leader_result]
    assert "news_LATE" not in news_module._inflight


def test_single_flight_fetches_again_after_completion():
    calls = {"count": 0}

    def fetch() -> List[Dict[str, str]]:
        calls["count"] += 1
        return []

    news_module._single_flight("news_AGAIN", fetch)
    news_module._single_flight("news_AGAIN", fetch)

    assert calls["count"] == 2
    assert news_module._inflight == {}


def test_fetch_news_alpha_skips_request_without_key(monkeypatch):
    """No key means no request: ``demo`` only serves IBM, so it always misses."""

    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)

    def fail_get(*args, **kwargs):
        raise AssertionError("AlphaVantage must not be called without a key")

    monkeypatch.setattr(news_module.requests, "get", fail_get)

    assert news_module.fetch_news_alpha("AAPL") == []


@pytest.mark.parametrize("notice_key", ["Information", "Note", "Error Message"])
def test_fetch_news_alpha_logs_notice_instead_of_feed(monkeypatch, caplog, notice_key):
    def fake_get(url, params=None, timeout=10, **kwargs):
        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {notice_key: "Thank you for using Alpha Vantage! Rate limit reached."}

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    with caplog.at_level("WARNING", logger=news_module.__name__):
        assert news_module.fetch_news_alpha("AAPL") == []

    messages = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert any(notice_key in m and "Rate limit reached" in m for m in messages)


def _yahoo_response(status_code: int, headers: Dict[str, str] | None = None):
    class Response:
        def __init__(self) -> None:
            self.status_code = status_code
            self.headers = headers or {}

        def raise_for_status(self):
            return None

        def json(self):
            return {"news": [{"title": "PFE stock update", "link": "https://example.com/pfe"}]}

    return Response()


def test_fetch_news_yahoo_429_starts_cooldown_and_skips_later_calls(monkeypatch, caplog):
    calls = {"count": 0}

    def fake_get(url, params=None, timeout=10, **kwargs):
        calls["count"] += 1
        return _yahoo_response(429, {"Retry-After": "120"})

    monkeypatch.setattr(news_module.curl_requests, "get", fake_get)

    with caplog.at_level("WARNING", logger=news_module.__name__):
        assert news_module.fetch_news_yahoo("PFE") == []
        assert news_module.fetch_news_yahoo("AZN") == []

    assert calls["count"] == 1
    assert 0 < news_module._yahoo_cooldown.remaining() <= 120
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1
    assert "429" in warnings[0] and "120 seconds" in warnings[0]


def test_fetch_news_yahoo_resumes_after_cooldown(monkeypatch):
    clock = {"now": 1000.0}
    monkeypatch.setattr(news_module.time, "monotonic", lambda: clock["now"])
    responses = [_yahoo_response(429), _yahoo_response(200)]
    monkeypatch.setattr(news_module.curl_requests, "get", lambda *a, **k: responses.pop(0))

    assert news_module.fetch_news_yahoo("PFE") == []
    clock["now"] += news_module.YAHOO_COOLDOWN_DEFAULT + 1

    assert news_module.fetch_news_yahoo("PFE") == [{"headline": "PFE stock update", "url": "https://example.com/pfe"}]


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [
        (None, news_module.YAHOO_COOLDOWN_DEFAULT),
        ("not-a-number", news_module.YAHOO_COOLDOWN_DEFAULT),
        ("Wed, 21 Oct 2026 07:28:00 GMT", news_module.YAHOO_COOLDOWN_DEFAULT),
        ("30", 30),
        ("999999", news_module.YAHOO_COOLDOWN_MAX),
    ],
)
def test_provider_cooldown_trip_parses_retry_after(retry_after, expected):
    cooldown = news_module._ProviderCooldown(news_module.YAHOO_COOLDOWN_DEFAULT, news_module.YAHOO_COOLDOWN_MAX)
    assert cooldown.trip(retry_after) == expected


def test_fetch_news_falls_through_to_google_during_yahoo_cooldown(monkeypatch, caplog):
    monkeypatch.setattr(news_module, "fetch_news_alpha", lambda ticker: [])
    news_module._yahoo_cooldown.trip()

    def fail_get(*args, **kwargs):
        raise AssertionError("Yahoo must not be called during cooldown")

    monkeypatch.setattr(news_module.curl_requests, "get", fail_get)
    google = [{"headline": "PFE shares rise", "url": "https://example.com/g"}]
    monkeypatch.setattr(news_module, "fetch_news_google", lambda ticker: google)

    with caplog.at_level("ERROR", logger=news_module.__name__):
        assert news_module._fetch_news("PFE") == google
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Adobe Inc Comm Stk US$.0001 *R", "Adobe"),
        ("United Parcel Service Class &#39;B&#39; Com Stock US$0.01 (CDI) *R", "United Parcel Service"),
        ("Alphabet Inc. (Class A)", "Alphabet"),
        ("AstraZeneca PLC Ord Shs $0.25", "AstraZeneca"),
        ("Rio Tinto Ord 10p", "Rio Tinto"),
        # Pence par value without a preceding "Ord".
        ("Rio Tinto 10p", "Rio Tinto"),
        ("Rolls-Royce Holdings plc Ord 20p", "Rolls-Royce Holdings"),
        # Bare integers are part of index/fund names, not par values.
        ("Vanguard S&P 500 UCITS ETF", "Vanguard S&P 500 UCITS ETF"),
        ("iShares Core FTSE 100 UCITS ETF", "iShares Core FTSE 100 UCITS ETF"),
        ("BP p.l.c.", "BP"),
        ("Moody's Corporation", "Moody's"),
        ("Lloyds Banking Group plc", "Lloyds Banking Group"),
        # "Stock" alone is part of a fund's name, not share-class noise.
        ("Vanguard Total World Stock ETF", "Vanguard Total World Stock ETF"),
        ("Vanguard FTSE All-World UCITS ETF (GBP)", "Vanguard FTSE All-World UCITS ETF"),
        ("Inc", None),
        (None, None),
    ],
)
def test_normalise_instrument_name(raw, expected):
    assert news_module._normalise_instrument_name(raw) == expected


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [
        ("ADBE.N", ("ADBE", "N")),
        ("azn.l", ("AZN", "L")),
        ("VUSA.LSE", ("VUSA", "LSE")),
        ("^FTSE", ("^FTSE", None)),
        ("PFE", ("PFE", None)),
        # Share-class dots are part of the symbol, not an exchange code.
        ("BRK.B", ("BRK.B", None)),
    ],
)
def test_split_ticker(ticker, expected):
    assert news_module._split_ticker(ticker) == expected


def _stub_instrument_name(monkeypatch, names):
    monkeypatch.setattr(news_module, "get_instrument_meta", lambda ticker: {"name": names.get(ticker)})


@pytest.mark.parametrize(
    ("ticker", "name", "google", "yahoo"),
    [
        ("ADBE.N", "Adobe Inc Comm Stk US$.0001 *R", '"Adobe" OR ADBE stock', "ADBE"),
        ("AZN.L", "AstraZeneca PLC", '"AstraZeneca" OR AZN stock', "AZN.L"),
        ("^FTSE", None, "FTSE stock", "^FTSE"),
    ],
)
def test_provider_queries_drop_suffix_and_name_noise(monkeypatch, ticker, name, google, yahoo):
    _stub_instrument_name(monkeypatch, {ticker: name})
    subject = news_module._news_subject(ticker)

    assert news_module._google_query(subject) == google
    assert news_module._yahoo_query(subject) == yahoo


@pytest.mark.parametrize(
    ("ticker", "expected"),
    [("ADBE.N", "ADBE"), ("AZN.L", "AZN.LON"), ("PFE", "PFE")],
)
def test_alpha_vantage_ticker_uses_alpha_vantage_suffixes(monkeypatch, ticker, expected):
    captured = {}

    def fake_get(url, params=None, timeout=10, **kwargs):
        captured["tickers"] = params["tickers"]

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"feed": []}

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)
    news_module.fetch_news_alpha(ticker)

    assert captured["tickers"] == expected


def test_relevance_filter_matches_clean_name_and_bare_symbol():
    subject = news_module._NewsSubject(symbol="ADBE", exchange="N", name="Adobe")

    assert news_module._is_finance_related("Adobe beats on Firefly demand", subject)
    assert news_module._is_finance_related("Why ADBE fell today", subject)
    # Whole-symbol matches only: "ADBEX" is not ADBE.
    assert not news_module._is_finance_related("ADBEX launches new gadget", subject)
    assert not news_module._is_finance_related("Celebrity gossip roundup", subject)


def test_fetch_news_google_uses_clean_query_and_keeps_name_only_headlines(monkeypatch):
    _stub_instrument_name(monkeypatch, {"ADBE.N": "Adobe Inc Comm Stk US$.0001 *R"})
    captured = {}
    xml = """
        <rss><channel>
          <item><title>Adobe unveils new AI tools</title><link>https://example.com/a</link></item>
          <item><title>Celebrity gossip roundup</title><link>https://example.com/b</link></item>
        </channel></rss>
    """

    def fake_get(url, params=None, timeout=10, **kwargs):
        captured["q"] = params["q"]

        class Response:
            text = xml

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_get)

    items = news_module.fetch_news_google("ADBE.N")

    assert captured["q"] == '"Adobe" OR ADBE stock'
    # Passes on the clean name alone: no symbol, no finance keyword.
    assert items == [{"headline": "Adobe unveils new AI tools", "url": "https://example.com/a"}]


def test_relevance_symbol_match_is_case_sensitive():
    """Tickers that are ordinary words must not match prose ("all", "it")."""

    subject = news_module._NewsSubject(symbol="ALL", exchange="N", name=None)

    assert news_module._is_finance_related("ALL raises dividend outlook", subject)
    assert not news_module._is_finance_related("All the gadgets we loved this year", subject)


def _empty_yahoo(*args, **kwargs):
    return _yahoo_response(200)


def _set_quota_limits(monkeypatch, alpha: int, yahoo: int, google: int) -> None:
    monkeypatch.setattr(news_module.cfg, "news_requests_per_day", alpha)
    monkeypatch.setattr(news_module.cfg, "yahoo_news_requests_per_day", yahoo)
    monkeypatch.setattr(news_module.cfg, "google_news_requests_per_day", google)


def test_skipped_alpha_vantage_spends_no_alpha_quota(monkeypatch):
    """The bug: with no key, every fetch still spent AlphaVantage's 25/day."""

    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)
    monkeypatch.setattr(news_module.curl_requests, "get", _empty_yahoo)

    items = news_module._fetch_news("PFE")

    assert items == [{"headline": "PFE stock update", "url": "https://example.com/pfe"}]
    assert news_module._ALPHA_QUOTA.load()["count"] == 0
    assert news_module._YAHOO_QUOTA.load()["count"] == 1
    assert news_module._GOOGLE_QUOTA.load()["count"] == 0


def test_yahoo_cooldown_spends_no_yahoo_quota(monkeypatch):
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)
    news_module._yahoo_cooldown.trip()
    google = [{"headline": "PFE shares rise", "url": "https://example.com/g"}]

    def fake_google_get(url, params=None, timeout=10, **kwargs):
        class Response:
            text = "<rss><channel><item><title>PFE shares rise</title><link>https://example.com/g</link></item></channel></rss>"

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(news_module.requests, "get", fake_google_get)

    assert news_module._fetch_news("PFE") == google
    assert news_module._YAHOO_QUOTA.load()["count"] == 0
    assert news_module._GOOGLE_QUOTA.load()["count"] == 1


def test_exhausted_provider_is_skipped_without_a_request(monkeypatch):
    _set_quota_limits(monkeypatch, alpha=0, yahoo=1, google=1)

    def fail_alpha_get(*args, **kwargs):
        raise AssertionError("AlphaVantage must not be called once its quota is spent")

    monkeypatch.setattr(news_module.requests, "get", fail_alpha_get)
    monkeypatch.setattr(news_module.curl_requests, "get", _empty_yahoo)

    assert news_module._fetch_news("PFE") == [{"headline": "PFE stock update", "url": "https://example.com/pfe"}]
    assert news_module._YAHOO_QUOTA.load()["count"] == 1


@pytest.mark.parametrize(
    ("key", "limits", "cooldown", "expected"),
    [
        # Only Google has budget: news is still available.
        (None, (0, 0, 1), False, True),
        # AlphaVantage budget is irrelevant without a key.
        (None, (5, 0, 0), False, False),
        ("test-key", (5, 0, 0), False, True),
        # Yahoo budget is unusable while it is cooling down after a 429.
        (None, (0, 5, 0), True, False),
        (None, (0, 5, 0), False, True),
    ],
)
def test_can_request_news_needs_one_usable_provider(monkeypatch, key, limits, cooldown, expected):
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", key)
    _set_quota_limits(monkeypatch, *limits)
    if cooldown:
        news_module._yahoo_cooldown.trip()

    assert news_module._can_request_news() is expected


def test_get_cached_news_raises_only_when_every_provider_is_exhausted(monkeypatch, tmp_path):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)
    _set_quota_limits(monkeypatch, alpha=25, yahoo=0, google=0)

    with pytest.raises(news_module.NewsQuotaExceeded):
        news_module.get_cached_news("PFE", raise_on_quota_exhausted=True)


def test_fetch_news_raises_when_no_provider_could_spend(monkeypatch):
    """The gate passed, but every budget was gone by the time providers ran."""

    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)
    _set_quota_limits(monkeypatch, alpha=25, yahoo=0, google=0)

    def fail_get(*args, **kwargs):
        raise AssertionError("no provider should make a request without quota")

    monkeypatch.setattr(news_module.requests, "get", fail_get)
    monkeypatch.setattr(news_module.curl_requests, "get", fail_get)

    with pytest.raises(news_module.NewsQuotaExceeded):
        news_module._fetch_news("PFE")
    # The per-fetch spend record is cleared afterwards.
    assert news_module._spent_quota.get() is None


def test_fetch_news_empty_after_a_real_request_is_not_quota_exhaustion(monkeypatch):
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)
    _set_quota_limits(monkeypatch, alpha=0, yahoo=0, google=1)

    def empty_google(url, params=None, timeout=10, **kwargs):
        class Response:
            text = "<rss><channel></channel></rss>"

            def raise_for_status(self):
                return None

        return Response()

    monkeypatch.setattr(news_module.requests, "get", empty_google)

    # Google spent its last unit and found nothing: a genuine empty result.
    assert news_module._fetch_news("PFE") == []
    assert news_module._GOOGLE_QUOTA.load()["count"] == 1


def test_get_cached_news_lost_quota_race_serves_cache_instead_of_caching_empty(monkeypatch, tmp_path):
    """Gate says yes, a concurrent fetch takes the last unit, providers spend nothing."""

    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)
    _set_quota_limits(monkeypatch, alpha=0, yahoo=0, google=0)
    # Stale verdict from before the concurrent fetch drained the budget.
    monkeypatch.setattr(news_module, "_can_request_news", lambda: True)

    cached = [{"headline": "Cached", "url": "https://example.com/cached"}]
    page_cache.save_cache("news_PFE", cached)
    monkeypatch.setattr(page_cache, "is_stale", lambda page, ttl: True)

    result = news_module.get_cached_news("PFE")

    assert result == [{**cached[0], "stale": False}]
    # The cache keeps the good payload rather than being overwritten with [].
    assert page_cache.load_cache("news_PFE") == cached


def test_get_cached_news_lost_quota_race_without_cache_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(page_cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(page_cache, "schedule_refresh", lambda *a, **k: None)
    monkeypatch.setattr(news_module.cfg, "alpha_vantage_key", None)
    _set_quota_limits(monkeypatch, alpha=0, yahoo=0, google=0)
    monkeypatch.setattr(news_module, "_can_request_news", lambda: True)

    with pytest.raises(news_module.NewsQuotaExceeded):
        news_module.get_cached_news("PFE", raise_on_quota_exhausted=True)
    assert page_cache.load_cache("news_PFE") is None


def test_exhausted_quota_logs_info_once_per_day(monkeypatch, caplog):
    monkeypatch.setattr(news_module, "date", _FakeDate)
    monkeypatch.setattr(news_module.cfg, "yahoo_news_requests_per_day", 0)
    quota = news_module._ProviderQuota("Yahoo", "yahoo_news_requests_per_day", 500, "yahoo")

    with caplog.at_level("DEBUG", logger=news_module.__name__):
        assert quota.try_consume() is False
        assert quota.try_consume() is False

        class _NextDay(_FakeDate):
            _value = date(2023, 1, 2)

        monkeypatch.setattr(news_module, "date", _NextDay)
        assert quota.try_consume() is False

    exhausted = [r for r in caplog.records if "news quota exhausted" in r.getMessage()]
    # First skip of each day at INFO, repeats the same day at DEBUG.
    assert [r.levelname for r in exhausted] == ["INFO", "DEBUG", "INFO"]
    assert "Yahoo news quota exhausted for today (limit 0); skipping Yahoo until tomorrow" in exhausted[0].getMessage()
