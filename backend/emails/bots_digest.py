"""Bots digest email (#10485), following ``weekly_report.py`` / ``pension_report.py``.

Renders a stored :class:`~backend.bots.digest_models.Digest`. Money amounts in
the opener and item lines are hidden unless ``include_balances`` is set.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List

import boto3
from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.bots.digest_delivery import redact_amounts
from backend.bots.digest_models import Digest, DigestEntry

logger = logging.getLogger(__name__)

# Directory containing HTML templates
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Jinja2 environment for rendering email templates
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)

_STATUS_LABELS = {"new": "New", "still_open": "Still open", "resolved": "Resolved"}


def _safe_link(link: str | None) -> str:
    """Only app-relative or https links are rendered (no ``javascript:`` etc.)."""

    if link and (link.startswith("https://") or (link.startswith("/") and not link.startswith("//"))):
        return link
    return ""


def _row(entry: DigestEntry, include_balances: bool) -> Dict[str, str]:
    return {
        "severity": entry.severity.value,
        "status": _STATUS_LABELS[entry.status],
        "title": redact_amounts(entry.title, include_balances),
        "summary": redact_amounts(entry.summary, include_balances),
        "bot": entry.bot,
        "link": _safe_link(entry.link),
        "action": "Action needed" if entry.action_required else "",
    }


def render_bots_digest(digest: Digest, include_balances: bool = False) -> str:
    """Render the digest email HTML from a template."""

    items: List[Dict[str, str]] = [_row(entry, include_balances) for entry in digest.items]
    resolved: List[Dict[str, str]] = [_row(entry, include_balances) for entry in digest.resolved]
    template = _env.get_template("bots_digest.html")
    return template.render(
        owner=digest.owner,
        date=digest.generated_at.date().isoformat(),
        opener=redact_amounts(digest.opener, include_balances),
        items=items,
        resolved=resolved,
        not_run=[bot.name for bot in digest.bots if bot.state == "not_run_yet"],
        truncated=sum(digest.truncated.values()),
    )


_SENDER_EMAIL = os.getenv("BOTS_DIGEST_FROM", "no-reply@allotmint.com")


def send_bots_digest_email(user_email: str, digest: Digest, include_balances: bool = False) -> None:
    """Send the digest email via AWS SES."""

    body_html = render_bots_digest(digest, include_balances)
    count = len(digest.items)
    subject = f"Bots digest - {count} item{'s' if count != 1 else ''} need you" if count else "Bots digest - all clear"

    ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=_SENDER_EMAIL,
        Destination={"ToAddresses": [user_email]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body_html}},
        },
    )
