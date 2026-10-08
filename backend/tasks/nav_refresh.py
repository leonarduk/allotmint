"""Daily refresh of held investment trusts' NAVs from their published NAVs (#9232).

The refresh itself lives in allotmint-pro
(``allotmint_pro.screener.nav_refresh``): it finds the held closed-end funds,
reads each one's latest NAV from its manager's own published NAV page or file
(only where the manager's terms allow automated access) and records it in the
instrument metadata, never replacing a newer NAV with an older one.

This module schedules it and reports on it:

* ``nav_refresh_enabled: true`` in config.yaml starts a background task at app
  startup that runs the refresh daily at ``nav_refresh_time`` (Europe/London);
* ``python -m backend.tasks.nav_refresh`` runs it once now (manual trigger) and
  prints the per-ticker report as JSON;
* :func:`lambda_handler` runs it once from a scheduled event.

Every run logs one line per trust; trusts that could not be refreshed are
logged as warnings, and keep their stale/undated NAV, so they stay in the
valuation screen's ``nav_attention`` list.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from datetime import datetime, time, timedelta, timezone
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo

from backend import config as config_module
from backend.common.core_optional import CoreFeatureUnavailableError, missing_package
from backend.config import Config
from backend.logging_setup import sanitise_log_value

logger = logging.getLogger(__name__)

LONDON = ZoneInfo("Europe/London")
FEATURE = "Investment trust NAV refresh"
# Outcomes that leave a trust's NAV as it was, so it may still be flagged.
_NOT_REFRESHED = ("no_source", "no_announcement", "failed")


def run_nav_refresh(cfg: Optional[Config] = None) -> Dict[str, Any]:
    """Refresh every held trust's NAV once and return the per-ticker report.

    Raises :class:`CoreFeatureUnavailableError` when allotmint-pro is not installed.
    """

    if cfg is None:
        cfg = _current_config()
    try:
        from allotmint_pro.screener.nav_refresh import refresh_held_trust_navs
        from allotmint_pro.screener.nav_sources import CachedFetcher
    except ModuleNotFoundError as exc:
        if missing_package(exc):
            raise CoreFeatureUnavailableError(FEATURE) from exc
        raise
    from backend.common.portfolio_loader import list_portfolios

    fetch = CachedFetcher(
        ttl=cfg.nav_refresh_cache_ttl_seconds,
        min_interval=cfg.nav_refresh_request_interval_seconds,
    )
    report = refresh_held_trust_navs(list_portfolios(), fetch=fetch)
    log_report(report)
    return report


def _current_config() -> Config:
    current = getattr(config_module, "settings", None) or config_module.config
    if not isinstance(current, Config):
        raise RuntimeError("backend configuration is not loaded")
    return current


def log_report(report: Dict[str, Any]) -> None:
    """Log one line per trust (a warning when it was not refreshed) and the run's counts."""

    for row in report.get("results", []):
        outcome = row.get("outcome")
        level = logging.WARNING if outcome in _NOT_REFRESHED else logging.INFO
        logger.log(
            level,
            "NAV refresh %s: %s (nav_as_of %s -> %s) %s",
            sanitise_log_value(row.get("ticker")),
            sanitise_log_value(outcome),
            sanitise_log_value(row.get("previous_nav_as_of")),
            sanitise_log_value(row.get("nav_as_of")),
            sanitise_log_value(row.get("detail", "")),
        )
    logger.info("NAV refresh counts: %s", sanitise_log_value(report.get("counts")))


def seconds_until_next_run(now: datetime, at: str) -> float:
    """Seconds from ``now`` (timezone-aware) until the next ``at`` (HH:MM) in Europe/London.

    The difference is taken in UTC: subtracting two datetimes that share one
    ``ZoneInfo`` gives the wall-clock gap, an hour out on clock-change days.
    """

    hours, minutes = (int(part) for part in at.split(":"))
    local_now = now.astimezone(LONDON)
    target = datetime.combine(local_now.date(), time(hours, minutes), tzinfo=LONDON)
    if target <= local_now:
        target = datetime.combine(local_now.date() + timedelta(days=1), time(hours, minutes), tzinfo=LONDON)
    return (target.astimezone(timezone.utc) - local_now.astimezone(timezone.utc)).total_seconds()


async def nav_refresh_loop(
    cfg: Config,
    *,
    run: Callable[[Config], Dict[str, Any]] = run_nav_refresh,
    now: Callable[[], datetime] = lambda: datetime.now(LONDON),
    sleep: Callable[[float], Any] = asyncio.sleep,
) -> None:
    """Run the refresh daily at ``cfg.nav_refresh_time`` until cancelled; a failed run is logged, not fatal.

    A day on which ``offline_mode`` has been switched on since startup is skipped.
    """

    while True:
        await sleep(seconds_until_next_run(now(), cfg.nav_refresh_time))
        if cfg.offline_mode:
            logger.info("NAV refresh skipped: offline_mode is on")
            continue
        try:
            await asyncio.to_thread(run, cfg)
        except CoreFeatureUnavailableError:
            logger.error("NAV refresh disabled: allotmint-pro is not installed")
            return
        except Exception:
            logger.exception("Scheduled NAV refresh failed; trusts keep their previous NAVs")


def start_nav_refresh_task(cfg: Config) -> Optional[asyncio.Task]:
    """Start the daily refresh when ``nav_refresh_enabled`` (and not offline); otherwise ``None``."""

    if not cfg.nav_refresh_enabled:
        return None
    if cfg.offline_mode:
        logger.info("NAV refresh not scheduled: offline_mode is on")
        return None
    logger.info("NAV refresh scheduled daily at %s Europe/London", sanitise_log_value(cfg.nav_refresh_time))
    return asyncio.create_task(nav_refresh_loop(cfg))


def lambda_handler(_event: Any, _context: Any) -> Dict[str, Any]:
    """AWS Lambda entry point: run one refresh and return its counts."""

    return {"counts": run_nav_refresh()["counts"]}


def main(argv: Optional[list[str]] = None) -> int:
    """Manual trigger: run one refresh now and print the report; exit 1 if any trust failed.

    ``no_source`` and ``no_announcement`` exit 0: they describe the trust (no
    permitted source, or nothing published yet), not a broken run, and are
    already logged as warnings and kept in ``nav_attention``.
    """

    parser = argparse.ArgumentParser(description="Refresh held investment trusts' NAVs from published NAVs.")
    parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    report = run_nav_refresh()
    print(json.dumps(report, indent=2))
    return 1 if report["counts"].get("failed") else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
