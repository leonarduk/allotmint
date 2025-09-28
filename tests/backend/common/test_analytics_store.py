from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from backend.common import analytics_store
from backend.config import config


@pytest.fixture(autouse=True)
def analytics_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure analytics events are written inside the pytest sandbox."""

    accounts_root = tmp_path / "accounts"
    accounts_root.mkdir()

    monkeypatch.setattr(config, "repo_root", tmp_path)
    monkeypatch.setattr(config, "accounts_root", accounts_root)

    # Ensure each test starts with a clean slate
    analytics_store.clear_events()


def test_append_and_load_round_trip() -> None:
    first = analytics_store.AnalyticsEvent(
        source="frontend",
        event="clicked",
        user="demo",
        occurred_at=datetime(2024, 1, 1, 12, 30, tzinfo=timezone.utc),
        metadata={"button": "start"},
    )
    second = analytics_store.AnalyticsEvent(
        source="worker",
        event="processed",
        user=None,
        occurred_at=datetime(2024, 1, 1, 12, 31, tzinfo=timezone.utc),
        metadata=None,
    )

    analytics_store.append_event(first)
    analytics_store.append_event(second)

    loaded = analytics_store.load_events(source="frontend")

    assert [evt.source for evt in loaded] == ["frontend"]
    assert loaded[0].event == first.event
    assert loaded[0].metadata == first.metadata
    assert loaded[0].occurred_at.isoformat() == first.occurred_at.isoformat()


def test_load_events_skips_invalid_rows_and_normalises(monkeypatch: pytest.MonkeyPatch) -> None:
    events_path = analytics_store._events_path()  # pylint: disable=protected-access

    valid_time = datetime(2023, 12, 31, 23, 59, tzinfo=timezone.utc)
    fallback_time = datetime(2024, 2, 1, 15, 0, tzinfo=timezone.utc)

    lines = [
        "",  # blank line should be ignored
        "{\"source\": \"broken\"",  # invalid JSON skipped
        json.dumps(
            {
                "source": "valid",
                "event": "ok",
                "user": "demo",
                "occurred_at": valid_time.isoformat(),
                "metadata": {"foo": "bar"},
            }
        ),
        json.dumps(
            {
                "source": "missing",
                "event": "no_ts",
                "metadata": ["unexpected"],  # non-dict coerced to None
            }
        ),
        json.dumps(
            {
                "source": "bad",
                "event": "bad_ts",
                "occurred_at": "not-a-timestamp",
                "metadata": {"value": 1},
            }
        ),
    ]
    events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    real_datetime = datetime

    class DateTimeStub:
        def __init__(self) -> None:
            self.calls: list[timezone] = []

        def now(self, tz: timezone) -> datetime:
            self.calls.append(tz)
            return fallback_time

        def fromisoformat(self, value: str) -> datetime:
            return real_datetime.fromisoformat(value)

    stub = DateTimeStub()
    monkeypatch.setattr(analytics_store, "datetime", stub)

    events = analytics_store.load_events()

    assert [evt.source for evt in events] == ["valid", "missing", "bad"]

    valid, missing, bad = events

    assert valid.occurred_at == valid_time
    assert valid.metadata == {"foo": "bar"}

    assert missing.metadata is None
    assert missing.occurred_at == fallback_time

    assert bad.metadata == {"value": 1}
    assert bad.occurred_at == fallback_time

    assert stub.calls == [timezone.utc, timezone.utc]


def test_clear_events_removes_file() -> None:
    event = analytics_store.AnalyticsEvent(
        source="frontend",
        event="clicked",
        user="demo",
        occurred_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        metadata=None,
    )
    analytics_store.append_event(event)

    path = analytics_store._events_path()  # pylint: disable=protected-access
    assert path.exists()

    analytics_store.clear_events()

    assert not path.exists()
    assert analytics_store.load_events() == []
