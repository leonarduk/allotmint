from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.app as app_module
from backend.bootstrap.isolation import configure_runtime_paths
from backend.bootstrap.startup import AppLifecycleService
from backend.config import config


def test_create_app_test_isolation_copies_accounts_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    repo_root = tmp_path / "repo"
    accounts_root = repo_root / "data" / "accounts"
    owner_dir = accounts_root / "alice"
    owner_dir.mkdir(parents=True)
    (owner_dir / "ISA.json").write_text('{"account_type": "isa", "holdings": []}')

    monkeypatch.setenv("TESTING", "1")
    monkeypatch.setattr(config, "repo_root", repo_root, raising=False)
    monkeypatch.setattr(config, "accounts_root", accounts_root, raising=False)
    monkeypatch.setattr(config, "transactions_output_root", accounts_root, raising=False)

    runtime_paths = configure_runtime_paths(config)

    assert runtime_paths.accounts_root != accounts_root
    assert runtime_paths.accounts_root.exists()
    assert (runtime_paths.accounts_root / "alice" / "ISA.json").exists()
    assert config.transactions_output_root == runtime_paths.accounts_root


@pytest.mark.asyncio
async def test_lifecycle_service_warms_snapshot_and_registers_background_task(
    monkeypatch: pytest.MonkeyPatch,
):
    warmed = {}
    snapshot_task = asyncio.Future()

    monkeypatch.setattr("backend.bootstrap.startup._load_snapshot", lambda: ({"ABC": 1}, "ts"))
    monkeypatch.setattr(
        "backend.bootstrap.startup.refresh_snapshot_in_memory",
        lambda snapshot, ts: warmed.update({"snapshot": snapshot, "ts": ts}),
    )

    class InstrumentApi:
        latest = None
        primed = False

        @staticmethod
        def update_latest_prices_from_snapshot(snapshot):
            InstrumentApi.latest = snapshot

        @staticmethod
        def prime_latest_prices():
            InstrumentApi.primed = True

    monkeypatch.setattr(
        "backend.common.instrument_api.update_latest_prices_from_snapshot",
        InstrumentApi.update_latest_prices_from_snapshot,
    )
    monkeypatch.setattr(
        "backend.common.instrument_api.prime_latest_prices", InstrumentApi.prime_latest_prices
    )
    monkeypatch.setattr(
        "backend.bootstrap.startup.refresh_snapshot_async", lambda days: snapshot_task
    )

    config.skip_snapshot_warm = False
    config.snapshot_warm_days = 5
    service = AppLifecycleService(cfg=config)
    app = app_module.create_app()

    await service.startup(app)

    assert warmed == {"snapshot": {"ABC": 1}, "ts": "ts"}
    assert InstrumentApi.latest == {"ABC": 1}
    assert InstrumentApi.primed is True
    assert app.state.background_tasks == [snapshot_task]


@pytest.mark.asyncio
async def test_lifecycle_service_shutdown_cancels_tasks_and_temp_dirs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cleanup_called = {"page_cache": False}
    temp_dir = tmp_path / "isolated"
    temp_dir.mkdir()
    task = asyncio.Future()

    async def cancel_refresh_tasks():
        cleanup_called["page_cache"] = True

    monkeypatch.setattr(
        "backend.bootstrap.startup.page_cache.cancel_refresh_tasks", cancel_refresh_tasks
    )

    service = AppLifecycleService(cfg=config, temp_dirs=[temp_dir])
    app = app_module.create_app()
    app.state.background_tasks = [task]

    await service.shutdown(app)

    assert task.cancelled() is True
    assert cleanup_called["page_cache"] is True
    assert not temp_dir.exists()


@pytest.mark.asyncio
async def test_lifecycle_service_startup_survives_prime_latest_prices_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
):
    """Startup must not raise when prime_latest_prices fails.

    If the re-raise is present, the ASGI lifespan aborts and every subsequent
    request (including /docs) returns 500.  Remove the raise so that Lambda
    cold-start network failures are non-fatal.
    """

    def _fail_prime():
        raise RuntimeError("simulated network failure")

    monkeypatch.setattr("backend.bootstrap.startup._load_snapshot", lambda: ({}, None))
    monkeypatch.setattr(
        "backend.bootstrap.startup.refresh_snapshot_in_memory",
        lambda snapshot, ts: None,
    )
    monkeypatch.setattr(
        "backend.common.instrument_api.update_latest_prices_from_snapshot",
        lambda snapshot: None,
    )
    monkeypatch.setattr(
        "backend.common.instrument_api.prime_latest_prices",
        _fail_prime,
    )
    monkeypatch.setattr("backend.bootstrap.startup.refresh_snapshot_async", lambda days: None)

    config.skip_snapshot_warm = False
    service = AppLifecycleService(cfg=config)
    app = app_module.create_app()

    import logging

    with caplog.at_level(logging.ERROR):
        # Must not raise — previously the re-raise turned this into a 500 for all requests.
        await service.startup(app)

    assert any("prime" in r.message.lower() for r in caplog.records), (
        "Expected a log record mentioning 'prime' but got: "
        + str([r.message for r in caplog.records])
    )


def test_create_app_skips_snapshot_warm_when_disabled(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "skip_snapshot_warm", True, raising=False)

    warm_called = False

    async def unexpected_warm(*_args, **_kwargs):
        nonlocal warm_called
        warm_called = True

    monkeypatch.setattr(
        "backend.bootstrap.startup.AppLifecycleService._warm_snapshot", unexpected_warm
    )
    monkeypatch.setattr("backend.bootstrap.startup.refresh_snapshot_async", lambda days: None)

    app = app_module.create_app()
    with TestClient(app):
        pass

    assert warm_called is False
