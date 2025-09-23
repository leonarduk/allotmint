"""Unit tests for helper functions in ``backend.routes.news``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest

from backend.routes import news as news_module


def _assert_refresh_call(call: dict[str, Any], *, page: str, delay: float | None) -> None:
    assert call["page"] == page
    assert call["ttl"] == news_module.NEWS_TTL
    assert callable(call["func"])
    assert call["func"].__name__ == "_call"
    assert call["can_refresh"] is news_module._can_request_news
    assert call["initial_delay"] == delay


def test_clean_str_strips_and_ignores_blank_or_non_strings():
    assert news_module._clean_str(" headline ") == "headline"
    assert news_module._clean_str("   ") is None
    assert news_module._clean_str(123) is None


def test_make_news_item_requires_headline_and_url():
    headline = "Some Headline"
    url = "https://example.com/story"
    assert news_module._make_news_item(headline, url) == {
        "headline": headline,
        "url": url,
    }
    # Missing or invalid components should result in ``None``
    assert news_module._make_news_item(headline, None) is None
    assert news_module._make_news_item("   ", url) is None


def test_trim_payload_filters_invalid_entries():
    payload: List[Dict[str, Any]] = [
        {"headline": " First ", "url": " https://example.com/1 "},
        {"headline": "", "url": "https://example.com/ignored"},
        {"headline": "Second", "link": "wrong-key"},
        "not-a-dict",
        {"headline": "Third", "url": "https://example.com/3"},
    ]

    assert news_module._trim_payload(payload) == [
        {"headline": "First", "url": "https://example.com/1"},
        {"headline": "Third", "url": "https://example.com/3"},
    ]
    assert news_module._trim_payload({"unexpected": "mapping"}) == []


def test_isoformat_normalises_to_utc_seconds():
    naive = datetime(2024, 1, 2, 3, 4, 5)
    aware = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=2)))

    assert news_module._isoformat(None) is None
    assert news_module._isoformat(naive) == "2024-01-02T03:04:05Z"
    # Non-UTC aware datetimes should be converted to UTC
    assert news_module._isoformat(aware) == "2024-01-02T01:04:05Z"


@pytest.mark.parametrize(
    "value, expected",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("2024-06-01T12:34:56Z", "2024-06-01T12:34:56Z"),
        ("2024-06-01T12:34:56+02:00", "2024-06-01T10:34:56Z"),
        ("20240601T123456", "2024-06-01T12:34:56Z"),
        ("not-a-date", None),
    ],
)
def test_parse_alpha_time_handles_formats_and_invalid_values(value: str | None, expected: str | None):
    assert news_module._parse_alpha_time(value) == expected


def test_get_cached_news_returns_empty_for_blank_ticker(monkeypatch):
    def fail(*args, **kwargs):  # pragma: no cover - defensive guard in test
        raise AssertionError("should not be called for blank tickers")

    monkeypatch.setattr(news_module.page_cache, "load_cache", fail)
    monkeypatch.setattr(news_module.page_cache, "schedule_refresh", fail)

    assert news_module.get_cached_news("   ") == []


def test_get_cached_news_raises_on_quota_exhausted_without_cache(monkeypatch):
    scheduled: list[dict[str, Any]] = []

    def fake_schedule(page: str, ttl: int, func, *, can_refresh, initial_delay):
        scheduled.append(
            {
                "page": page,
                "ttl": ttl,
                "func": func,
                "can_refresh": can_refresh,
                "initial_delay": initial_delay,
            }
        )

    monkeypatch.setattr(news_module.page_cache, "load_cache", lambda page: None)
    monkeypatch.setattr(news_module.page_cache, "is_stale", lambda page, ttl: True)
    monkeypatch.setattr(news_module.page_cache, "time_until_stale", lambda page, ttl: 0)
    monkeypatch.setattr(news_module.page_cache, "schedule_refresh", fake_schedule)

    monkeypatch.setattr(news_module, "_try_consume_quota", lambda: False)

    def fail_fetch(*args, **kwargs):  # pragma: no cover - defensive guard in test
        raise AssertionError("fetch should not be attempted when quota exhausted")

    monkeypatch.setattr(news_module, "_fetch_news", fail_fetch)

    with pytest.raises(RuntimeError):
        news_module.get_cached_news("limited", raise_on_quota_exhausted=True)

    assert len(scheduled) == 1
    _assert_refresh_call(scheduled[0], page="news_LIMITED", delay=None)


def test_get_cached_news_reuses_fresh_cache(monkeypatch):
    cached_payload = [
        {"headline": "Cached", "url": "https://example.com/cached"},
        {"headline": "  Trim  ", "url": " https://example.com/trim "},
    ]
    scheduled: list[dict[str, Any]] = []

    def fake_schedule(page: str, ttl: int, func, *, can_refresh, initial_delay):
        scheduled.append(
            {
                "page": page,
                "ttl": ttl,
                "func": func,
                "can_refresh": can_refresh,
                "initial_delay": initial_delay,
            }
        )

    monkeypatch.setattr(news_module.page_cache, "load_cache", lambda page: cached_payload)
    monkeypatch.setattr(news_module.page_cache, "is_stale", lambda page, ttl: False)
    monkeypatch.setattr(news_module.page_cache, "time_until_stale", lambda page, ttl: 42.0)
    monkeypatch.setattr(news_module.page_cache, "schedule_refresh", fake_schedule)

    def fail_try_quota():  # pragma: no cover - defensive guard in test
        raise AssertionError("quota should not be consumed when cache fresh")

    monkeypatch.setattr(news_module, "_try_consume_quota", fail_try_quota)
    monkeypatch.setattr(news_module, "_fetch_news", fail_try_quota)

    result = news_module.get_cached_news("cached")

    assert result == [
        {"headline": "Cached", "url": "https://example.com/cached"},
        {"headline": "Trim", "url": "https://example.com/trim"},
    ]
    assert len(scheduled) == 1
    _assert_refresh_call(scheduled[0], page="news_CACHED", delay=42.0)

