"""Startup warm-up of the admin pages' per-file caches (#10754)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from backend.bootstrap import admin_cache_warm
from backend.common import admin_cache_state


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
    monkeypatch.setattr(timeseries_admin, "local_timeseries_summaries", lambda: called.append("timeseries"))

    def fake_series(**_kwargs):
        from backend.timeseries.cache import is_cache_only

        called.append(f"series cache_only={is_cache_only()}")

    monkeypatch.setattr(issues, "aggregate_series_issues", fake_series)

    for _, step in admin_cache_warm._warm_steps():
        step()

    assert called == ["instruments", "timeseries", "series cache_only=True"]


def test_background_warm_runs_on_a_daemon_thread(monkeypatch):
    """A daemon thread, so stopping or reloading the server never waits for a scan."""
    import threading

    seen: list[tuple[str, bool]] = []

    def record():
        current = threading.current_thread()
        seen.append((current.name, current.daemon))

    monkeypatch.setattr(admin_cache_warm, "warm_admin_caches", record)

    thread = admin_cache_warm.start_admin_cache_warm_thread()
    thread.join(5)

    assert thread.daemon
    assert seen == [("admin-cache-warm", True)]


def test_background_warm_failure_is_logged_not_raised(monkeypatch, caplog):
    def boom():
        raise RuntimeError("warm failed")

    monkeypatch.setattr(admin_cache_warm, "warm_admin_caches", boom)

    admin_cache_warm.start_admin_cache_warm_thread().join(5)

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
    """Startup returns at once and the loop keeps serving while a scan blocks (#7690)."""
    import threading
    import time

    release = threading.Event()
    started = threading.Event()

    def slow_warm():
        started.set()
        release.wait(5)  # stands in for a long, blocking scan

    monkeypatch.setattr(admin_cache_warm, "warm_admin_caches", slow_warm)

    async def scenario() -> float:
        thread = admin_cache_warm.start_admin_cache_warm_thread()
        while not started.is_set():
            await asyncio.sleep(0.01)
        worst = 0.0
        for _ in range(20):  # loop ticks while the warm-up is still blocked
            tick = time.perf_counter()
            await asyncio.sleep(0)
            worst = max(worst, time.perf_counter() - tick)
        assert thread.is_alive()
        release.set()
        thread.join(5)
        return worst

    assert asyncio.run(scenario()) < 0.5


def test_startup_starts_the_warm_thread_only_when_allowed(monkeypatch):
    from backend.bootstrap import startup

    started: list[str] = []
    monkeypatch.setattr(admin_cache_warm, "start_admin_cache_warm_thread", lambda: started.append("warm"))
    monkeypatch.setattr(admin_cache_warm, "should_warm_admin_caches", lambda cfg: cfg.app_env == "local")
    monkeypatch.setattr("backend.common.portfolio_utils.refresh_snapshot_async", lambda days: None)
    monkeypatch.setattr("backend.tasks.nav_refresh.start_nav_refresh_task", lambda cfg: None)

    for app_env in ("local", "aws"):
        cfg = SimpleNamespace(app_env=app_env, skip_snapshot_warm=True, snapshot_warm_days=1)
        app = SimpleNamespace(state=SimpleNamespace(background_tasks=[]))
        asyncio.run(startup.AppLifecycleService(cfg).startup(app))

    assert started == ["warm"]


def test_each_step_stops_warming_as_soon_as_it_finishes(monkeypatch):
    """An endpoint stops serving partial results once its own step is done, not the whole warm-up."""
    names = admin_cache_state.WARM_STEP_NAMES
    observed: list[tuple[bool, ...]] = []

    def step():
        observed.append(tuple(admin_cache_state.is_step_warming(n) for n in names))

    monkeypatch.setattr(admin_cache_warm, "_warm_steps", lambda: [(n, step) for n in names])
    admin_cache_state.mark_steps_pending(names)

    admin_cache_warm.warm_admin_caches()

    assert observed == [(True, True, True), (False, True, True), (False, False, True)]
    assert not any(admin_cache_state.is_step_warming(n) for n in names)


def test_a_failing_step_stops_warming(monkeypatch):
    """A failed step falls back to scanning on request rather than serving partial results forever."""

    def boom():
        raise OSError("disk gone")

    monkeypatch.setattr(admin_cache_warm, "_warm_steps", lambda: [(admin_cache_state.INSTRUMENT_LIST, boom)])
    admin_cache_state.mark_steps_pending([admin_cache_state.INSTRUMENT_LIST])

    admin_cache_warm.warm_admin_caches()

    assert not admin_cache_state.is_step_warming(admin_cache_state.INSTRUMENT_LIST)


def test_unlisted_steps_are_cleared_when_the_warm_up_ends(monkeypatch):
    """A step that never ran (e.g. the step list failed to import) is not left pending."""

    def no_steps():
        raise ImportError("pandas missing")

    monkeypatch.setattr(admin_cache_warm, "_warm_steps", no_steps)
    admin_cache_state.mark_steps_pending(admin_cache_state.WARM_STEP_NAMES)

    with pytest.raises(ImportError):
        admin_cache_warm.warm_admin_caches()

    assert not any(admin_cache_state.is_step_warming(n) for n in admin_cache_state.WARM_STEP_NAMES)


def test_starting_the_thread_marks_every_step_pending_until_it_runs(monkeypatch):
    import threading

    release = threading.Event()
    seen: list[bool] = []

    def blocked_warm():
        seen.append(all(admin_cache_state.is_step_warming(n) for n in admin_cache_state.WARM_STEP_NAMES))
        release.wait(5)
        admin_cache_state.finish_all_steps()

    monkeypatch.setattr(admin_cache_warm, "warm_admin_caches", blocked_warm)

    thread = admin_cache_warm.start_admin_cache_warm_thread()
    assert admin_cache_state.is_step_warming(admin_cache_state.DATA_QUALITY_SERIES)
    release.set()
    thread.join(5)

    assert seen == [True]
