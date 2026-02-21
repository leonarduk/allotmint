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

from backend.common import approvals, group_portfolio, portfolio, portfolio_utils
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

def run_owner_checks(threshold: float) -> list[dict]:
    findings = []
    owners = portfolio.list_owners()
    for owner in owners:
        dd = portfolio_utils.compute_max_drawdown(owner)
        entry = create_entry("owner", owner, dd, threshold)
        if dd is None or dd >= -threshold:
            logger.info(entry["message"])
        else:
            logger.warning(entry["message"])
            publish_alert({"message": entry["message"]})
            notify_slack(entry["message"])
        findings.append(entry)
    return findings


def run_group_checks(threshold: float) -> list[dict]:
    findings = []
    for grp in group_portfolio.list_groups():
        slug = grp.get("slug")
        dd = portfolio_utils.compute_group_max_drawdown(slug)
        entry = create_entry("group", slug, dd, threshold)
        if dd is None or dd >= -threshold:
            logger.info(entry["message"])
        else:
            logger.warning(entry["message"])
            publish_alert({"message": entry["message"]})
            notify_slack(entry["message"])
        findings.append(entry)
    return findings


def run_approvals_checks() -> list[dict]:
    findings = []
    owners = portfolio.list_owners()
    for owner in owners:
        try:
            path = approvals.approvals_path(owner)
        except FileNotFoundError:
            continue
        if not path.exists():
            msg = f"approvals file for '{owner}' not found at {path}"
            findings.append(
                {
                    "type": "missing_approvals",
                    "level": "warning",
                    "owner": owner,
                    "path": str(path),
                    "message": msg,
                }
            )
    return findings


def run_metadata_checks() -> list[dict]:
    findings = []
    for path in sorted(portfolio_utils._MISSING_META):
        msg = f"Instrument metadata {path} not found"
        findings.append(
            {
                "type": "missing_metadata",
                "level": "warning",
                "path": path,
                "message": msg,
            }
        )
    return findings


def create_entry(type_: str, name: str, dd: Optional[float], threshold: float) -> dict:
    entry = {
        "type": type_,
        "name": name,
        "drawdown": dd,
        "alert": bool(dd is not None and dd < -threshold),
    }
    if dd is None:
        entry.update(
            {
                "level": "info",
                "message": f"{type_.capitalize()} {name} max drawdown unavailable",
            }
        )
    else:
        msg = f"{type_.capitalize()} {name} max drawdown {dd*100:.2f}%"
        if dd < -threshold:
            msg = (
                f"{type_.capitalize()} {name} drawdown {dd*100:.2f}% exceeds "
                f"{threshold*100:.2f}%"
            )
        entry["message"] = msg
    return entry


def run_check(threshold: float) -> list[dict]:
    findings = []
    findings.extend(run_owner_checks(threshold))
    findings.extend(run_group_checks(threshold))
    findings.extend(run_approvals_checks())
    findings.extend(run_metadata_checks())
    return findings


def main() -> None:
    threshold = float(os.getenv("DRAWDOWN_THRESHOLD", "0.2"))
    for finding in run_check(threshold):
        level = finding.get("level")
        msg = finding.get("message")
        if level == "warning":
            logger.warning(msg)
        else:
            logger.info(msg)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
