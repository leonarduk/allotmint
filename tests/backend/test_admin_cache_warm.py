"""Startup warm-up of the admin pages' per-file caches (#10754)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.bootstrap import admin_cache_warm
from backend.bootstrap.startup import AppLifecycleService


@pytest.mark.parametrize(
    ("env", "app_env", "expected"),
    [
        ({}, "local", True),
        ({}, None, True),
        ({}, "aws", False),
        ({"TESTING": "1"}, "local", False),
        ({"AWS_LAMBDA_FUNCTION_NAME": "fn"}, "local", False),
    ],
)
def test_should_warm_only_for_a_local_non_test_server(monkeypatch, env, app_env, expected):
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert admin_cache_warm.should_warm_admin_caches(SimpleNamespace(app_env=app_env)) is expected


def test_warm_runs_every_step_and_survives_a_failing_one(monkeypatch, caplog):
    ran: list[str] = []

    def failing() -> None:
        ran.append("timeseries")
        raise OSError("disk gone")

    monkeypatch.setattr(
        admin_cache_warm,
        "_warm_steps",
        lambda: [
            ("instruments", lambda: ran.append("instruments")),
            ("timeseries", failing),
            ("dq", lambda: ran.append("dq")),
        ],
    )

    timings = admin_cache_warm.warm_admin_caches()

    assert ran == ["instruments", "timeseries", "dq"]
    assert set(timings) == {"instruments", "dq"}
    assert "Admin cache warm-up step timeseries failed" in caplog.text


def test_warm_steps_fill_the_real_caches(monkeypatch):
    """Each step calls the cached function the matching endpoint uses."""
    from backend.common import instruments
    from backend.data_quality import issues
    from backend.routes import timeseries_admin

    called: list[str] = []
    monkeypatch.setattr(instruments, "list_instruments", lambda: called.append("instruments"))
    monkeypatch.setattr(timeseries_admin, "timeseries_admin", lambda: called.append("timeseries"))

    def fake_series(**_kwargs):
        from backend.timeseries.cache import is_cache_only

        called.append(f"series cache_only={is_cache_only()}")

    monkeypatch.setattr(issues, "aggregate_series_issues", fake_series)

    for _, step in admin_cache_warm._warm_steps():
        step()

    assert called == ["instruments", "timeseries", "series cache_only=True"]


def test_background_warm_runs_off_the_event_loop(monkeypatch):
    import threading

    threads: list[str] = []
    monkeypatch.setattr(admin_cache_warm, "warm_admin_caches", lambda: threads.append(threading.current_thread().name))

    asyncio.run(AppLifecycleService._warm_admin_caches_background())

    assert threads and threads[0] != threading.main_thread().name


def test_background_warm_failure_is_logged_not_raised(monkeypatch, caplog):
    def boom():
        raise RuntimeError("warm failed")

    monkeypatch.setattr(admin_cache_warm, "warm_admin_caches", boom)

    asyncio.run(AppLifecycleService._warm_admin_caches_background())

    assert "Failed to warm admin page caches" in caplog.text
