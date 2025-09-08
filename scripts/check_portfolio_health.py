#!/usr/bin/env python3
"""Nightly portfolio health check.

Iterates over all owner and group portfolios and logs the maximum drawdown.
Any drawdown beyond a configurable threshold triggers an alert via logs,
Slack (when ``SLACK_WEBHOOK_URL`` is set) and the existing alert pipeline.

Environment variables
---------------------
DRAWDOWN_THRESHOLD
    Absolute drawdown percentage required to trigger an alert.
    Defaults to ``0.2`` (20%).
SLACK_WEBHOOK_URL
    Optional Slack incoming webhook to post alerts.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.append(str(Path(__file__).resolve().parents[1]))

import requests

from backend.common import portfolio, group_portfolio, portfolio_utils
from backend.common.alerts import publish_alert

logger = logging.getLogger("check_portfolio_health")


def notify_slack(message: str) -> None:
    """Post ``message`` to Slack when a webhook URL is configured."""
    url = os.getenv("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        requests.post(url, json={"text": message}, timeout=5)
    except Exception as exc:  # pragma: no cover - best effort notification
        logger.warning("Failed to send Slack notification: %s", exc)


def _check(name: str, drawdown: Optional[float], threshold: float, *, label: str) -> None:
    """Log drawdown for ``name`` and alert if it exceeds ``threshold``."""
    if drawdown is None:
        logger.info("%s %s max drawdown unavailable", label, name)
        return
    logger.info("%s %s max drawdown %.2f%%", label, name, drawdown * 100)
    if drawdown < -threshold:
        msg = f"{label} {name} drawdown {drawdown*100:.2f}% exceeds {threshold*100:.2f}%"
        logger.warning(msg)
        publish_alert({"message": msg})
        notify_slack(msg)


def main() -> None:
    threshold = float(os.getenv("DRAWDOWN_THRESHOLD", "0.2"))
    for owner in portfolio.list_owners():
        dd = portfolio_utils.compute_max_drawdown(owner)
        _check(owner, dd, threshold, label="Owner")
    for grp in group_portfolio.list_groups():
        slug = grp.get("slug")
        dd = portfolio_utils.compute_group_max_drawdown(slug)
        _check(slug, dd, threshold, label="Group")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
