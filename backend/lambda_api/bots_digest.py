"""Lambda entry point for the bots digest (#10485).

Meant to run daily. For each owner it composes the digest from the latest bot
run records and sends any immediate alerts the owner's settings ask for
(``alert_immediately_for``). On the owner's digest day (Monday for a weekly
digest, the 1st for a monthly one, or whenever the event has ``"force": true``)
it also saves the digest and delivers it by email and/or Telegram/SNS.

Owners come from ``list_portfolios()``, optionally narrowed by the
comma-separated ``BOTS_DIGEST_OWNERS``. An owner whose email is one of the
deployment's ``allowed_emails`` (an admin) also sees system-wide items.

Runs inside :func:`backend.auth.system_job_context`, like the pension report:
a scheduled job has no request user (#8805). Per-owner failures are logged and
reported through ``publish_sns_alert``; they do not stop other owners.

The EventBridge rule and IAM for this handler are not wired in CDK yet: no bot
writes run records until the registry (#10477) lands.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any, Dict, List, Optional

from backend.auth import system_job_context
from backend.bots import digest_store
from backend.bots.digest import compose_digest
from backend.bots.digest_delivery import send_digest_telegram, send_immediate_alerts
from backend.bots.digest_settings import DigestSettings, load_settings
from backend.bots.run_records import FileRunRecordSource, RunRecordSource
from backend.common.alerts import publish_sns_alert
from backend.common.portfolio_loader import list_portfolios
from backend.config import config
from backend.emails.bots_digest import send_bots_digest_email
from backend.logging_setup import sanitise_exception_traceback, sanitise_log_value

logger = logging.getLogger(__name__)

_ALERT_TICKER = "bots-digest"


def is_due(settings: DigestSettings, today: dt.date) -> bool:
    if settings.period == "monthly":
        return today.day == 1
    return today.weekday() == 0


def _is_admin_email(email: Optional[str]) -> bool:
    allowed = {e.strip().lower() for e in (config.allowed_emails or []) if isinstance(e, str) and e.strip()}
    return bool(email) and str(email).strip().lower() in allowed


def _target_owners() -> Optional[List[str]]:
    raw = os.getenv("BOTS_DIGEST_OWNERS", "")
    owners = [o.strip() for o in raw.split(",") if o.strip()]
    return owners or None


def run_owner(
    owner: str,
    person: Dict[str, Any],
    source: RunRecordSource,
    now: dt.datetime,
    force: bool = False,
) -> Dict[str, Any]:
    """Compose, alert and (when due) save and deliver one owner's digest."""

    settings = load_settings(owner)
    email = person.get("email")
    digest = compose_digest(
        owner,
        source,
        previous=digest_store.load_latest(owner),
        now=now,
        include_system=_is_admin_email(email),
        per_bot_cap=settings.per_bot_cap,
        period=settings.period,
    )
    result: Dict[str, Any] = {"alerted": len(send_immediate_alerts(owner, list(digest.items), settings))}
    if not (force or is_due(settings, now.date())):
        return {**result, "saved": False, "emailed": False}
    digest_store.save_digest(digest)
    deliver = bool(digest.items) or settings.send_when_empty
    emailed = deliver and settings.email_enabled and bool(email)
    if emailed:
        send_bots_digest_email(str(email), digest, settings.include_balances)
    if deliver and settings.telegram_enabled:
        send_digest_telegram(digest, settings)
    return {**result, "saved": True, "emailed": emailed}


def lambda_handler(event, context):
    """Lambda handler invoked by the scheduled EventBridge rule (or by hand)."""

    with system_job_context():
        return run_digest(event if isinstance(event, dict) else {})


def _report_failure(message: str) -> None:
    publish_sns_alert({"message": message, "ticker": _ALERT_TICKER})


def run_digest(event: Dict[str, Any], source: Optional[RunRecordSource] = None) -> Dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    force = bool(event.get("force"))
    try:
        portfolios = list_portfolios()
    except Exception as exc:
        logger.error("Bots digest failed to start: %s", sanitise_exception_traceback(exc))
        _report_failure(f"Bots digest Lambda failed to start: {type(exc).__name__}")
        return {"owners": 0, "errors": [type(exc).__name__]}

    wanted = _target_owners()
    records = source or FileRunRecordSource()
    done = 0
    errors: List[str] = []
    for portfolio in portfolios:
        owner = str(portfolio.get("owner") or "")
        if not owner or (wanted is not None and owner not in wanted):
            continue
        try:
            run_owner(owner, portfolio.get("person") or {}, records, now, force)
            done += 1
        except Exception as exc:
            logger.error(
                "Bots digest failed for owner %s: %s",
                sanitise_log_value(owner),
                sanitise_exception_traceback(exc),
            )
            errors.append(f"{owner}: {type(exc).__name__}")

    if errors:
        _report_failure(f"Bots digest failed for {len(errors)} owner(s): {'; '.join(errors)}")
    return {"owners": done, "errors": errors}
