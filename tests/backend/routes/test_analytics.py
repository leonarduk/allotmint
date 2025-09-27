from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from backend.common.analytics_store import AnalyticsEvent
from backend.config import config
from backend.routes import analytics


@pytest.fixture(autouse=True)
def restore_disable_auth() -> None:
    """Ensure tests do not leak config.disable_auth mutations."""

    original = config.disable_auth
    yield
    config.disable_auth = original


@pytest.mark.asyncio
async def test_optional_current_user_skips_when_auth_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Auth dependencies are bypassed when ``config.disable_auth`` is true."""

    oauth_called = False
    get_user_called = False

    async def fake_oauth2_scheme(request: Request) -> str:  # pragma: no cover - defensive
        nonlocal oauth_called
        oauth_called = True
        return "token"

    async def fake_get_current_user(token: str) -> str:  # pragma: no cover - defensive
        nonlocal get_user_called
        get_user_called = True
        return "user"

    monkeypatch.setattr(analytics, "oauth2_scheme", fake_oauth2_scheme)
    monkeypatch.setattr(analytics, "get_current_user", fake_get_current_user)

    config.disable_auth = True
    request = Request({"type": "http"})

    result = await analytics._optional_current_user(request)

    assert result is None
    assert oauth_called is False
    assert get_user_called is False


@pytest.mark.asyncio
async def test_log_event_appends_expected_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """``log_event`` stores an ``AnalyticsEvent`` matching the inbound payload."""

    captured: dict[str, AnalyticsEvent] = {}

    def fake_append_event(event: AnalyticsEvent) -> None:
        captured["event"] = event

    monkeypatch.setattr(analytics, "append_event", fake_append_event)

    config.disable_auth = False
    occurred_at = datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc)
    payload = analytics.AnalyticsEventIn(
        source="trail",
        event="view",
        user=None,
        metadata={"foo": "bar"},
        occurred_at=occurred_at,
    )

    response = await analytics.log_event(payload, current_user="authenticated-user")

    assert response == {"status": "ok"}
    stored = captured["event"]
    assert isinstance(stored, AnalyticsEvent)
    assert stored.source == "trail"
    assert stored.event == "view"
    assert stored.user == "authenticated-user"
    assert stored.metadata == {"foo": "bar"}
    assert stored.occurred_at == occurred_at


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload_kwargs", "expected_detail"),
    [
        ({"source": "unknown", "event": "view"}, "Unknown analytics source"),
        ({"source": "trail", "event": "does-not-exist"}, "Unsupported event for source"),
    ],
)
async def test_log_event_validation_errors(
    payload_kwargs: dict[str, Any], expected_detail: str
) -> None:
    """Validation failures raise ``HTTPException`` with a 400 status code."""

    payload = analytics.AnalyticsEventIn(**payload_kwargs)
    with pytest.raises(HTTPException) as exc:
        await analytics.log_event(payload, current_user=None)

    assert exc.value.status_code == 400
    assert exc.value.detail == expected_detail


@pytest.mark.asyncio
async def test_log_event_rejects_unserialisable_metadata() -> None:
    """Non JSON-serialisable metadata triggers a 400 ``HTTPException``."""

    payload = analytics.AnalyticsEventIn(
        source="trail",
        event="view",
        metadata={"bad": {1}},
    )

    with pytest.raises(HTTPException) as exc:
        await analytics.log_event(payload, current_user="user")

    assert exc.value.status_code == 400
    assert "Invalid metadata" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_funnel_with_no_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_funnel`` returns zero counts when the store is empty."""

    def fake_load_events(source: str) -> list[AnalyticsEvent]:
        assert source == "trail"
        return []

    monkeypatch.setattr(analytics, "load_events", fake_load_events)

    summary = await analytics.get_funnel("trail")

    assert summary.source == "trail"
    assert summary.total_events == 0
    assert summary.unique_users == 0
    assert summary.first_event_at is None
    assert summary.last_event_at is None
    assert [step.event for step in summary.steps] == ["view", "task_started", "task_completed"]
    assert all(step.count == 0 for step in summary.steps)
    assert summary.other_events is None


@pytest.mark.asyncio
async def test_get_funnel_with_events(monkeypatch: pytest.MonkeyPatch) -> None:
    """Aggregates funnel metrics, including unexpected events and timestamps."""

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    events = [
        AnalyticsEvent("trail", "view", "user-1", base, None),
        AnalyticsEvent("trail", "task_started", "user-1", base + timedelta(minutes=5), None),
        AnalyticsEvent("trail", "task_completed", "user-1", base + timedelta(minutes=10), None),
        AnalyticsEvent("trail", "view", "user-2", base + timedelta(minutes=15), None),
        AnalyticsEvent("trail", "task_started", None, base + timedelta(minutes=20), None),
        AnalyticsEvent("trail", "unexpected", "user-3", base + timedelta(minutes=25), None),
    ]

    def fake_load_events(source: str) -> list[AnalyticsEvent]:
        assert source == "trail"
        return events

    monkeypatch.setattr(analytics, "load_events", fake_load_events)

    summary = await analytics.get_funnel("trail")

    assert summary.source == "trail"
    assert summary.total_events == len(events)
    assert summary.unique_users == 3  # ``None`` is excluded from the count.
    assert summary.first_event_at == base
    assert summary.last_event_at == base + timedelta(minutes=25)
    assert [step.event for step in summary.steps] == ["view", "task_started", "task_completed"]
    assert [step.count for step in summary.steps] == [2, 2, 1]
    assert summary.other_events == {"unexpected": 1}

