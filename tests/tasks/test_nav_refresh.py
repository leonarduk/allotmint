"""Scheduling and reporting of the held-trust NAV refresh (#9232)."""

import asyncio
import logging
import sys
import types
from dataclasses import replace
from datetime import datetime, timezone

import pytest

import backend.tasks.nav_refresh as nav_task
from backend.common.core_optional import CoreFeatureUnavailableError
from backend.config import build_config

REPORT = {
    "run_at": "2026-10-08T17:30:00+00:00",
    "counts": {"held_trusts": 2, "updated": 1, "unchanged": 0, "no_source": 0, "no_announcement": 0, "failed": 1},
    "results": [
        {"ticker": "HFEL.L", "outcome": "updated", "previous_nav_as_of": "2026-02-28", "nav_as_of": "2026-10-07"},
        {"ticker": "JEGI.L", "outcome": "failed", "previous_nav_as_of": None, "detail": "HTTP 503"},
    ],
}


def _cfg(**overrides):
    return replace(build_config({}, check_google_auth=False), **overrides)


@pytest.mark.parametrize(
    "now, expected_hours",
    [
        # 17:00 BST (16:00 UTC) -> 18:30 BST the same day.
        (datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc), 1.5),
        # 19:00 BST -> 18:30 BST the next day.
        (datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc), 23.5),
        # Winter (GMT): 18:00 UTC is 18:00 local -> 30 minutes.
        (datetime(2026, 12, 1, 18, 0, tzinfo=timezone.utc), 0.5),
    ],
)
def test_seconds_until_next_run_uses_london_time(now, expected_hours):
    assert nav_task.seconds_until_next_run(now, "18:30") == expected_hours * 3600


def test_not_scheduled_unless_enabled():
    assert nav_task.start_nav_refresh_task(_cfg()) is None


def test_not_scheduled_offline():
    assert nav_task.start_nav_refresh_task(_cfg(nav_refresh_enabled=True, offline_mode=True)) is None


def test_scheduled_when_enabled(monkeypatch):
    async def fake_loop(cfg):
        return cfg.nav_refresh_time

    monkeypatch.setattr(nav_task, "nav_refresh_loop", fake_loop)

    async def scenario():
        task = nav_task.start_nav_refresh_task(_cfg(nav_refresh_enabled=True))
        assert task is not None
        return await task

    assert asyncio.run(scenario()) == "18:30"


def test_loop_survives_a_failed_run_and_keeps_running(caplog):
    runs = []
    sleeps = []

    def run(cfg):
        runs.append(cfg)
        if len(runs) == 1:
            raise RuntimeError("manager site down")
        return REPORT

    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) > 2:
            raise asyncio.CancelledError

    now = lambda: datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)  # noqa: E731
    with caplog.at_level(logging.ERROR, logger=nav_task.__name__), pytest.raises(asyncio.CancelledError):
        asyncio.run(nav_task.nav_refresh_loop(_cfg(), run=run, now=now, sleep=sleep))

    assert len(runs) == 2
    assert sleeps[0] == 1.5 * 3600
    assert "Scheduled NAV refresh failed" in caplog.text


def test_loop_stops_when_allotmint_pro_is_missing(caplog):
    def run(cfg):
        raise CoreFeatureUnavailableError(nav_task.FEATURE)

    async def sleep(seconds):
        return None

    now = lambda: datetime(2026, 10, 8, 16, 0, tzinfo=timezone.utc)  # noqa: E731
    with caplog.at_level(logging.ERROR, logger=nav_task.__name__):
        asyncio.run(nav_task.nav_refresh_loop(_cfg(), run=run, now=now, sleep=sleep))
    assert "allotmint-pro is not installed" in caplog.text


def test_run_requires_allotmint_pro(monkeypatch):
    monkeypatch.setitem(sys.modules, "allotmint_pro.screener.nav_refresh", None)
    with pytest.raises(CoreFeatureUnavailableError):
        nav_task.run_nav_refresh(_cfg())


def test_run_passes_rate_limit_settings_and_logs_each_ticker(monkeypatch, caplog):
    captured = {}

    class FakeFetcher:
        def __init__(self, *, ttl, min_interval):
            captured["fetcher"] = (ttl, min_interval)

    def fake_refresh(portfolios, *, fetch):
        captured["portfolios"] = portfolios
        assert isinstance(fetch, FakeFetcher)
        return REPORT

    monkeypatch.setitem(
        sys.modules,
        "allotmint_pro.screener.nav_refresh",
        types.SimpleNamespace(refresh_held_trust_navs=fake_refresh),
    )
    monkeypatch.setitem(
        sys.modules, "allotmint_pro.screener.nav_sources", types.SimpleNamespace(CachedFetcher=FakeFetcher)
    )
    monkeypatch.setattr("backend.common.portfolio_loader.list_portfolios", lambda: [{"owner": "steve"}])

    cfg = _cfg(nav_refresh_request_interval_seconds=3.0, nav_refresh_cache_ttl_seconds=120)
    with caplog.at_level(logging.INFO, logger=nav_task.__name__):
        assert nav_task.run_nav_refresh(cfg) is REPORT

    assert captured["fetcher"] == (120, 3.0)
    assert captured["portfolios"] == [{"owner": "steve"}]
    failed = [r for r in caplog.records if "JEGI.L" in r.getMessage()]
    assert failed and failed[0].levelno == logging.WARNING
    updated = [r for r in caplog.records if "HFEL.L" in r.getMessage()]
    assert updated and updated[0].levelno == logging.INFO


def test_main_prints_report_and_fails_on_failed_trusts(monkeypatch, capsys):
    monkeypatch.setattr(nav_task, "run_nav_refresh", lambda: REPORT)
    assert nav_task.main([]) == 1
    assert '"HFEL.L"' in capsys.readouterr().out


def test_lambda_handler_returns_counts(monkeypatch):
    monkeypatch.setattr(nav_task, "run_nav_refresh", lambda: REPORT)
    assert nav_task.lambda_handler({}, None) == {"counts": REPORT["counts"]}
