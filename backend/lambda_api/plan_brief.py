"""Lambda entry point for the monthly plan-drift brief (#10475).

Follows ``backend.lambda_api.pension_report``: runs as a system job (no request
user, #8805), reports on the owners listed at ``PLAN_BRIEF_RECIPIENTS_URI``
(default ``ssm://plan-brief-recipients``; every owner when unset), catches
per-owner failures and raises one SNS alert listing them.

Each brief is built and saved by :func:`backend.plan_brief.service.run_brief`;
an owner without a saved plan is skipped. With ``PLAN_BRIEF_SEND_EMAIL=true``
the brief is also emailed to the owner's ``person.json`` email. Without
``MCP_SERVER_URL`` the brief is deterministic only and every review trigger is
reported as "can't evaluate".
"""

from __future__ import annotations

import asyncio
import datetime as dt
import logging
import os
from typing import Any, Dict, List, Optional

from backend.auth import system_job_context
from backend.common.alerts import publish_sns_alert
from backend.common.data_loader import resolve_default_accounts_root
from backend.common.investment_plan import PlanNotFoundError
from backend.common.portfolio_loader import list_portfolios
from backend.common.storage import get_storage
from backend.config import config
from backend.emails.plan_brief import send_plan_brief_email
from backend.logging_setup import sanitise_exception_traceback, sanitise_log_value
from backend.plan_brief.service import run_brief

logger = logging.getLogger(__name__)

_DEFAULT_RECIPIENTS_URI = "ssm://plan-brief-recipients"


def _load_recipient_owners() -> Optional[List[str]]:
    """Owners to brief, or ``None`` for every owner (owner keys only; no secrets).

    A missing parameter is not an error: ``ParameterStoreJSONStorage.load``
    logs and returns ``{}``, which means every owner.
    """
    uri = os.getenv("PLAN_BRIEF_RECIPIENTS_URI", _DEFAULT_RECIPIENTS_URI)
    # load() parses the parameter value as JSON ({} when missing); accept
    # {"owners": [...]} as the pension report does, or a bare JSON list.
    data: Any = get_storage(uri, param_type="String").load()
    owners = data.get("owners") if isinstance(data, dict) else data
    if not isinstance(owners, list) or not owners:
        if os.getenv("PLAN_BRIEF_RECIPIENTS_URI"):
            logger.warning(
                "PLAN_BRIEF_RECIPIENTS_URI %s gave no owner list; briefing every owner", sanitise_log_value(uri)
            )
        return None
    return [str(owner) for owner in owners]


def _send_email() -> bool:
    return os.getenv("PLAN_BRIEF_SEND_EMAIL", "").strip().lower() in {"1", "true", "yes"}


def lambda_handler(event, context):
    """Handler invoked by the monthly EventBridge rule."""
    with system_job_context():
        return asyncio.run(_run())


async def _brief_owner(owner: str, person: Dict[str, Any], today: dt.date) -> bool:
    """Build and save one owner's brief; ``False`` when the owner has no plan."""
    try:
        brief = await run_brief(
            owner, resolve_default_accounts_root(), cfg=config, mcp_server_url=config.mcp_server_url, today=today
        )
    except PlanNotFoundError:
        logger.info("No investment plan for %s; no brief", sanitise_log_value(owner))
        return False
    email = person.get("email")
    if _send_email() and email:
        send_plan_brief_email(email, brief, str(person.get("full_name") or owner))
    return True


async def _run() -> Dict[str, Any]:
    today = dt.date.today()
    try:
        target_owners = _load_recipient_owners()
        portfolios = list_portfolios()
    except Exception as exc:
        logger.error(
            "Plan brief failed to initialise: %s; traceback: %s",
            sanitise_log_value(exc),
            sanitise_exception_traceback(exc),
        )
        publish_sns_alert({"message": f"Plan brief Lambda failed to start: {exc}", "ticker": "plan-brief"})
        return {"briefs": 0, "errors": [str(exc)]}

    done = 0
    errors: List[str] = []
    for portfolio in portfolios:
        owner = portfolio["owner"]
        if target_owners is not None and owner not in target_owners:
            continue
        try:
            done += await _brief_owner(owner, portfolio.get("person") or {}, today)
        except Exception as exc:
            logger.error(
                "Plan brief failed for owner %s: %s; traceback: %s",
                sanitise_log_value(owner),
                sanitise_log_value(exc),
                sanitise_exception_traceback(exc),
            )
            errors.append(f"{owner}: {exc}")

    if errors:
        publish_sns_alert(
            {"message": f"Plan brief failed for {len(errors)} owner(s): {'; '.join(errors)}", "ticker": "plan-brief"}
        )
    return {"briefs": done, "errors": errors}
