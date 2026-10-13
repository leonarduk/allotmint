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


def test_warm_fills_the_real_caches_from_a_data_root(monkeypatch, tmp_path):
    """Unpatched steps against a real data root: afterwards each endpoint is served from cache."""
    import json

    import pandas as pd

    from backend.common import instruments
    from backend.config import config
    from backend.data_quality import issues
    from backend.routes import timeseries_admin
    from backend.timeseries import cache

    meta_dir = tmp_path / "timeseries" / "meta"
    meta_dir.mkdir(parents=True)
    parquet = meta_dir / "ABC_L.parquet"
    dates = pd.bdate_range("2026-01-05", periods=30)
    pd.DataFrame({"Date": dates, "Close": [100.0 + i for i in range(30)], "Source": ["A"] * 30}).to_parquet(parquet)
    (tmp_path / "instruments" / "L").mkdir(parents=True)
    (tmp_path / "instruments" / "L" / "ABC.json").write_text(
        json.dumps({"ticker": "ABC.L", "name": "Alpha"}), encoding="utf-8"
    )

    monkeypatch.setattr(config, "app_env", "local")
    monkeypatch.setattr(config, "data_root", tmp_path)
    monkeypatch.delenv("METADATA_BUCKET", raising=False)
    monkeypatch.setattr(cache, "_CACHE_BASE", str(tmp_path / "timeseries"))
    monkeypatch.setattr(instruments, "_INSTRUMENTS_DIR", tmp_path / "instruments")
    monkeypatch.setattr(issues, "_refresh_universe", lambda: [])
    # Other tests importlib.reload(backend.common.instruments); bind the modules
    # that imported its functions to the module object patched above.
    for module in (timeseries_admin, issues):
        monkeypatch.setattr(module, "get_instrument_meta", instruments.get_instrument_meta)
        monkeypatch.setattr(module, "instrument_meta_path", instruments.instrument_meta_path)
    instruments.get_instrument_meta.cache_clear()

    timings = admin_cache_warm.warm_admin_caches()

    assert set(timings) == {"instrument_list", "timeseries_summaries", "data_quality_series"}
    assert any(p.endswith("ABC.json") for p in instruments._LIST_CACHE)
    assert parquet in timeseries_admin._SUMMARY_CACHE
    assert ("ABC", "L") in issues._SERIES_ISSUE_CACHE

    def no_reads(*_args, **_kwargs):
        raise AssertionError("served from cache, nothing should be re-read")

    monkeypatch.setattr(timeseries_admin.pd, "read_parquet", no_reads)
    monkeypatch.setattr(issues, "load_cached_meta_timeseries_full", no_reads)
    monkeypatch.setattr(instruments, "_load_listed_instrument", no_reads)
    assert [s["name"] for s in timeseries_admin.timeseries_admin()] == ["Alpha"]
    assert [i["ticker"] for i in instruments.list_instruments()] == ["ABC.L"]
    issues.aggregate_series_issues()


def test_event_loop_keeps_serving_while_the_warm_up_runs(monkeypatch):
    """The warm-up blocks a worker thread, never the loop, so /health stays responsive (#7690)."""
    import threading
    import time

    release = threading.Event()
    started = threading.Event()

    def slow_warm():
        started.set()
        release.wait(5)  # stands in for a long, blocking scan

    monkeypatch.setattr(admin_cache_warm, "warm_admin_caches", slow_warm)

    async def scenario() -> float:
        task = asyncio.create_task(AppLifecycleService._warm_admin_caches_background())
        while not started.is_set():
            await asyncio.sleep(0.01)
        worst = 0.0
        for _ in range(20):  # loop ticks while the warm-up is still blocked
            tick = time.perf_counter()
            await asyncio.sleep(0)
            worst = max(worst, time.perf_counter() - tick)
        assert not task.done()
        release.set()
        await task
        return worst

    assert asyncio.run(scenario()) < 0.5
