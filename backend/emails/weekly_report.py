from __future__ import annotations

from dataclasses import dataclass
import logging
import os
from pathlib import Path
from typing import Dict

import boto3
from jinja2 import Environment, FileSystemLoader, select_autoescape

logger = logging.getLogger(__name__)

# Directory containing HTML templates
_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# Jinja2 environment for rendering email templates
_env = Environment(
    loader=FileSystemLoader(_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)


@dataclass
class WeeklyReport:
    """Data required to render a weekly report email."""

    week_number: int
    portfolio_stats: Dict[str, str]
    holdings_table: str
    transactions_table: str


def render_weekly_report(report: WeeklyReport) -> str:
    """Render the weekly report email HTML from a template."""

    template = _env.get_template("weekly_report.html")
    return template.render(
        week_number=report.week_number,
        portfolio_stats=report.portfolio_stats,
        holdings_table=report.holdings_table,
        transactions_table=report.transactions_table,
    )


_SENDER_EMAIL = os.getenv("WEEKLY_REPORT_FROM", "no-reply@allotmint.com")


def send_weekly_report_email(user_email: str, report: WeeklyReport) -> None:
    """Send the weekly report email via AWS SES."""

    body_html = render_weekly_report(report)
    subject = f"Weekly Report - Week {report.week_number}"

    ses = boto3.client("ses", region_name=os.getenv("AWS_REGION", "us-east-1"))
    ses.send_email(
        Source=_SENDER_EMAIL,
        Destination={"ToAddresses": [user_email]},
        Message={
            "Subject": {"Data": subject},
            "Body": {"Html": {"Data": body_html}},
        },
    )
